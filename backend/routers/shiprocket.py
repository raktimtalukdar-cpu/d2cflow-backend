"""
Shiprocket API router.
Handles auth (with in-memory token cache), shipment creation,
rate checking, AWB tracking and label generation.
No Supabase required — works standalone with just env vars.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shiprocket", tags=["shiprocket"])

SHIPROCKET_BASE = "https://apiv2.shiprocket.in/v1/external"

# ── In-memory token cache (avoids re-login on every request) ─────────────────
_token_cache: dict = {"token": None, "expires_at": None}


def _get_credentials():
    s = get_settings()
    email = s.shiprocket_email or os.environ.get("SHIPROCKET_EMAIL", "")
    password = s.shiprocket_password or os.environ.get("SHIPROCKET_PASSWORD", "")
    if not email or not password:
        raise HTTPException(
            status_code=503,
            detail="Shiprocket credentials not configured. Set SHIPROCKET_EMAIL and SHIPROCKET_PASSWORD env vars."
        )
    return email, password


def _get_token() -> str:
    now = datetime.now(timezone.utc)
    if _token_cache["token"] and _token_cache["expires_at"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    email, password = _get_credentials()
    try:
        resp = httpx.post(
            f"{SHIPROCKET_BASE}/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Shiprocket login failed: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Shiprocket unreachable: {str(e)}")

    data = resp.json()
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=502, detail=f"Shiprocket login error: {data}")

    _token_cache["token"] = token
    _token_cache["expires_at"] = now + timedelta(days=9)
    logger.info("Shiprocket token refreshed successfully")
    return token


def _headers():
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class OrderItem(BaseModel):
    name: str
    sku: str = ""
    qty: int = 1
    price: float = 0.0


class CreateShipmentRequest(BaseModel):
    # Order identity
    order_id: str                    # your internal order ID
    order_date: Optional[str] = None

    # Customer
    customer_name: str
    customer_phone: str
    customer_email: str = ""

    # Delivery address
    address: str
    city: str
    state: str
    pincode: str
    country: str = "India"

    # Items
    items: List[OrderItem]

    # Payment
    payment_method: str = "Prepaid"  # "Prepaid" | "COD"
    sub_total: float

    # Package dimensions (cm / kg)
    length: float = 10
    breadth: float = 10
    height: float = 10
    weight: float = 0.5

    # Pickup location name as configured in Shiprocket
    pickup_location: str = "Home"


class TrackRequest(BaseModel):
    awb: str


class RateRequest(BaseModel):
    pickup_pincode: str
    delivery_pincode: str
    weight: float = 0.5
    cod: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def shiprocket_status():
    """Check if Shiprocket credentials are configured and valid."""
    try:
        token = _get_token()
        return {"connected": True, "token_preview": token[:12] + "…"}
    except HTTPException as e:
        return {"connected": False, "error": e.detail}


@router.post("/shipment/create")
def create_shipment(req: CreateShipmentRequest):
    """
    Create a Shiprocket order + auto-assign best courier + return AWB.
    """
    order_date = req.order_date or datetime.now().strftime("%Y-%m-%d %H:%M")

    # Shiprocket requires separate first/last name
    name_parts = req.customer_name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else "."

    payload = {
        "order_id": req.order_id,
        "order_date": order_date,
        "pickup_location": req.pickup_location,
        "billing_customer_name": first_name,
        "billing_last_name": last_name,
        "billing_address": req.address,
        "billing_address_2": "",
        "billing_city": req.city,
        "billing_pincode": str(req.pincode),
        "billing_state": req.state,
        "billing_country": req.country,
        "billing_email": req.customer_email or "noreply@d2cflow.in",
        "billing_phone": str(req.customer_phone),
        "shipping_is_billing": True,
        "order_items": [
            {
                "name": item.name,
                "sku": item.sku or item.name[:20],
                "units": item.qty,
                "selling_price": str(item.price),
            }
            for item in req.items
        ],
        "payment_method": req.payment_method,
        "sub_total": req.sub_total,
        "length": req.length,
        "breadth": req.breadth,
        "height": req.height,
        "weight": req.weight,
    }

    try:
        resp = httpx.post(
            f"{SHIPROCKET_BASE}/orders/create/adhoc",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Order creation failed: {e.response.text}")

    data = resp.json()
    sr_order_id = data.get("order_id")
    shipment_id = data.get("shipment_id")

    if not shipment_id:
        raise HTTPException(status_code=502, detail=f"Shiprocket did not return shipment_id: {data}")

    # Auto-assign best courier & get AWB
    awb = ""
    courier_name = ""
    try:
        awb_resp = httpx.post(
            f"{SHIPROCKET_BASE}/courier/assign/awb",
            headers=_headers(),
            json={"shipment_id": str(shipment_id)},
            timeout=30,
        )
        awb_resp.raise_for_status()
        courier_data = awb_resp.json().get("response", {}).get("data", {})
        awb = courier_data.get("awb_code", "")
        courier_name = courier_data.get("courier_name", "")
    except Exception as e:
        logger.warning(f"AWB auto-assign failed (order still created): {e}")

    # Generate label URL
    label_url = ""
    try:
        label_resp = httpx.post(
            f"{SHIPROCKET_BASE}/courier/generate/label",
            headers=_headers(),
            json={"shipment_id": [shipment_id]},
            timeout=30,
        )
        label_resp.raise_for_status()
        label_url = label_resp.json().get("label_url", "")
    except Exception as e:
        logger.warning(f"Label generation failed: {e}")

    logger.info(f"Shipment created: order={req.order_id} sr_order={sr_order_id} awb={awb} courier={courier_name}")

    return {
        "success": True,
        "shiprocket_order_id": str(sr_order_id),
        "shipment_id": str(shipment_id),
        "awb": awb,
        "courier": courier_name,
        "label_url": label_url,
    }


@router.get("/track/{awb}")
def track_shipment(awb: str):
    """Track a shipment by AWB number."""
    try:
        resp = httpx.get(
            f"{SHIPROCKET_BASE}/courier/track/awb/{awb}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Tracking failed: {e.response.text}")


@router.post("/rates")
def check_rates(req: RateRequest):
    """Check shipping rates for a pincode pair."""
    try:
        resp = httpx.get(
            f"{SHIPROCKET_BASE}/courier/serviceability/",
            headers=_headers(),
            params={
                "pickup_postcode": req.pickup_pincode,
                "delivery_postcode": req.delivery_pincode,
                "weight": req.weight,
                "cod": 1 if req.cod else 0,
            },
            timeout=15,
        )
        resp.raise_for_status()
        couriers = resp.json().get("data", {}).get("available_courier_companies", [])
        # Return top 5 sorted by rate
        sorted_couriers = sorted(couriers, key=lambda c: c.get("rate", 9999))[:5]
        return {"couriers": sorted_couriers}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Rate check failed: {e.response.text}")


@router.post("/pickup/schedule")
def schedule_pickup(shipment_ids: List[int], pickup_date: Optional[str] = None):
    """Schedule a pickup for given shipment IDs."""
    if not pickup_date:
        pickup_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        resp = httpx.post(
            f"{SHIPROCKET_BASE}/courier/generate/pickup",
            headers=_headers(),
            json={"shipment_id": shipment_ids, "pickup_date": [pickup_date]},
            timeout=30,
        )
        resp.raise_for_status()
        return {"success": True, "pickup_date": pickup_date, "detail": resp.json()}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Pickup scheduling failed: {e.response.text}")


@router.get("/pickups")
def list_pickups():
    """List pickup locations configured in Shiprocket."""
    try:
        resp = httpx.get(
            f"{SHIPROCKET_BASE}/settings/company/pickup",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch pickups: {e.response.text}")
