"""
Meta Commerce router — WhatsApp catalog messages, Instagram seller cues,
catalog sync (import/export), and Razorpay payment link auto-send.

Covers:
  - GET  /api/meta/catalogs              — list merchant's Meta catalogs
  - POST /api/meta/catalog/import        — pull catalog from Meta → PIM
  - POST /api/meta/catalog/export        — push PIM products → Meta catalog
  - POST /api/meta/send/product          — send single product card on WhatsApp
  - POST /api/meta/send/catalog          — send multi-product list on WhatsApp
  - POST /api/meta/webhook               — receive WhatsApp + Instagram events
  - GET  /api/meta/instagram/cues        — unactioned Instagram purchase signals
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import get_settings
from ..database import get_db
from ..middleware.auth import get_current_user, get_tenant_id
from ..automation.logger import log_event

router = APIRouter(prefix="/api/meta", tags=["meta_commerce"])
logger = logging.getLogger(__name__)
META_BASE = "https://graph.facebook.com/v19.0"

# Purchase-intent keywords for Instagram comments/DMs
PURCHASE_KEYWORDS = {"buy", "price", "cost", "interested", "want", "order",
                     "how much", "kitna", "khareedna", "chahiye", "dm", "inbox"}


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _get_meta_creds(tenant_id: str) -> dict:
    """Load Meta credentials from channel_credentials for this tenant."""
    db = get_db()
    row = (
        db.table("channel_credentials")
        .select("credentials")
        .eq("tenant_id", tenant_id)
        .eq("channel", "meta")
        .maybe_single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=400, detail="Meta not connected. Go to Integrations → Meta and connect.")
    creds = json.loads(row.data["credentials"] or "{}")
    if not creds.get("access_token"):
        raise HTTPException(status_code=400, detail="Meta access token missing. Reconnect via Integrations.")
    return creds


def _wa_send(phone_number_id: str, access_token: str, to: str, payload: dict) -> dict:
    """Send any WhatsApp Cloud API message."""
    resp = httpx.post(
        f"{META_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": to, **payload},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------ #
# Catalog sync
# ------------------------------------------------------------------ #

@router.get("/catalogs")
def list_catalogs(user=Depends(get_current_user)):
    """List all Meta Commerce Manager catalogs for the merchant."""
    creds = _get_meta_creds(get_tenant_id(user))
    try:
        from ..catalog.meta_importer import MetaCatalogImporter
        importer = MetaCatalogImporter(
            access_token=creds["access_token"],
            business_id=creds.get("business_id"),
        )
        return {"catalogs": importer.get_catalogs()}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e.response.text}")


@router.post("/catalog/import")
def import_catalog(catalog_id: Optional[str] = None, user=Depends(get_current_user)):
    """Pull products from Meta catalog into d2cflow PIM."""
    creds = _get_meta_creds(get_tenant_id(user))
    from ..catalog.meta_importer import MetaCatalogImporter
    importer = MetaCatalogImporter(
        access_token=creds["access_token"],
        business_id=creds.get("business_id"),
    )
    if catalog_id:
        result = importer.import_catalog(catalog_id)
    else:
        result = importer.import_all()

    # Store catalog_id for product message sends
    if catalog_id:
        db = get_db()
        tenant_id = get_tenant_id(user)
        row = db.table("channel_credentials").select("credentials").eq("tenant_id", tenant_id).eq("channel", "meta").maybe_single().execute()
        if row.data:
            existing = json.loads(row.data["credentials"] or "{}")
            existing["catalog_id"] = catalog_id
            db.table("channel_credentials").update({"credentials": json.dumps(existing)}).eq("tenant_id", tenant_id).eq("channel", "meta").execute()

    return result


@router.post("/catalog/export")
def export_catalog(catalog_id: str, user=Depends(get_current_user)):
    """Push all PIM products to Meta catalog (makes them available on WhatsApp/Instagram)."""
    s = get_settings()
    creds = _get_meta_creds(get_tenant_id(user))
    from ..catalog.meta_exporter import MetaCatalogExporter
    exporter = MetaCatalogExporter(
        access_token=creds["access_token"],
        catalog_id=catalog_id,
    )
    return exporter.export_all(app_base_url=s.app_base_url)


# ------------------------------------------------------------------ #
# WhatsApp product messages
# ------------------------------------------------------------------ #

class SendProductRequest(BaseModel):
    to: str                    # customer phone e.g. 919876543210
    sku: str                   # our internal SKU → maps to Meta product
    body_text: str = "Check out this product! Reply YES to order."


class SendCatalogRequest(BaseModel):
    to: str
    skus: List[str]            # up to 30 SKUs
    header_text: str = "Our Products"
    body_text: str = "Browse and reply with the product name to order!"


@router.post("/send/product")
def send_product_message(req: SendProductRequest, user=Depends(get_current_user)):
    """
    Send a WhatsApp interactive product card (single item).
    Customer sees image, name, price + can tap to order.
    """
    creds = _get_meta_creds(get_tenant_id(user))
    db = get_db()

    # Look up Meta product ID from listings table
    listing = (
        db.table("listings")
        .select("channel_sku_id, listing_id")
        .eq("sku", req.sku)
        .eq("channel", "meta")
        .maybe_single()
        .execute()
    )
    if not listing.data:
        raise HTTPException(status_code=404, detail=f"SKU {req.sku} not found in Meta catalog. Export catalog first.")

    catalog_id = listing.data.get("listing_id") or creds.get("catalog_id", "")
    product_retailer_id = req.sku

    payload = {
        "type": "interactive",
        "interactive": {
            "type": "product",
            "body": {"text": req.body_text},
            "action": {
                "catalog_id": catalog_id,
                "product_retailer_id": product_retailer_id,
            },
        },
    }

    try:
        result = _wa_send(creds["phone_number_id"], creds["access_token"], req.to, payload)
        log_event("wa_product_sent", "sku", req.sku, "success", f"to={req.to}")
        return {"status": "sent", "message_id": result.get("messages", [{}])[0].get("id")}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {e.response.text}")


@router.post("/send/catalog")
def send_catalog_message(req: SendCatalogRequest, user=Depends(get_current_user)):
    """
    Send a WhatsApp multi-product list (up to 30 items).
    Customer can browse and tap to order.
    """
    creds = _get_meta_creds(get_tenant_id(user))
    db = get_db()

    catalog_id = creds.get("catalog_id", "")
    if not catalog_id:
        raise HTTPException(status_code=400, detail="No catalog linked. Import your Meta catalog first.")

    product_items = [{"product_retailer_id": sku} for sku in req.skus[:30]]

    payload = {
        "type": "interactive",
        "interactive": {
            "type": "product_list",
            "header": {"type": "text", "text": req.header_text},
            "body": {"text": req.body_text},
            "action": {
                "catalog_id": catalog_id,
                "sections": [{"title": "Products", "product_items": product_items}],
            },
        },
    }

    try:
        result = _wa_send(creds["phone_number_id"], creds["access_token"], req.to, payload)
        log_event("wa_catalog_sent", "system", catalog_id, "success",
                  f"to={req.to} items={len(product_items)}")
        return {"status": "sent", "items_sent": len(product_items),
                "message_id": result.get("messages", [{}])[0].get("id")}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {e.response.text}")


# ------------------------------------------------------------------ #
# Meta Webhook — WhatsApp messages + Instagram cues
# ------------------------------------------------------------------ #

@router.get("/webhook")
async def webhook_verify(
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None,
):
    """Webhook verification handshake from Meta."""
    s = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == s.meta_webhook_verify_token:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def webhook_receive(request: Request):
    """
    Receive all Meta events:
    - WhatsApp: text messages, order button taps, product inquiries
    - Instagram: comments with purchase intent, DMs
    """
    s = get_settings()
    body = await request.body()

    # Verify signature
    if s.meta_app_secret:
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            s.meta_app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(body)
    object_type = event.get("object")

    for entry in event.get("entry", []):
        if object_type == "whatsapp_business_account":
            for change in entry.get("changes", []):
                await _handle_whatsapp_change(change)
        elif object_type == "instagram":
            for change in entry.get("changes", []):
                await _handle_instagram_change(change)

    return {"status": "ok"}


async def _handle_whatsapp_change(change: dict):
    db = get_db()
    s = get_settings()
    value = change.get("value", {})
    messages = value.get("messages", [])
    contacts = value.get("contacts", [])
    phone_number_id = value.get("metadata", {}).get("phone_number_id", s.whatsapp_phone_number_id)

    # Find which tenant owns this phone_number_id
    cred_row = (
        db.table("channel_credentials")
        .select("credentials, tenant_id")
        .eq("channel", "whatsapp")
        .execute()
    )
    tenant_creds = None
    for row in (cred_row.data or []):
        c = json.loads(row.get("credentials") or "{}")
        if c.get("phone_number_id") == phone_number_id:
            tenant_creds = c
            break
    # Fall back to global settings
    if not tenant_creds:
        tenant_creds = {
            "phone_number_id": s.whatsapp_phone_number_id,
            "access_token": s.whatsapp_access_token,
        }

    contact_map = {c["wa_id"]: c.get("profile", {}).get("name", "") for c in contacts}

    for msg in messages:
        from_number = msg.get("from", "")
        customer_name = contact_map.get(from_number, from_number)
        msg_type = msg.get("type")
        msg_id = msg.get("id")

        if msg_type == "order":
            # Customer tapped "Order" on a WhatsApp product card
            order_data = msg.get("order", {})
            await _create_order_from_wa_product(from_number, customer_name, order_data, db, tenant_creds)

        elif msg_type == "text":
            text = msg.get("text", {}).get("body", "").strip()
            text_lower = text.lower()

            # YES / confirm → find pending order/broadcast → send Razorpay link
            if text_lower in ("yes", "yes!", "haan", "ha", "ok", "okay", "confirm", "order", "buy"):
                _handle_yes_reply(from_number, customer_name, db, tenant_creds)
            elif _has_purchase_intent(text_lower):
                _store_instagram_cue(db, "whatsapp", from_number, customer_name, text, msg_id)

        elif msg_type == "interactive":
            reply = msg.get("interactive", {})
            if reply.get("type") == "button_reply":
                btn_title = reply.get("button_reply", {}).get("title", "").lower()
                if btn_title in ("yes", "confirm", "order", "buy"):
                    _handle_yes_reply(from_number, customer_name, db, tenant_creds)


def _handle_yes_reply(from_number: str, customer_name: str, db, tenant_creds: dict):
    """
    Customer replied YES. Find the last broadcast sent to them,
    create an order, and send a Razorpay payment link.
    """
    try:
        # Look for a pending order for this customer
        existing = (
            db.table("orders")
            .select("id, channel_order_id, total_amount, customer_name")
            .eq("customer_phone", from_number)
            .eq("payment_status", "pending")
            .eq("channel", "whatsapp")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if existing.data:
            order = existing.data[0]
            _send_razorpay_for_wa_order(
                phone=from_number,
                name=order.get("customer_name") or customer_name,
                order_id=order["channel_order_id"],
                amount=float(order["total_amount"] or 0),
                tenant_creds=tenant_creds,
            )
        else:
            # No pending order — send friendly reply
            s = get_settings()
            pid = tenant_creds.get("phone_number_id", s.whatsapp_phone_number_id)
            token = tenant_creds.get("access_token", s.whatsapp_access_token)
            if pid and token:
                httpx.post(
                    f"{META_BASE}/{pid}/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "messaging_product": "whatsapp",
                        "to": from_number,
                        "type": "text",
                        "text": {"body": "Thanks for your interest! 😊 Please let us know which product you'd like to order and we'll send you the payment link right away."},
                    },
                    timeout=10,
                )
    except Exception as e:
        logger.error(f"Failed to handle YES reply from {from_number}: {e}")


async def _create_order_from_wa_product(phone: str, name: str, order_data: dict, db):
    """When customer taps Order button on WhatsApp product card, create order + send payment link."""
    items = order_data.get("product_items", [])
    if not items:
        return

    total = sum(float(i.get("item_price", 0)) * int(i.get("quantity", 1)) for i in items)
    order_items = []
    for i in items:
        order_items.append({
            "sku": i.get("product_retailer_id", ""),
            "name": i.get("product_retailer_id", ""),
            "qty": int(i.get("quantity", 1)),
            "unit_price": float(i.get("item_price", 0)),
            "cost_price": None,
        })

    order_id = f"WA-{phone[-6:]}-{int(datetime.now().timestamp())}"
    result = db.table("orders").insert({
        "channel": "whatsapp",
        "channel_order_id": order_id,
        "status": "confirmed",
        "payment_mode": "prepaid",
        "customer_name": name,
        "customer_phone": phone,
        "total_amount": total,
        "source": "whatsapp_product_card",
    }).execute()

    order_db_id = result.data[0]["id"]
    for item in order_items:
        item["order_id"] = order_db_id
    if order_items:
        db.table("order_items").insert(order_items).execute()

    log_event("wa_product_order", "order", order_id, "success",
              f"customer={name} total={total}")

    # Auto-send Razorpay payment link
    _send_razorpay_for_wa_order(phone, name, order_id, total)


def _send_razorpay_for_wa_order(phone: str, name: str, order_id: str, amount: float, tenant_creds: dict = None):
    """Generate Razorpay payment link and send back to the customer on WhatsApp."""
    try:
        s = get_settings()
        from ..routers.payments import _rz_auth, RAZORPAY_BASE
        import time
        auth = _rz_auth()
        norm_phone = phone if phone.startswith("+") else f"+{phone}"

        payload = {
            "amount": int(amount * 100),
            "currency": "INR",
            "description": f"WhatsApp Order {order_id}",
            "reference_id": order_id,
            "expire_by": int(time.time()) + 86400,
            "customer": {"name": name, "contact": norm_phone},
            "notify": {"sms": True, "email": False},
            "reminder_enable": True,
            "notes": {"order_id": order_id, "source": "whatsapp_product_card"},
            "callback_url": f"{s.app_base_url}/api/payments/webhook",
            "callback_method": "get",
        }
        resp = httpx.post(f"{RAZORPAY_BASE}/payment_links", auth=auth, json=payload, timeout=20)
        resp.raise_for_status()
        short_url = resp.json().get("short_url", "")

        pid = (tenant_creds or {}).get("phone_number_id") or s.whatsapp_phone_number_id
        token = (tenant_creds or {}).get("access_token") or s.whatsapp_access_token
        if short_url and pid and token:
            msg = (
                f"Thank you for your order! 🎉\n\n"
                f"💳 *Amount:* ₹{amount:,.0f}\n"
                f"🔗 *Pay here:* {short_url}\n\n"
                f"Complete payment to confirm dispatch. Powered by Razorpay 🙏"
            )
            httpx.post(
                f"{META_BASE}/{pid}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "to": phone,
                      "type": "text", "text": {"body": msg}},
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Failed to send Razorpay link for WA order {order_id}: {e}")


async def _handle_instagram_change(change: dict):
    """Handle Instagram comments and DMs for purchase intent."""
    db = get_db()
    field = change.get("field")
    value = change.get("value", {})

    if field == "comments":
        text = value.get("text", "").lower()
        sender_id = value.get("from", {}).get("id", "")
        sender_name = value.get("from", {}).get("username", sender_id)
        media_id = value.get("media", {}).get("id", "")
        comment_id = value.get("id", "")

        if _has_purchase_intent(text):
            _store_instagram_cue(db, "instagram_comment", sender_id, sender_name,
                                 text, comment_id, media_id=media_id)

    elif field == "messages":
        msg = value.get("message", {})
        text = (msg.get("text") or "").lower()
        sender_id = value.get("sender", {}).get("id", "")
        msg_id = msg.get("mid", "")

        if _has_purchase_intent(text) or text in ("buy", "yes", "order"):
            _store_instagram_cue(db, "instagram_dm", sender_id, "", text, msg_id)


def _has_purchase_intent(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in PURCHASE_KEYWORDS)


def _store_instagram_cue(db, channel: str, sender_id: str, sender_name: str,
                          text: str, message_id: str, media_id: str = None):
    """Store a purchase-intent signal for merchant review."""
    db.table("instagram_cues").upsert({
        "channel": channel,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_text": text[:500],
        "message_id": message_id,
        "media_id": media_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="message_id").execute()


# ------------------------------------------------------------------ #
# Instagram cues — list + action
# ------------------------------------------------------------------ #

@router.get("/instagram/cues")
def list_instagram_cues(
    status: Optional[str] = "pending",
    limit: int = 50,
    user=Depends(get_current_user),
):
    """List Instagram comments/DMs with purchase intent."""
    db = get_db()
    q = db.table("instagram_cues").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    return q.execute().data


class ReplyRequest(BaseModel):
    cue_id: str
    reply_text: str
    send_payment_link: bool = False
    amount: Optional[float] = None
    sku: Optional[str] = None


@router.post("/instagram/reply")
def reply_to_cue(req: ReplyRequest, user=Depends(get_current_user)):
    """Reply to an Instagram DM/comment and optionally send a Razorpay payment link."""
    db = get_db()
    creds = _get_meta_creds(get_tenant_id(user))

    cue = db.table("instagram_cues").select("*").eq("id", req.cue_id).maybe_single().execute()
    if not cue.data:
        raise HTTPException(status_code=404, detail="Cue not found")

    cue_data = cue.data
    sender_id = cue_data["sender_id"]
    reply_text = req.reply_text

    if req.send_payment_link and req.amount:
        import time
        from ..routers.payments import _rz_auth, RAZORPAY_BASE
        s = get_settings()
        try:
            auth = _rz_auth()
            rz_payload = {
                "amount": int(req.amount * 100),
                "currency": "INR",
                "description": req.sku or "Instagram Order",
                "expire_by": int(time.time()) + 86400,
                "notes": {"source": "instagram_cue", "cue_id": req.cue_id},
                "callback_url": f"{s.app_base_url}/api/payments/webhook",
                "callback_method": "get",
            }
            rz_resp = httpx.post(f"{RAZORPAY_BASE}/payment_links", auth=auth, json=rz_payload, timeout=20)
            rz_resp.raise_for_status()
            short_url = rz_resp.json().get("short_url", "")
            if short_url:
                reply_text = f"{reply_text}\n\n💳 Pay here: {short_url}"
        except Exception as e:
            logger.error(f"Razorpay link failed for Instagram cue: {e}")

    # Send via Instagram Graph API (DM reply)
    if cue_data["channel"] == "instagram_dm":
        try:
            httpx.post(
                f"{META_BASE}/me/messages",
                headers={"Authorization": f"Bearer {creds['access_token']}"},
                json={"recipient": {"id": sender_id}, "message": {"text": reply_text}},
                timeout=15,
            ).raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Instagram send failed: {e}")

    db.table("instagram_cues").update({
        "status": "replied",
        "reply_text": reply_text[:500],
        "replied_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", req.cue_id).execute()

    return {"status": "replied", "cue_id": req.cue_id}


# ------------------------------------------------------------------ #
# Catalog status
# ------------------------------------------------------------------ #

@router.get("/catalog/status")
def catalog_status(user=Depends(get_current_user)):
    """Summary of products synced to Meta catalog."""
    db = get_db()
    meta_listings = (
        db.table("listings")
        .select("sku, is_active, last_synced_at")
        .eq("channel", "meta")
        .execute()
    )
    active = sum(1 for l in meta_listings.data if l.get("is_active"))
    latest_sync = max(
        (l["last_synced_at"] for l in meta_listings.data if l.get("last_synced_at")),
        default=None
    )
    return {
        "total_synced": len(meta_listings.data),
        "active": active,
        "last_synced_at": latest_sync,
    }
