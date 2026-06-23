"""
Ajio Business Partner API ingestion.
Docs: https://business.ajio.com/api-docs
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

AJIO_BASE = "https://business.ajio.com/api/v1"

AJIO_STATUS_MAP = {
    "PLACED": "confirmed",
    "CONFIRMED": "confirmed",
    "PACKED": "confirmed",
    "READY_FOR_PICKUP": "rtd",
    "PICKED_UP": "dispatched",
    "SHIPPED": "dispatched",
    "OUT_FOR_DELIVERY": "dispatched",
    "DELIVERED": "delivered",
    "CANCELLED": "cancelled",
    "RETURN_INITIATED": "returned",
    "RETURN_COMPLETED": "returned",
    "RTO_INITIATED": "rto",
    "RTO_DELIVERED": "rto",
}


class AjioIngester(BaseIngester):
    channel = "ajio"

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Bearer {s.ajio_api_key}",
            "Content-Type": "application/json",
            "X-Seller-Id": s.ajio_seller_id,
        }

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        s = get_settings()
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%S")
        page = 0
        page_size = 50

        while True:
            try:
                resp = httpx.get(
                    f"{AJIO_BASE}/orders",
                    headers=self._headers(),
                    params={
                        "fromDate": since,
                        "pageNo": page,
                        "pageSize": page_size,
                        "status": "PLACED,CONFIRMED,PACKED,READY_FOR_PICKUP,PICKED_UP,SHIPPED",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[ajio] Failed to fetch orders page {page}: {e}")
                break

            orders = data.get("orders", [])
            if not orders:
                break

            for o in orders:
                addr = o.get("shippingAddress", {})
                payment_mode = "cod" if o.get("paymentMode", "").upper() == "COD" else "prepaid"

                items = []
                for item in o.get("orderItems", []):
                    items.append({
                        "sku": item.get("sellerSku"),
                        "channel_sku_id": item.get("ajioSku"),
                        "name": item.get("productName"),
                        "qty": item.get("quantity", 1),
                        "unit_price": float(item.get("sellingPrice", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="ajio",
                    channel_order_id=o["orderId"],
                    channel_suborder_id=o.get("subOrderId"),
                    status=AJIO_STATUS_MAP.get(o.get("orderStatus", ""), "pending"),
                    payment_mode=payment_mode,
                    customer_name=addr.get("name"),
                    customer_phone=addr.get("mobile"),
                    shipping_address=addr,
                    pincode=addr.get("pincode"),
                    state=addr.get("state"),
                    total_amount=float(o.get("orderAmount", 0)),
                    marketplace_fee=float(o.get("commissionAmount", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["createdAt"].replace("Z", "+00:00"))
                    if o.get("createdAt") else datetime.now(timezone.utc),
                )

            total_pages = data.get("totalPages", 0)
            page += 1
            if page >= total_pages:
                break
