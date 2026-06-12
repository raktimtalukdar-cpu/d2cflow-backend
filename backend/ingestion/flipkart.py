"""
Flipkart Seller Hub API ingestion.
Docs: https://seller.flipkart.com/api-docs/order-api-docs/
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

FLIPKART_BASE = "https://api.flipkart.net/sellers"

FLIPKART_STATUS_MAP = {
    "APPROVED": "confirmed",
    "PACKED": "confirmed",
    "READY_TO_DISPATCH": "rtd",
    "PICKUP_COMPLETE": "dispatched",
    "SHIPPED": "dispatched",
    "DELIVERED": "delivered",
    "CANCELLED": "cancelled",
    "RETURN_REQUESTED": "returned",
    "RETURNED": "returned",
}


class FlipkartIngester(BaseIngester):
    channel = "flipkart"
    _token: str | None = None
    _token_expiry: datetime | None = None

    def _get_token(self) -> str:
        if self._token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return self._token
        s = get_settings()
        resp = httpx.post(
            "https://api.flipkart.net/oauth-service/oauth/token",
            params={"grant_type": "client_credentials", "scope": "Seller_Api"},
            auth=(s.flipkart_client_id, s.flipkart_client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"] - 60)
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%S")
        params = {
            "orderState": "APPROVED,PACKED,READY_TO_DISPATCH,PICKUP_COMPLETE,SHIPPED",
            "modifiedDateFrom": since,
            "pageSize": 20,
        }
        page_token = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            resp = httpx.get(f"{FLIPKART_BASE}/orders/list", headers=self._headers(),
                             params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for o in data.get("orderItems", []):
                addr = o.get("shippingAddress", {})
                payment_mode = "cod" if o.get("paymentType") == "COD" else "prepaid"

                items = [{
                    "sku": o.get("sellerSKU"),
                    "channel_sku_id": o.get("FSN"),
                    "name": o.get("productTitle"),
                    "qty": 1,
                    "unit_price": float(o.get("sellingPrice", {}).get("amount", 0)),
                    "cost_price": None,
                }]

                yield NormalizedOrder(
                    channel="flipkart",
                    channel_order_id=o["orderId"],
                    channel_suborder_id=o.get("orderItemId"),
                    status=FLIPKART_STATUS_MAP.get(o.get("orderState", ""), "pending"),
                    payment_mode=payment_mode,
                    customer_name=addr.get("name"),
                    customer_phone=addr.get("phone"),
                    shipping_address=addr,
                    pincode=addr.get("pinCode"),
                    state=addr.get("state"),
                    total_amount=float(o.get("sellingPrice", {}).get("amount", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["createdOn"].replace("Z", "+00:00"))
                    if o.get("createdOn") else datetime.now(timezone.utc),
                )

            page_token = data.get("nextPageToken")
            if not page_token:
                break
