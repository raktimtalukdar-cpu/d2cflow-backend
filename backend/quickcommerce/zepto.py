"""
Zepto seller integration.
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from ..ingestion.base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

ZEPTO_BASE = "https://seller.zeptonow.com/api/v1"


class ZeptoIngester(BaseIngester):
    channel = "zepto"

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Bearer {s.zepto_api_token}",
            "X-Seller-Code": s.zepto_seller_code,
            "Content-Type": "application/json",
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
        cursor = None

        while True:
            try:
                params = {"from_timestamp": since, "limit": 50}
                if cursor:
                    params["cursor"] = cursor
                resp = httpx.get(
                    f"{ZEPTO_BASE}/orders",
                    headers=self._headers(),
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[zepto] Failed to fetch orders: {e}")
                break

            orders = data.get("orders", [])
            if not orders:
                break

            for o in orders:
                items = []
                for item in o.get("items", []):
                    items.append({
                        "sku": item.get("seller_sku"),
                        "channel_sku_id": item.get("zepto_item_id"),
                        "name": item.get("item_name"),
                        "qty": item.get("ordered_quantity", 1),
                        "unit_price": float(item.get("mrp", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="zepto",
                    channel_order_id=str(o["order_id"]),
                    status="confirmed",
                    payment_mode="prepaid",
                    customer_name=o.get("address", {}).get("name"),
                    customer_phone=o.get("address", {}).get("phone"),
                    shipping_address=o.get("address", {}),
                    pincode=str(o.get("address", {}).get("pincode", "")),
                    total_amount=float(o.get("order_amount", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
                    if o.get("created_at") else datetime.now(timezone.utc),
                )

            cursor = data.get("next_cursor")
            if not cursor:
                break
