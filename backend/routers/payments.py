"""
Razorpay Payment Links — dynamic, per-tenant, per-product/cart/collection.

Key design decisions from API docs:
  - Razorpay has no native line-items array. Cart is encoded in description + notes.
  - notes supports up to 15 key-value pairs (256 chars each) — used for full cart metadata.
  - Per-tenant: each merchant connects their own Razorpay account via channel_credentials.
    Platform keys (global settings) are the fallback for the platform's own account.
  - The business name on the hosted payment page comes from the Razorpay account used —
    so merchants must connect their own account for their brand to appear.
"""
import hashlib
import hmac
import json
import logging
import time
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import get_settings
from ..database import get_db
from ..automation.logger import log_event
from ..middleware.auth import get_current_user, get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

RAZORPAY_BASE = "https://api.razorpay.com/v1"


# ------------------------------------------------------------------ #
# Auth helpers — per-tenant first, platform fallback
# ------------------------------------------------------------------ #

def _rz_auth_for_tenant(tenant_id: str | None = None) -> tuple[str, str]:
    """
    Load Razorpay credentials.
    Priority: tenant's own Razorpay account → platform global keys.
    Raises HTTPException if neither is configured.
    """
    if tenant_id:
        try:
            db = get_db()
            row = (
                db.table("channel_credentials")
                .select("credentials, connected")
                .eq("tenant_id", tenant_id)
                .eq("channel", "razorpay")
                .maybe_single()
                .execute()
            )
            if row.data and row.data.get("connected"):
                creds = json.loads(row.data["credentials"] or "{}")
                key_id = creds.get("key_id", "")
                key_secret = creds.get("key_secret", "")
                if key_id and key_secret:
                    return (key_id, key_secret)
        except Exception as e:
            logger.debug("Could not load tenant Razorpay creds: %s", e)

    # Fall back to platform keys
    s = get_settings()
    if s.razorpay_key_id and s.razorpay_key_secret:
        return (s.razorpay_key_id, s.razorpay_key_secret)

    raise HTTPException(
        status_code=503,
        detail="Razorpay not connected. Go to Integrations → Razorpay and add your API keys.",
    )


def _rz_auth():
    """Convenience wrapper for routes without tenant context."""
    return _rz_auth_for_tenant(None)


def _normalize_phone(phone: str) -> str:
    """Razorpay requires +91XXXXXXXXXX format."""
    p = phone.replace(" ", "").replace("-", "").replace("+", "")
    if p.startswith("91") and len(p) == 12:
        return "+" + p
    if len(p) == 10:
        return "+91" + p
    return "+" + p


# ------------------------------------------------------------------ #
# Schemas
# ------------------------------------------------------------------ #

class CartItem(BaseModel):
    product_id: Optional[str] = None
    sku: Optional[str] = None
    name: str
    price: float         # unit price in INR
    quantity: int = 1
    image_url: Optional[str] = None


class CreateLinkRequest(BaseModel):
    # What to charge for
    cart: List[CartItem]                    # one item = product, many = cart/collection

    # Who to charge
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None

    # Order tracking
    order_id: Optional[str] = None         # internal order ID — used as reference_id
    source: str = "dashboard"              # "whatsapp_bot" | "product_page" | "dashboard"

    # Link behaviour
    expire_hours: int = 24                 # link expires after N hours (default 24h)
    send_whatsapp: bool = False
    whatsapp_jid: Optional[str] = None

    # Partial payments (e.g. advance booking)
    accept_partial: bool = False
    first_min_partial_amount: Optional[float] = None


# Legacy single-item schema kept for backward compat with whatsapp bot
class CreatePaymentLinkRequest(BaseModel):
    order_id: str
    amount: float
    customer_name: str
    customer_phone: str
    customer_email: str = ""
    description: str = ""
    send_whatsapp: bool = True
    whatsapp_jid: str = ""


# ------------------------------------------------------------------ #
# Core link builder
# ------------------------------------------------------------------ #

