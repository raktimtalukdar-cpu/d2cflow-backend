"""
Myntra Seller API ingestion.
API base: https://api.myntra.com/seller/v1
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

MYNTRA_BASE = "https://api.myntra.com/seller/v1"

MYNTRA_STATUS_MAP = {
    "Created": "confirmed",
    "Packing": "confirmed",
    "Packed": "rtd",
    "Pickup": "dispatched",
    "InTransit": "dispatched",
    "Delivered": "delivered",
    "Cancelled": "cancelled",
    "ReturnInitiated": "returned",
    "Returned": "returned",
}


class MyntraIngester(BaseIngester):
    channel = "myntra"
    _token: str | None = None
    _token_expiry: datetime | None = None

    def _get_token(self) -> str:
        if self._token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return self._token
        s = get_settings()
        resp = httpx.post(
            f"{MYNTRA_BASE}/auth/token",
            json={"supplierId": s.myntra_supplier_id, "apiKey": s.myntra_api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("access_token") or data.get("token")
        self._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        since = int((datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp() * 1000)
        page = 0

        while True:
            params = {"fromDate": since, "pageNumber": page, "pageSize": 50}
            resp = httpx.get(f"{MYNTRA_BASE}/orders", headers=self._headers(),
                             params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            orders = data.get("orders", [])
            if not orders:
                break

            for o in orders:
                addr = o.get("deliveryAddress", {})
                items = [{
                    "sku": o.get("skuCode"),
                    "channel_sku_id": o.get("styleId"),
                    "name": o.get("styleDescription"),
                    "qty": 1,
                    "unit_price": float(o.get("sellingPrice", 0)),
                    "cost_price": None,
                }]

                yield NormalizedOrder(
                    channel="myntra",
                    channel_order_id=str(o["orderId"]),
                    status=MYNTRA_STATUS_MAP.get(o.get("orderStatus", ""), "pending"),
                    payment_mode="prepaid",  # Myntra is prepaid only
                    customer_name=addr.get("name"),
                    customer_phone=addr.get("phone"),
                    shipping_address=addr,
                    pincode=str(addr.get("pinCode", "")),
                    state=addr.get("state"),
                    total_amount=float(o.get("sellingPrice", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromtimestamp(o["orderDate"] / 1000, tz=timezone.utc)
                    if o.get("orderDate") else datetime.now(timezone.utc),
                )

            if len(orders) < 50:
                break
            page += 1
