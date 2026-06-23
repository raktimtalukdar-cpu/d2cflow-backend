"""
Snapdeal Seller API ingestion.
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

SNAPDEAL_BASE = "https://seller.snapdeal.com/api"

SNAPDEAL_STATUS_MAP = {
    "NEW": "confirmed",
    "APPROVED": "confirmed",
    "PACKED": "confirmed",
    "DISPATCHED": "dispatched",
    "DELIVERED": "delivered",
    "CANCELLED": "cancelled",
    "RTO_INITIATED": "rto",
    "RTO_DELIVERED": "rto",
    "RETURN_INITIATED": "returned",
    "RETURNED": "returned",
}


class SnapdealIngester(BaseIngester):
    channel = "snapdeal"

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Bearer {s.snapdeal_api_token}",
            "sellerId": s.snapdeal_seller_id,
            "Content-Type": "application/json",
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since_ts = int((datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp() * 1000)
        page_number = 1

        while True:
            try:
                resp = httpx.get(
                    f"{SNAPDEAL_BASE}/orders/list",
                    headers=self._headers(),
                    params={
                        "fromDate": since_ts,
                        "pageNumber": page_number,
                        "pageSize": 50,
                        "subbOrderStatus": "NEW,APPROVED,PACKED,DISPATCHED",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[snapdeal] Failed to fetch page {page_number}: {e}")
                break

            orders = data.get("data", {}).get("orders", [])
            if not orders:
                break

            for o in orders:
                addr = o.get("shippingAddress", {})
                payment_mode = "cod" if o.get("paymentMode", "").upper() == "COD" else "prepaid"

                items = [{
                    "sku": o.get("sellerSkuCode"),
                    "channel_sku_id": o.get("productId"),
                    "name": o.get("productTitle"),
                    "qty": int(o.get("quantity", 1)),
                    "unit_price": float(o.get("orderPrice", 0)),
                    "cost_price": None,
                }]

                yield NormalizedOrder(
                    channel="snapdeal",
                    channel_order_id=o["orderId"],
                    channel_suborder_id=o.get("subOrderId"),
                    status=SNAPDEAL_STATUS_MAP.get(o.get("subbOrderStatus", ""), "pending"),
                    payment_mode=payment_mode,
                    customer_name=addr.get("name"),
                    customer_phone=addr.get("mobile"),
                    shipping_address=addr,
                    pincode=str(addr.get("pincode", "")),
                    state=addr.get("state"),
                    total_amount=float(o.get("orderPrice", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromtimestamp(o["createdOn"] / 1000, tz=timezone.utc)
                    if o.get("createdOn") else datetime.now(timezone.utc),
                )

            total_pages = data.get("data", {}).get("totalPages", 0)
            if page_number >= total_pages:
                break
            page_number += 1