def _build_link_payload(req: CreateLinkRequest, tenant_id: str | None, s) -> dict:
    """
    Construct the Razorpay API payload from a cart.
    Encodes line items into description (human-readable) + notes (machine-readable).
    """
    total = sum(item.price * item.quantity for item in req.cart)
    if total <= 0:
        raise HTTPException(status_code=400, detail="Cart total must be greater than ₹0")

    # Human-readable description shown on Razorpay payment page
    if len(req.cart) == 1:
        item = req.cart[0]
        qty_str = f" x{item.quantity}" if item.quantity > 1 else ""
        description = f"{item.name}{qty_str} — ₹{item.price * item.quantity:,.0f}"
    else:
        lines = [f"{i.name} x{i.quantity} ₹{i.price * i.quantity:,.0f}" for i in req.cart]
        description = "Order: " + ", ".join(lines[:4])  # keep under 255 chars
        if len(req.cart) > 4:
            description += f" +{len(req.cart) - 4} more"

    # notes: encode cart as JSON (split if needed — 256 char limit per note)
    cart_json = json.dumps([
        {"n": i.name, "sku": i.sku or "", "qty": i.quantity, "price": i.price}
        for i in req.cart
    ])
    notes: dict = {
        "order_id": req.order_id or "",
        "source": req.source,
        "tenant_id": tenant_id or "",
        "item_count": str(len(req.cart)),
        "total_items": str(sum(i.quantity for i in req.cart)),
    }
    # Store cart JSON — split across note slots if long (256 char limit each)
    if len(cart_json) <= 256:
        notes["cart"] = cart_json
    else:
        # Truncate to first 4 items to stay within notes limit
        short_cart = json.dumps([
            {"n": i.name, "sku": i.sku or "", "qty": i.quantity, "price": i.price}
            for i in req.cart[:4]
        ])
        notes["cart"] = short_cart[:256]

    # Store individual product IDs for webhook lookup (up to 5)
    for idx, item in enumerate(req.cart[:5]):
        if item.product_id:
            notes[f"pid_{idx}"] = item.product_id[:256]

    payload: dict = {
        "amount": int(total * 100),         # paise
        "currency": "INR",
        "accept_partial": req.accept_partial,
        "description": description[:255],
        "reference_id": req.order_id or f"d2c-{int(time.time())}",
        "expire_by": int(time.time()) + (req.expire_hours * 3600),
        "customer": {
            "name": req.customer_name,
            "contact": _normalize_phone(req.customer_phone),
            "email": req.customer_email or "noreply@d2cflow.in",
        },
        "notify": {
            "sms": True,
            "email": bool(req.customer_email),
        },
        "reminder_enable": True,
        "notes": notes,
        "callback_url": f"{s.app_base_url}/api/payments/webhook",
        "callback_method": "get",
    }

    if req.accept_partial and req.first_min_partial_amount:
        payload["first_min_partial_amount"] = int(req.first_min_partial_amount * 100)

    return payload


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@router.get("/status")
def payments_status(user=Depends(get_current_user)):
    """Check if Razorpay is connected — tenant account first, then platform."""
    tenant_id = get_tenant_id(user)
    try:
        key_id, _ = _rz_auth_for_tenant(tenant_id)
        # Quick check — list payment links with limit=1
        resp = httpx.get(
            f"{RAZORPAY_BASE}/payment_links",
            auth=(key_id, _),
            params={"count": 1},
            timeout=10,
        )
        account_type = "tenant" if tenant_id else "platform"
        return {
            "connected": resp.status_code == 200,
            "account_type": account_type,
            "key_id_preview": key_id[:12] + "…",
        }
    except HTTPException as e:
        return {"connected": False, "error": e.detail}


@router.post("/create-link")
def create_link(req: CreateLinkRequest, user=Depends(get_current_user)):
    """
    Create a dynamic Razorpay Payment Link from a cart (1 product, multiple products, or a collection).
    Uses the merchant's own Razorpay account if connected, otherwise platform account.
    """
    s = get_settings()
    tenant_id = get_tenant_id(user)
    auth = _rz_auth_for_tenant(tenant_id)
    payload = _build_link_payload(req, tenant_id, s)

    try:
        resp = httpx.post(f"{RAZORPAY_BASE}/payment_links", auth=auth, json=payload, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e.response.text}")

    data = resp.json()
    short_url = data.get("short_url", "")
    link_id = data.get("id", "")

    if not short_url:
        raise HTTPException(status_code=502, detail=f"No short_url in Razorpay response: {data}")

    total = sum(i.price * i.quantity for i in req.cart)
    logger.info("Payment link created: tenant=%s order=%s link=%s amount=%.2f",
                tenant_id, req.order_id, link_id, total)
    log_event("payment_link_created", "order", req.order_id or link_id, "success",
              f"link={link_id} amount={total}")

    wa_sent = False
    if req.send_whatsapp and req.whatsapp_jid:
        wa_sent = _send_link_via_whatsapp(
            jid=req.whatsapp_jid,
            name=req.customer_name,
            short_url=short_url,
            amount=total,
            order_id=req.order_id or link_id,
        )

    return {
        "success": True,
        "link_id": link_id,
        "short_url": short_url,
        "amount": total,
        "item_count": len(req.cart),
        "expires_in_hours": req.expire_hours,
        "whatsapp_sent": wa_sent,
    }


