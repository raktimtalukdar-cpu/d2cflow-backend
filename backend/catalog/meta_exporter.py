"""
Meta Catalog Exporter — push products from our PIM to Meta Commerce Manager.
Uses the items_batch API for bulk upserts.
Docs: https://developers.facebook.com/docs/marketing-api/catalog/reference
"""
import httpx
import logging
from datetime import datetime, timezone
from ..database import get_db
from ..automation.logger import log_event

logger = logging.getLogger(__name__)
META_BASE = "https://graph.facebook.com/v19.0"


class MetaCatalogExporter:

    def __init__(self, access_token: str, catalog_id: str):
        self._token = access_token
        self._catalog_id = catalog_id

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _price_to_meta(self, price: float, currency: str = "INR") -> str:
        """Meta expects price as '1299 INR' (whole units)."""
        return f"{int(price * 100)} {currency}"

    def export_all(self, app_base_url: str = "https://d2cflow.app") -> dict:
        """Push all active SKUs from our PIM to Meta Catalog in batches of 50."""
        db = get_db()
        skus = db.table("skus").select(
            "sku, name, selling_price, mrp, weight_grams, skus_id:id, "
            "products(name, description, images, category, brand, is_active)"
        ).execute().data

        active = [s for s in skus if (s.get("products") or {}).get("is_active", True)]
        batches = [active[i:i + 50] for i in range(0, len(active), 50)]

        total_pushed, errors = 0, 0
        for batch in batches:
            requests = []
            for sku in batch:
                product = sku.get("products") or {}
                images = product.get("images") or []
                price = float(sku.get("selling_price") or sku.get("mrp") or 0)
                mrp = float(sku.get("mrp") or price)

                if price <= 0:
                    continue

                item = {
                    "retailer_id": sku["sku"],
                    "availability": "in stock",
                    "condition": "new",
                    "name": sku.get("name") or product.get("name", sku["sku"]),
                    "description": (product.get("description") or "")[:200] or sku.get("name", ""),
                    "price": self._price_to_meta(price),
                    "currency": "INR",
                    "url": f"{app_base_url}/p/{sku.get('skus_id', sku['sku'])}",
                    "brand": product.get("brand", ""),
                    "category": product.get("category", ""),
                }
                if images:
                    item["image_url"] = images[0]
                    if len(images) > 1:
                        item["additional_image_urls"] = images[1:5]
                if mrp > price:
                    item["sale_price"] = self._price_to_meta(price)
                    item["price"] = self._price_to_meta(mrp)

                requests.append({"method": "UPDATE", "retailer_id": sku["sku"], "data": item})

            if not requests:
                continue

            try:
                resp = httpx.post(
                    f"{META_BASE}/{self._catalog_id}/items_batch",
                    headers=self._headers(),
                    json={"item_type": "PRODUCT_ITEM", "requests": requests},
                    timeout=60,
                )
                resp.raise_for_status()
                total_pushed += len(requests)
            except Exception as e:
                logger.error(f"[meta_export] Batch failed: {e}")
                errors += len(requests)

        log_event("catalog_export", "system", f"meta:{self._catalog_id}", "success",
                  f"pushed={total_pushed} errors={errors}")
        return {"pushed": total_pushed, "errors": errors, "catalog_id": self._catalog_id}

    def delete_product(self, retailer_id: str) -> bool:
        try:
            resp = httpx.post(
                f"{META_BASE}/{self._catalog_id}/items_batch",
                headers=self._headers(),
                json={"item_type": "PRODUCT_ITEM",
                      "requests": [{"method": "DELETE", "retailer_id": retailer_id}]},
                timeout=20,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[meta_export] Delete failed for {retailer_id}: {e}")
            return False
