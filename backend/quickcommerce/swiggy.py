"""
Swiggy Instamart seller integration.
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from ..ingestion.base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

SWIGGY_BASE = "https://partner.swiggy.com/api/v1"


class SwiggyIngester(BaseIngester):
    channel = "swiggy"

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Bearer {s.swiggy_api_token}",
            "Content-Type": "application/json",
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = int((datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp())
        page = 0

        while True:
            try:
                resp = httpx.get(
                    f"{SWIGGY_BASE}/orders",
                    headers=self._headers(),
                    params={"from_time": since, "offset": page * 50, "limit": 50},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[swiggy] Failed to fetch page {page}: {e}")
                break

            orders = data.get("data", {}).get("orders", [])
            if not orders:
                break

            for o in orders:
                items = []
                for item in o.get("order_items", []):
                    items.append({
                        "sku": item.get("external_item_id"),
                        "channel_sku_id": item.get("item_id"),
                        "name": item.get("name"),
                        "qty": item.get("quantity", 1),
                        "unit_price": float(item.get("price", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="swiggy",
                    channel_order_id=str(o["order_id"]),
                    status="confirmed",
                    payment_mode="prepaid",
                    customer_name=o.get("delivery_address", {}).get("name"),
                    customer_phone=o.get("delivery_address", {}).get("mobile"),
                    shipping_address=o.get("delivery_address", {}),
                    pincode=str(o.get("delivery_address", {}).get("pincode", "")),
                    total_amount=float(o.get("order_total", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromtimestamp(o.get("order_time", 0), tz=timezone.utc),
                )

            if len(orders) < 50:
                break
            page += 1
