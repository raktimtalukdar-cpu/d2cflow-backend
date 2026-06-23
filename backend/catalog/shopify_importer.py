"""
Import all products from Shopify into the PIM (products + skus + listings tables).
Pulls product title, description, images, variants (SKU, price, weight, barcode),
and creates a listings record mapping each variant to the Shopify channel.
"""
import httpx
import logging
from datetime import datetime, timezone

from ..database import get_db
from ..config import get_settings
from ..automation.logger import log_event

logger = logging.getLogger(__name__)


class ShopifyCatalogImporter:

    def __init__(self, creds: dict | None = None):
        if creds:
            self._token = creds.get("access_token", "")
            self._store = creds.get("shop_domain", "")
        else:
            s = get_settings()
            self._token = s.shopify_access_token
            self._store = s.shopify_store_url

    def _headers(self):
        return {"X-Shopify-Access-Token": self._token}

    def _base(self):
        return f"https://{self._store}/admin/api/2024-01"

    def import_all(self) -> dict:
        """
        Pull every product from Shopify and upsert into products + skus + listings.
        Returns counts of created/updated/errors.
        """
        db = get_db()
        created, updated, errors = 0, 0, 0
        page_info = None

        while True:
            params = {"limit": 250, "fields": "id,title,body_html,vendor,product_type,tags,status,images,variants"}
            if page_info:
                params = {"limit": 250, "page_info": page_info}

            try:
                resp = httpx.get(
                    f"{self._base()}/products.json",
                    headers=self._headers(),
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[shopify_import] Failed to fetch products: {e}")
                errors += 1
                break

            products = resp.json().get("products", [])
            if not products:
                break

            for p in products:
                try:
                    result = self._upsert_product(db, p)
                    if result == "created":
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    logger.error(f"[shopify_import] Failed to upsert product {p.get('id')}: {e}")
                    errors += 1

            # Shopify cursor-based pagination via Link header
            link_header = resp.headers.get("Link", "")
            page_info = self._parse_next_page(link_header)
            if not page_info:
                break

        log_event("catalog_import", "system", "shopify", "success",
                  f"created={created} updated={updated} errors={errors}")
        return {"channel": "shopify", "created": created, "updated": updated, "errors": errors}

    def _upsert_product(self, db, p: dict) -> str:
        # Collect images
        images = [img["src"] for img in p.get("images", [])]

        # Tags as list
        tags = [t.strip() for t in p.get("tags", "").split(",") if t.strip()]

        product_payload = {
            "shopify_product_id": str(p["id"]),
            "name": p.get("title", ""),
            "description": p.get("body_html", ""),
            "brand": p.get("vendor", ""),
            "category": p.get("product_type", ""),
            "images": images,
            "tags": tags,
            "is_active": p.get("status") == "active",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Check if product exists by shopify_product_id
        existing = db.table("products").select("id").eq("shopify_product_id", str(p["id"])).execute()

        if existing.data:
            product_id = existing.data[0]["id"]
            db.table("products").update(product_payload).eq("id", product_id).execute()
            action = "updated"
        else:
            result = db.table("products").insert(product_payload).execute()
            product_id = result.data[0]["id"]
            action = "created"

        # Upsert each variant as a SKU
        for v in p.get("variants", []):
            sku_code = v.get("sku") or f"SHOPIFY-{v['id']}"
            sku_payload = {
                "sku": sku_code,
                "product_id": product_id,
                "barcode": v.get("barcode"),
                "weight_grams": float(v.get("grams", 500)),
                "mrp": float(v.get("compare_at_price") or v.get("price") or 0),
                "selling_price": float(v.get("price") or 0),
                "shopify_variant_id": str(v["id"]),
                "shopify_inventory_item_id": str(v.get("inventory_item_id", "")),
                "color": self._option_value(v, p, "Color"),
                "size": self._option_value(v, p, "Size"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            db.table("skus").upsert(sku_payload, on_conflict="sku").execute()

            # Create/update listing record
            db.table("listings").upsert({
                "sku": sku_code,
                "channel": "shopify",
                "channel_sku_id": str(v.get("inventory_item_id", "")),
                "listing_id": str(p["id"]),
                "channel_price": float(v.get("price") or 0),
                "channel_mrp": float(v.get("compare_at_price") or v.get("price") or 0),
                "is_active": p.get("status") == "active",
                "is_deactivated_by_channel": p.get("status") != "active",
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="sku,channel").execute()

        return action

    def _option_value(self, variant: dict, product: dict, option_name: str) -> str | None:
        options = product.get("options", [])
        for i, opt in enumerate(options):
            if opt.get("name", "").lower() == option_name.lower():
                return variant.get(f"option{i + 1}")
        return None

    def _parse_next_page(self, link_header: str) -> str | None:
        """Extract page_info cursor for the next page from Shopify's Link header."""
        if 'rel="next"' not in link_header:
            return None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                for param in url.split("?")[-1].split("&"):
                    if param.startswith("page_info="):
                        return param.split("=", 1)[1]
        return None
