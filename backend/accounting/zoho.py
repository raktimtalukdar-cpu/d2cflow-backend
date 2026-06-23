"""
Zoho Books integration — sync orders as invoices and track GST.
"""
import httpx
import logging
from datetime import datetime, timezone
from ..config import get_settings
from ..database import get_db
from ..automation.logger import log_event

logger = logging.getLogger(__name__)

ZOHO_BASE = "https://www.zohoapis.in/books/v3"


class ZohoBooks:

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Zoho-oauthtoken {s.zoho_access_token}",
            "Content-Type": "application/json",
        }

    def _params(self):
        s = get_settings()
        return {"organization_id": s.zoho_organization_id}

    def create_invoice_from_order(self, order: dict) -> dict:
        s = get_settings()
        line_items = []
        for item in order.get("order_items", []):
            line_items.append({
                "item_id": item.get("zoho_item_id", ""),
                "name": item.get("name", item.get("sku", "")),
                "description": f"SKU: {item.get('sku', '')}",
                "rate": float(item.get("unit_price", 0)),
                "quantity": item.get("qty", 1),
            })

        invoice_payload = {
            "customer_name": order.get("customer_name", ""),
            "customer_email": order.get("customer_email", ""),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "due_date": datetime.now().strftime("%Y-%m-%d"),
            "reference_number": order.get("channel_order_id", ""),
            "line_items": line_items,
            "billing_address": {
                "address": order.get("shipping_address", {}).get("address1", ""),
                "city": order.get("shipping_address", {}).get("city", ""),
                "state": order.get("state", ""),
                "zip": order.get("pincode", ""),
                "country": "India",
                "phone": order.get("customer_phone", ""),
            },
            "notes": f"Channel: {order.get('channel', '')} | Order: {order.get('channel_order_id', '')}",
        }

        resp = httpx.post(
            f"{ZOHO_BASE}/invoices",
            headers=self._headers(),
            params=self._params(),
            json={"JSONString": str(invoice_payload)},
            timeout=30,
        )
        resp.raise_for_status()
        invoice = resp.json().get("invoice", {})
        log_event("zoho_invoice_created", "order", order.get("channel_order_id", ""), "success",
                  f"Invoice ID: {invoice.get('invoice_id')}")
        return invoice

    def sync_items_to_zoho(self, skus: list[dict]) -> list:
        created = []
        for sku in skus:
            try:
                existing = self._find_zoho_item(sku["sku"])
                if existing:
                    continue
                resp = httpx.post(
                    f"{ZOHO_BASE}/items",
                    headers=self._headers(),
                    params=self._params(),
                    json={"JSONString": str({
                        "name": sku.get("name", sku["sku"]),
                        "sku": sku["sku"],
                        "rate": float(sku.get("selling_price", 0)),
                        "purchase_rate": float(sku.get("cost_price", 0)),
                        "tax_percentage": float(sku.get("gst_rate", 18)),
                        "hsn_or_sac": sku.get("hsn_code", ""),
                        "unit": "pcs",
                    })},
                    timeout=20,
                )
                resp.raise_for_status()
                item = resp.json().get("item", {})
                # Store zoho_item_id back in SKU record
                db = get_db()
                db.table("skus").update({"zoho_item_id": item.get("item_id")}).eq("sku", sku["sku"]).execute()
                created.append(item)
            except Exception as e:
                logger.error(f"Failed to sync SKU {sku['sku']} to Zoho: {e}")
        return created

    def _find_zoho_item(self, sku: str) -> dict:
        resp = httpx.get(
            f"{ZOHO_BASE}/items",
            headers=self._headers(),
            params={**self._params(), "search_text": sku},
            timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            return next((i for i in items if i.get("sku") == sku), None)
        return None

    def get_invoice_list(self, limit: int = 50) -> list:
        resp = httpx.get(
            f"{ZOHO_BASE}/invoices",
            headers=self._headers(),
            params={**self._params(), "per_page": limit, "sort_column": "date", "sort_order": "D"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("invoices", [])