@router.post("/create-link-legacy")
def create_link_legacy(req: CreatePaymentLinkRequest):
    """
    Legacy single-amount endpoint — used internally by the WhatsApp bot.
    Converts to the new cart format.
    """
    s = get_settings()
    auth = _rz_auth()

    description = req.description or f"Payment for order {req.order_id}"
    payload = {
        "amount": int(req.amount * 100),
        "currency": "INR",
        "accept_partial": False,
        "description": description[:255],
        "reference_id": req.order_id,
        "expire_by": int(time.time()) + 86400,
        "customer": {
            "name": req.customer_name,
            "contact": _normalize_phone(req.customer_phone),
            "email": req.customer_email or "noreply@d2cflow.in",
        },
        "notify": {"sms": True, "email": bool(req.customer_email)},
        "reminder_enable": True,
        "notes": {"order_id": req.order_id, "source": "whatsapp_bot"},
        "callback_url": f"{s.app_base_url}/api/payments/webhook",
        "callback_method": "get",
    }

    try:
        resp = httpx.post(f"{RAZORPAY_BASE}/payment_links", auth=auth, json=payload, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e.response.text}")

    data = resp.json()
    short_url = data.get("short_url", "")
    link_id = data.get("id", "")

    wa_sent = False
    if req.send_whatsapp and req.whatsapp_jid:
        wa_sent = _send_link_via_whatsapp(
            jid=req.whatsapp_jid,
            name=req.customer_name,
            short_url=short_url,
            amount=req.amount,
            order_id=req.order_id,
        )

    return {"success": True, "link_id": link_id, "short_url": short_url,
            "amount": req.amount, "status": data.get("status"), "whatsapp_sent": wa_sent}


@router.get("/link/{link_id}")
def get_link_status(link_id: str, user=Depends(get_current_user)):
    """Check the status of a payment link."""
    tenant_id = get_tenant_id(user)
    auth = _rz_auth_for_tenant(tenant_id)
    try:
        resp = httpx.get(f"{RAZORPAY_BASE}/payment_links/{link_id}", auth=auth, timeout=15)
        resp.raise_for_status()
        d = resp.json()
        return {
            "link_id": link_id,
            "status": d.get("status"),
            "amount": d.get("amount", 0) / 100,
            "amount_paid": d.get("amount_paid", 0) / 100,
            "short_url": d.get("short_url"),
            "reference_id": d.get("reference_id"),
            "description": d.get("description"),
            "customer": d.get("customer", {}),
            "expire_by": d.get("expire_by"),
            "payments": d.get("payments", []),
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e.response.text}")


@router.get("/links")
def list_links(
    count: int = 20,
    status: Optional[str] = None,
    user=Depends(get_current_user),
):
    """List recent payment links for the tenant."""
    tenant_id = get_tenant_id(user)
    auth = _rz_auth_for_tenant(tenant_id)
    params = {"count": min(count, 100)}
    if status:
        params["status"] = status
    try:
        resp = httpx.get(f"{RAZORPAY_BASE}/payment_links", auth=auth, params=params, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [
            {
                "link_id": i.get("id"),
                "short_url": i.get("short_url"),
                "status": i.get("status"),
                "amount": i.get("amount", 0) / 100,
                "amount_paid": i.get("amount_paid", 0) / 100,
                "description": i.get("description"),
                "reference_id": i.get("reference_id"),
                "created_at": i.get("created_at"),
                "customer": i.get("customer", {}),
            }
            for i in items
        ]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e.response.text}")


# ------------------------------------------------------------------ #
# Webhook — payment.captured → mark paid → ship
# ------------------------------------------------------------------ #

