"""
Nykaa Seller Partner API ingestion.
Covers both Nykaa Fashion and Nykaa Beauty.
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

NYKAA_BASE = "https://seller.nykaa.com/api/v2"

NYKAA_STATUS_MAP = {
    "pending": "confirmed",
    "processing": "confirmed",
    "packed": "confirmed",
    "ready_to_ship": "rtd",
    "shipped": "dispatched",
    "out_for_delivery": "dispatched",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "return_initiated": "returned",
    "returned": "returned",
    "rto": "rto",
}


class NykaaIngester(BaseIngester):
    channel = "nykaa"

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Bearer {s.nykaa_api_token}",
            "X-Seller-Id": s.nykaa_seller_id,
            "Content-Type": "application/json",
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%d %H:%M:%S")
        page = 1

        while True:
            try:
                resp = httpx.get(
                    f"{NYKAA_BASE}/orders",
                    headers=self._headers(),
                    params={
                        "updated_at_min": since,
                        "page": page,
                        "limit": 50,
                        "status": "pending,processing,packed,ready_to_ship,shipped",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[nykaa] Failed to fetch page {page}: {e}")
                break

            orders = data.get("orders", [])
            if not orders:
                break

            for o in orders:
                addr = o.get("shipping_address", {})
                payment_mode = "cod" if o.get("payment_method", "").lower() == "cod" else "prepaid"

                items = []
                for item in o.get("line_items", []):
                    items.append({
                        "sku": item.get("seller_sku"),
                        "channel_sku_id": item.get("nykaa_sku_id"),
                        "name": item.get("product_title"),
                        "qty": item.get("quantity", 1),
                        "unit_price": float(item.get("price", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="nykaa",
                    channel_order_id=str(o["order_id"]),
                    status=NYKAA_STATUS_MAP.get(o.get("status", "").lower(), "pending"),
                    payment_mode=payment_mode,
                    customer_name=f"{addr.get('first_name', '')} {addr.get('last_name', '')}".strip(),
                    customer_phone=addr.get("phone"),
                    customer_email=o.get("customer_email"),
                    shipping_address=addr,
                    pincode=addr.get("zip"),
                    state=addr.get("province"),
                    total_amount=float(o.get("total_price", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
                    if o.get("created_at") else datetime.now(timezone.utc),
                )

            total = data.get("total_count", 0)
            if page * 50 >= total:
                break
            page += 1
