"""
Amazon SP-API ingestion.
Uses sp-api-python library (pip install python-amazon-sp-api).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings

logger = logging.getLogger(__name__)

AMAZON_STATUS_MAP = {
    "Pending": "pending",
    "Unshipped": "confirmed",
    "PartiallyShipped": "confirmed",
    "Shipped": "dispatched",
    "Canceled": "cancelled",
    "Unfulfillable": "cancelled",
}


class AmazonIngester(BaseIngester):
    channel = "amazon"

    def _get_client(self):
        from sp_api.api import Orders
        from sp_api.base import Marketplaces, Credentials
        s = get_settings()
        credentials = Credentials(
            refresh_token=s.amazon_refresh_token,
            lwa_app_id=s.amazon_client_id,
            lwa_client_secret=s.amazon_client_secret,
        )
        return Orders(credentials=credentials, marketplace=Marketplaces.IN)

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        client = self._get_client()
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        next_token = None
        while True:
            if next_token:
                res = client.get_orders(NextToken=next_token)
            else:
                res = client.get_orders(
                    CreatedAfter=since,
                    MarketplaceIds=[get_settings().amazon_marketplace_id],
                )

            for o in res.payload.get("Orders", []):
                order_id = o["AmazonOrderId"]

                # Fetch line items
                items_res = client.get_order_items(order_id=order_id)
                items = []
                for li in items_res.payload.get("OrderItems", []):
                    items.append({
                        "sku": li.get("SellerSKU"),
                        "channel_sku_id": li.get("ASIN"),
                        "name": li.get("Title"),
                        "qty": int(li.get("QuantityOrdered", 1)),
                        "unit_price": float(li.get("ItemPrice", {}).get("Amount", 0)),
                        "cost_price": None,
                    })

                addr = o.get("ShippingAddress", {})
                payment_mode = "cod" if o.get("PaymentMethod") == "COD" else "prepaid"

                yield NormalizedOrder(
                    channel="amazon",
                    channel_order_id=order_id,
                    status=AMAZON_STATUS_MAP.get(o.get("OrderStatus", ""), "pending"),
                    payment_mode=payment_mode,
                    customer_name=addr.get("Name"),
                    customer_phone=addr.get("Phone"),
                    shipping_address=addr,
                    pincode=addr.get("PostalCode"),
                    state=addr.get("StateOrRegion"),
                    total_amount=float(o.get("OrderTotal", {}).get("Amount", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["PurchaseDate"].replace("Z", "+00:00")),
                )

            next_token = res.payload.get("NextToken")
            if not next_token:
                break
