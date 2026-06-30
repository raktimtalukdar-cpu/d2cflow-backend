"""
Meta Catalog Importer — pulls products from Meta Commerce Manager into our PIM.

Flow:
  1. Get all catalogs owned by the merchant's business
  2. For each catalog, fetch all products (paginated)
  3. Upsert into products + skus + listings tables
  4. Store catalog_id in channel_credentials for future product message sends
"""
import httpx
import logging
from datetime import datetime, timezone
from ..database import get_db
from ..automation.logger import log_event

logger = logging.getLogger(__name__)
META_BASE = "https://graph.facebook.com/v19.0"


class MetaCatalogImporter:

    def __init__(self, access_token: str, business_id: str = None):
        self._token = access_token
        self._business_id = business_id

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------------ #
    # Discover catalogs
    # ------------------------------------------------------------------ #
    def get_catalogs(self) -> list[dict]:
        """Return all product catalogs owned by this business."""
        if not self._business_id:
            # Fetch from token's associated business
            resp = httpx.get(
                f"{META_BASE}/me/businesses",
                headers=self._headers(),
                params={"fields": "id,name"},
                timeout=15,
            )
            resp.raise_for_status()
            businesses = resp.json().get("data", [])
            if not businesses:
                return []
            self._business_id = businesses[0]["id"]

        resp = httpx.get(
            f"{META_BASE}/{self._business_id}/owned_product_catalogs",
            headers=self._headers(),
            params={"fields": "id,name,product_count"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    # ------------------------------------------------------------------ #
    # Import products from a catalog
    # ------------------------------------------------------------------ #
    def import_catalog(self, catalog_id: str) -> dict:
        db = get_db()
        created, updated, errors = 0, 0, 0
        cursor = None

        while True:
            params = {
                "fields": "id,retailer_id,name,description,price,currency,availability,"
                          "image_url,additional_image_urls,category,brand,url,"
                          "sale_price,condition,custom_label_0",
                "limit": 100,
            }
            if cursor:
                params["after"] = cursor

            try:
                resp = httpx.get(
                    f"{META_BASE}/{catalog_id}/products",
                    headers=self._headers(),
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[meta_catalog] Failed to fetch products: {e}")
                errors += 1
                break

            for item in data.get("data", []):
                try:
                    r = self._upsert_product(db, item, catalog_id)
                    if r == "created":
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    logger.error(f"[meta_catalog] Failed on item {item.get('id')}: {e}")
                    errors += 1

            paging = data.get("paging", {})
            cursor = paging.get("cursors", {}).get("after")
            if not cursor or not data.get("data"):
                break

        log_event("catalog_import", "system", f"meta:{catalog_id}", "success",
                  f"created={created} updated={updated} errors={errors}")
        return {"channel": "meta", "catalog_id": catalog_id,
                "created": created, "updated": updated, "errors": errors}

    def _upsert_product(self, db, item: dict, catalog_id: str) -> str:
        sku = item.get("retailer_id") or f"META-{item['id']}"
        name = item.get("name", sku)
        # Price comes as "1299 INR" or integer in cents — normalise
        price_raw = item.get("price", "0")
        try:
            if isinstance(price_raw, str) and " " in price_raw:
                price = float(price_raw.split()[0]) / 100
            else:
                price = float(price_raw) / 100
        except Exception:
            price = 0.0

        sale_price_raw = item.get("sale_price")
        selling_price = price
        if sale_price_raw:
            try:
                selling_price = float(str(sale_price_raw).split()[0]) / 100
            except Exception:
                pass

        images = [item["image_url"]] if item.get("image_url") else []
        images += item.get("additional_image_urls", [])

        product_payload = {
            "name": name,
            "description": item.get("description", ""),
            "brand": item.get("brand", ""),
            "category": item.get("category", ""),
            "images": images,
            "is_active": item.get("availability") == "in stock",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        existing = db.table("products").select("id").ilike("name", name).limit(1).execute()
        if existing.data:
            product_id = existing.data[0]["id"]
            db.table("products").update(product_payload).eq("id", product_id).execute()
            action = "updated"
        else:
            result = db.table("products").insert(product_payload).execute()
            product_id = result.data[0]["id"]
            action = "created"

        # Upsert SKU
        db.table("skus").upsert({
            "sku": sku,
            "product_id": product_id,
            "selling_price": selling_price,
            "mrp": price,
            "name": name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="sku").execute()

        # Upsert listing — store Meta catalog product ID for product messages
        db.table("listings").upsert({
            "sku": sku,
            "channel": "meta",
            "channel_sku_id": item["id"],        # Meta's internal product ID
            "listing_id": catalog_id,
            "channel_price": selling_price,
            "channel_mrp": price,
            "is_active": item.get("availability") == "in stock",
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="sku,channel").execute()

        return action

    # ------------------------------------------------------------------ #
    # Import all catalogs in one shot
    # ------------------------------------------------------------------ #
    def import_all(self) -> dict:
        catalogs = self.get_catalogs()
        if not catalogs:
            return {"error": "No catalogs found. Create a catalog in Meta Commerce Manager first."}
        results = {}
        for cat in catalogs:
            results[cat["name"]] = self.import_catalog(cat["id"])
        return {"catalogs_imported": len(catalogs), "results": results}
