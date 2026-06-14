"""
Razorpay Payment Links router.
Creates a payment link for an order and optionally sends it via WhatsApp.
"""
import logging
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

RAZORPAY_BASE = "https://api.razorpay.com/v1"


def _rz_auth():
    s = get_settings()
    key_id = s.razorpay_key_id
    key_secret = s.razorpay_key_secret
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=503,
            detail="Razorpay credentials not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to backend/.env"
        )
    return (key_id, key_secret)


class CreatePaymentLinkRequest(BaseModel):
    order_id: str                      # your internal order ID
    amount: float                      # in INR
    customer_name: str
    customer_phone: str                # 10-digit or with country code
    customer_email: str = ""
    description: str = ""
    send_whatsapp: bool = True         # auto-send link via WhatsApp after creation
    whatsapp_jid: str = ""             # JID to send to (phone@s.whatsapp.net)


@router.get("/status")
def payments_status():
    """Check if Razorpay credentials are configured."""
    try:
        key_id, _ = _rz_auth()
        return {"connected": True, "key_id_preview": key_id[:8] + "…"}
    except HTTPException as e:
        return {"connected": False, "error": e.detail}


@router.post("/create-link")
def create_payment_link(req: CreatePaymentLinkRequest):
    """
    Create a Razorpay Payment Link for the given order amount.
    Returns the short URL. Optionally sends it via WhatsApp.
    """
    auth = _rz_auth()

    # Razorpay expects amount in paise (1 INR = 100 paise)
    amount_paise = int(req.amount * 100)
    if amount_paise <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    # Normalise phone — Razorpay needs +91XXXXXXXXXX format
    phone = req.customer_phone.replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        if phone.startswith("91") and len(phone) == 12:
            phone = "+" + phone
        elif len(phone) == 10:
            phone = "+91" + phone
        else:
            phone = "+" + phone

    description = req.description or f"Payment for order {req.order_id}"

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "accept_partial": False,
        "description": description,
        "customer": {
            "name": req.customer_name,
            "contact": phone,
            "email": req.customer_email or "noreply@d2cflow.in",
        },
        "notify": {
            "sms": True,
            "email": bool(req.customer_email),
        },
        "reminder_enable": True,
        "notes": {
            "order_id": req.order_id,
            "source": "d2cflow",
        },
        "callback_url": "",
        "callback_method": "get",
    }

    try:
        resp = httpx.post(
            f"{RAZORPAY_BASE}/payment_links",
            auth=auth,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay unreachable: {str(e)}")

    data = resp.json()
    link_id = data.get("id", "")
    short_url = data.get("short_url", "")
    status = data.get("status", "")

    if not short_url:
        raise HTTPException(status_code=502, detail=f"Razorpay did not return a payment link: {data}")

    logger.info("Payment link created: order=%s link_id=%s url=%s", req.order_id, link_id, short_url)

    # Send via WhatsApp if requested
    wa_sent = False
    if req.send_whatsapp and req.whatsapp_jid:
        try:
            wa_message = (
                f"Hi {req.customer_name.split()[0]}! 👋\n\n"
                f"Here's your payment link for your order *{req.order_id}*:\n\n"
                f"💳 *Amount:* ₹{req.amount:,.0f}\n"
                f"🔗 *Pay here:* {short_url}\n\n"
                f"This link is secure and powered by Razorpay. "
                f"Please complete the payment to confirm your order. 🙏"
            )
            bridge_resp = httpx.post(
                "http://localhost:8080/api/send",
                json={"recipient": req.whatsapp_jid, "message": wa_message},
                timeout=10,
            )
            wa_sent = bridge_resp.status_code < 400
        except Exception as e:
            logger.warning("WhatsApp send failed for payment link: %s", e)

    return {
        "success": True,
        "link_id": link_id,
        "short_url": short_url,
        "amount": req.amount,
        "status": status,
        "whatsapp_sent": wa_sent,
    }


@router.get("/link/{link_id}")
def get_payment_link_status(link_id: str):
    """Check the status of a payment link."""
    auth = _rz_auth()
    try:
        resp = httpx.get(
            f"{RAZORPAY_BASE}/payment_links/{link_id}",
            auth=auth,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "link_id": link_id,
            "status": data.get("status"),
            "amount_paid": data.get("amount_paid", 0) / 100,
            "short_url": data.get("short_url"),
            "payments": data.get("payments", []),
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e.response.text}")