@router.post("/webhook")
async def razorpay_webhook(request: Request):
    """
    Configure in Razorpay Dashboard → Webhooks:
      URL: https://yourdomain.com/api/payments/webhook
      Events: payment.captured, payment_link.paid
    """
    s = get_settings()
    body = await request.body()

    if s.razorpay_webhook_secret:
        sig = request.headers.get("X-Razorpay-Signature", "")
        expected = hmac.new(
            s.razorpay_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = json.loads(body)
    event_type = event.get("event")

    if event_type not in ("payment.captured", "payment_link.paid"):
        return {"status": "ignored", "event": event_type}

    payload = event.get("payload", {})
    payment_entity = (
        payload.get("payment", {}).get("entity", {})
        or payload.get("payment_link", {}).get("entity", {})
    )
    notes = payment_entity.get("notes", {})
    internal_order_id = notes.get("order_id", "")
    amount_paid = payment_entity.get("amount", 0) / 100
    razorpay_payment_id = payment_entity.get("id", "")
    tenant_id = notes.get("tenant_id", "")

    if not internal_order_id:
        # Try reference_id as fallback
        internal_order_id = payment_entity.get("reference_id", "")

    if not internal_order_id:
        logger.warning("Webhook has no order_id in notes or reference_id: %s", event_type)
        return {"status": "no_order_id"}

    db = get_db()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    db.table("orders").update({
        "payment_status": "paid",
        "payment_id": razorpay_payment_id,
        "amount_paid": amount_paid,
        "paid_at": now,
        "status": "confirmed",
        "updated_at": now,
    }).eq("id", internal_order_id).execute()

    log_event("payment_captured", "order", internal_order_id, "success",
              f"rzp={razorpay_payment_id} ₹{amount_paid}")

    _auto_ship_after_payment(internal_order_id)
    _send_payment_confirmation(internal_order_id, amount_paid)

    return {"status": "ok", "order_id": internal_order_id, "amount_paid": amount_paid}


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _send_link_via_whatsapp(jid: str, name: str, short_url: str,
                             amount: float, order_id: str) -> bool:
    try:
        from ..routers.whatsapp import BRIDGE_API, _is_bridge_running
        if not _is_bridge_running():
            return False
        msg = (
            f"Hi {name.split()[0]}! 👋\n\n"
            f"Here's your secure payment link:\n\n"
            f"💳 *Amount:* ₹{amount:,.0f}\n"
            f"🔗 *Pay here:* {short_url}\n\n"
            f"Powered by Razorpay. Complete payment to confirm your order. 🙏"
        )
        resp = httpx.post(
            f"{BRIDGE_API}/api/send",
            json={"recipient": jid, "message": msg},
            timeout=10,
        )
        return resp.status_code < 400
    except Exception as e:
        logger.warning("WhatsApp send failed for payment link: %s", e)
        return False


def _auto_ship_after_payment(order_id: str):
    try:
        from ..couriers.shiprocket import ShiprocketClient
        from datetime import datetime, timezone

        db = get_db()
        order_res = db.table("orders").select("*").eq("id", order_id).execute()
        if not order_res.data:
            return
        o = order_res.data[0]
        if o.get("awb"):
            return

        items = db.table("order_items").select("*").eq("order_id", order_id).execute().data
        skus_data = db.table("skus").select("sku, weight_grams").execute().data
        sku_weights = {s["sku"]: s["weight_grams"] for s in skus_data}

        result = ShiprocketClient().create_shipment(o, items, sku_weights)
        db.table("orders").update({
            "awb": result["awb"],
            "courier": result["courier"],
            "shiprocket_order_id": result["shiprocket_order_id"],
            "label_url": result["label_url"],
            "status": "rtd",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", order_id).execute()

        log_event("auto_shipped", "order", order_id, "success",
                  f"AWB={result['awb']} Courier={result['courier']}")
    except Exception as e:
        logger.error("Auto-ship failed for order %s: %s", order_id, e)
        log_event("auto_ship_failed", "order", order_id, "failed", str(e))


def _send_payment_confirmation(order_id: str, amount_paid: float):
    try:
        from ..routers.whatsapp import BRIDGE_API, _is_bridge_running
        db = get_db()
        o = db.table("orders").select(
            "customer_name, customer_phone, awb, courier"
        ).eq("id", order_id).execute()
        if not o.data:
            return
        order = o.data[0]
        phone = order.get("customer_phone", "")
        if not phone:
            return

        clean = phone.replace(" ", "").replace("-", "").replace("+", "")
        jid = f"91{clean}@s.whatsapp.net" if len(clean) == 10 else f"{clean}@s.whatsapp.net"
        name = (order.get("customer_name") or "Customer").split()[0]
        awb = order.get("awb", "")
        courier = order.get("courier", "")

        msg = (
            f"✅ Payment received! Thank you, {name}!\n\n"
            f"💳 *Amount paid:* ₹{amount_paid:,.0f}\n"
        )
        if awb:
            msg += f"📦 *Dispatched via {courier}*\n🔍 *AWB:* {awb}\n"
        else:
            msg += "📦 Your order is being prepared for dispatch.\n"
        msg += "\nThank you for shopping with us! 🙏"

        if _is_bridge_running():
            httpx.post(f"{BRIDGE_API}/api/send",
                       json={"recipient": jid, "message": msg}, timeout=10)
    except Exception as e:
        logger.warning("Payment confirmation WA failed for order %s: %s", order_id, e)
