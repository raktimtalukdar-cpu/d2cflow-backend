import httpx
from datetime import datetime, timedelta, timezone
from typing import Generator
from .base import BaseIngester
from ..models.order import NormalizedOrder
from ..config import get_settings
import logging

logger = logging.getLogger(__name__)

SHOPIFY_STATUS_MAP = {
    "pending": "pending",
    "authorized": "confirmed",
    "partially_paid": "confirmed",
    "paid": "confirmed",
    "partially_refunded": "returned",
    "refunded": "returned",
    "voided": "cancelled",
}


class ShopifyIngester(BaseIngester):
    channel = "shopify"

    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        s = get_settings()
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
        url = f"https://{s.shopify_store_url}/admin/api/2024-01/orders.json"
        headers = {"X-Shopify-Access-Token": s.shopify_access_token}
        params = {"status": "any", "updated_at_min": since, "limit": 250}

        while url:
            resp = httpx.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for o in data.get("orders", []):
                address = o.get("shipping_address") or o.get("billing_address") or {}
                pincode = address.get("zip", "")
                state = address.get("province", "")

                payment_mode = "prepaid"
                for gateway in (o.get("payment_gateway_names") or []):
                    if "cod" in gateway.lower() or "cash" in gateway.lower():
                        payment_mode = "cod"
                        break

                items = []
                for li in o.get("line_items", []):
                    items.append({
                        "sku": li.get("sku"),
                        "channel_sku_id": li.get("variant_id"),
                        "name": li.get("name"),
                        "qty": li.get("quantity", 1),
                        "unit_price": float(li.get("price", 0)),
                        "cost_price": None,
                    })

                yield NormalizedOrder(
                    channel="shopify",
                    channel_order_id=str(o["id"]),
                    status=SHOPIFY_STATUS_MAP.get(o.get("financial_status", ""), "pending"),
                    payment_mode=payment_mode,
                    customer_name=f"{o.get('customer', {}).get('first_name', '')} {o.get('customer', {}).get('last_name', '')}".strip(),
                    customer_phone=address.get("phone") or o.get("customer", {}).get("phone"),
                    customer_email=o.get("email"),
                    shipping_address=address,
                    pincode=pincode,
                    state=state,
                    total_amount=float(o.get("total_price", 0)),
                    shipping_charge=float(o.get("total_shipping_price_set", {}).get("shop_money", {}).get("amount", 0)),
                    items=items,
                    raw_payload=o,
                    created_at=datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")),
                )

            # Pagination via Link header
            link = resp.headers.get("Link", "")
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
            url = next_url
            params = {}
