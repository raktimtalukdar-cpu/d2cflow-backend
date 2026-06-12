"""
Meesho Supplier API ingestion.
API base: https://external.meesho.com/api/v1
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

MEESHO_BASE = "https://external.meesho.com/api/v1"

MEESHO_STATUS_MAP = {
    "NEW": "confirmed",
    "READY_TO_SHIP": "rtd",
    "SHIPPED": "dispatched",
    "DELIVERED": "delivered",
    "CANCELLED": "cancelled",
    "RETURN_REQUESTED": "returned",
    "RETURNED": "returned",
    "RTO": "rto",
}


class MeeshoIngester(BaseIngester):
    channel = "meesho"

    def _headers(self):
        s = get_settings()
        return {
            "api-token": s.meesho_api_token,
            "Content-Type": "application/json",
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%d")
        page = 1

        while True:
            payload = {
                "from_date": since,
                "to_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "page_no": page,
                "page_size": 50,
            }
            resp = httpx.post(f"{MEESHO_BASE}/supplier/orders/fetch",
                              headers=self._headers(), json=payload, timeout=30)
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            data = resp.json()

            orders = data.get("data", [])
            if not orders:
                break

            for o in orders:
                addr = o.get("delivery_address", {})
                items = []
                for li in o.get("sub_orders", []):
                    items.append({
                        "sku": li.get("seller_sku_code"),
                        "channel_sku_id": li.get("product_id"),
                        "name": li.get("product_name"),
                        "qty": li.get("quantity", 1),
                        "unit_price": float(li.get("price_per_unit", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="meesho",
                    channel_order_id=str(o["order_id"]),
                    status=MEESHO_STATUS_MAP.get(o.get("order_status", ""), "pending"),
                    payment_mode="cod" if o.get("payment_method") == "COD" else "prepaid",
                    customer_name=addr.get("name"),
                    customer_phone=addr.get("phone"),
                    shipping_address=addr,
                    pincode=str(addr.get("pincode", "")),
                    state=addr.get("state"),
                    total_amount=float(o.get("total_amount", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["created_at"])
                    if o.get("created_at") else datetime.now(timezone.utc),
                )

            if len(orders) < 50:
                break
            page += 1
