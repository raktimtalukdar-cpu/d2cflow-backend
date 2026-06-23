"""
Blinkit (quick commerce) seller integration.
Handles inventory sync, order ingestion, and stock updates for dark stores.
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from ..ingestion.base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

BLINKIT_BASE = "https://seller.blinkit.com/api/v1"


class BlinkitIngester(BaseIngester):
    channel = "blinkit"

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Bearer {s.blinkit_api_token}",
            "X-Seller-Id": s.blinkit_seller_id,
            "Content-Type": "application/json",
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
        page = 1

        while True:
            try:
                resp = httpx.get(
                    f"{BLINKIT_BASE}/orders",
                    headers=self._headers(),
                    params={"from_time": since, "page": page, "page_size": 50},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[blinkit] Failed to fetch page {page}: {e}")
                break

            orders = data.get("orders", [])
            if not orders:
                break

            for o in orders:
                items = []
                for item in o.get("items", []):
                    items.append({
                        "sku": item.get("seller_sku"),
                        "channel_sku_id": item.get("item_id"),
                        "name": item.get("item_name"),
                        "qty": item.get("quantity", 1),
                        "unit_price": float(item.get("item_price", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="blinkit",
                    channel_order_id=str(o["order_id"]),
                    status="confirmed" if o.get("status") in ("PLACED", "ACCEPTED") else "dispatched",
                    payment_mode="prepaid",
                    customer_name=o.get("customer_name"),
                    customer_phone=o.get("customer_phone"),
                    shipping_address=o.get("delivery_address", {}),
                    pincode=str(o.get("delivery_address", {}).get("pincode", "")),
                    total_amount=float(o.get("order_value", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
                    if o.get("created_at") else datetime.now(timezone.utc),
                )

            if not data.get("has_more"):
                break
            page += 1

    def update_inventory(self, sku: str, store_id: str, qty: int):
        resp = httpx.post(
            f"{BLINKIT_BASE}/inventory/update",
            headers=self._headers(),
            json={"seller_sku": sku, "store_id": store_id, "quantity": qty},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_stores(self) -> list:
        resp = httpx.get(
            f"{BLINKIT_BASE}/stores",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("stores", [])
