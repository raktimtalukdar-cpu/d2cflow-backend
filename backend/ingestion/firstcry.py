"""
FirstCry Seller API ingestion.
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

FIRSTCRY_BASE = "https://seller.firstcry.com/api/v1"

FIRSTCRY_STATUS_MAP = {
    "CONFIRMED": "confirmed",
    "PACKED": "confirmed",
    "READY_TO_SHIP": "rtd",
    "SHIPPED": "dispatched",
    "DELIVERED": "delivered",
    "CANCELLED": "cancelled",
    "RETURN_REQUESTED": "returned",
    "RETURNED": "returned",
    "RTO": "rto",
}


class FirstcryIngester(BaseIngester):
    channel = "firstcry"

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Bearer {s.firstcry_api_token}",
            "X-Seller-Code": s.firstcry_seller_code,
            "Content-Type": "application/json",
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%S")
        page = 1

        while True:
            try:
                resp = httpx.get(
                    f"{FIRSTCRY_BASE}/orders",
                    headers=self._headers(),
                    params={
                        "updated_from": since,
                        "page": page,
                        "page_size": 50,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[firstcry] Failed to fetch page {page}: {e}")
                break

            orders = data.get("orders", [])
            if not orders:
                break

            for o in orders:
                addr = o.get("delivery_address", {})
                payment_mode = "cod" if o.get("payment_type", "").upper() == "COD" else "prepaid"

                items = []
                for item in o.get("items", []):
                    items.append({
                        "sku": item.get("seller_sku"),
                        "channel_sku_id": item.get("firstcry_sku"),
                        "name": item.get("product_name"),
                        "qty": item.get("quantity", 1),
                        "unit_price": float(item.get("selling_price", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="firstcry",
                    channel_order_id=str(o["order_id"]),
                    channel_suborder_id=str(o.get("sub_order_id", "")),
                    status=FIRSTCRY_STATUS_MAP.get(o.get("status", ""), "pending"),
                    payment_mode=payment_mode,
                    customer_name=addr.get("full_name"),
                    customer_phone=addr.get("phone_number"),
                    shipping_address=addr,
                    pincode=str(addr.get("pincode", "")),
                    state=addr.get("state"),
                    total_amount=float(o.get("order_amount", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
                    if o.get("created_at") else datetime.now(timezone.utc),
                )

            has_more = data.get("has_more", False)
            if not has_more:
                break
            page += 1
