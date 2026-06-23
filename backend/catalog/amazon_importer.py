"""
Import active listings from Amazon SP-API into the PIM.
Uses Listings Items API + Catalog Items API for product details.
"""
import httpx
import logging
from datetime import datetime, timezone

from ..database import get_db
from ..config import get_settings
from ..automation.logger import log_event

logger = logging.getLogger(__name__)


class AmazonCatalogImporter:

    def __init__(self, creds: dict | None = None):
        if creds:
            self._refresh_token = creds.get("refresh_token", "")
            self._seller_id = creds.get("seller_id", "")
        else:
            s = get_settings()
            self._refresh_token = s.amazon_refresh_token
            self._seller_id = s.amazon_client_id

    def _get_sp_client(self, api_class, **kwargs):
        from sp_api.base import Marketplaces, Credentials
        s = get_settings()
        creds = Credentials(
            refresh_token=self._refresh_token,
            lwa_app_id=s.amazon_client_id,
            lwa_client_secret=s.amazon_client_secret,
        )
        return api_class(credentials=creds, marketplace=Marketplaces.IN, **kwargs)

    def import_all(self) -> dict:
        """Pull all active seller listings from Amazon and upsert into PIM."""
        db = get_db()
        created, updated, errors = 0, 0, 0

        try:
            from sp_api.api import Listings, CatalogItems
            listings_client = self._get_sp_client(Listings)
            s = get_settings()

            # Fetch all active listings using the Listings Items API
            next_token = None
            while True:
                kwargs = {"sellerId": s.amazon_client_id, "marketplaceIds": [s.amazon_marketplace_id]}
                if next_token:
                    kwargs["pageToken"] = next_token

                resp = listings_client.get_listings_items(**kwargs)
                items = (resp.payload or {}).get("items", [])

                for item in items:
                    try:
                        seller_sku = item.get("sellerSku", "")
                        asin = item.get("asin", "")
                        summaries = item.get("summaries", [{}])[0]
                        attributes = item.get("attributes", {})

                        name = summaries.get("itemName", seller_sku)
                        price = float((attributes.get("purchasable_offer", [{}])[0]
                                       .get("our_price", [{}])[0]
                                       .get("schedule", [{}])[0]
                                       .get("value_with_tax", 0)) or 0)
                        images = [
                            img.get("link", "") for img in
                            attributes.get("main_product_image_locator", [])
                        ]

                        product_payload = {
                            "name": name,
                            "brand": summaries.get("brandName", ""),
                            "category": summaries.get("productType", ""),
                            "images": [i for i in images if i],
                            "is_active": summaries.get("status") == "BUYABLE",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }

                        existing = db.table("products").select("id").eq("name", name).execute()
                        if existing.data:
                            product_id = existing.data[0]["id"]
                            db.table("products").update(product_payload).eq("id", product_id).execute()
                            updated += 1
                        else:
                            result = db.table("products").insert(product_payload).execute()
                            product_id = result.data[0]["id"]
                            created += 1

                        # Upsert SKU
                        db.table("skus").upsert({
                            "sku": seller_sku,
                            "product_id": product_id,
                            "selling_price": price,
                            "amazon_asin": asin,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }, on_conflict="sku").execute()

                        # Upsert listing
                        db.table("listings").upsert({
                            "sku": seller_sku,
                            "channel": "amazon",
                            "channel_sku_id": seller_sku,
                            "listing_id": asin,
                            "channel_price": price,
                            "is_active": summaries.get("status") == "BUYABLE",
                            "last_synced_at": datetime.now(timezone.utc).isoformat(),
                        }, on_conflict="sku,channel").execute()

                    except Exception as e:
                        logger.error(f"[amazon_import] Failed on SKU {item.get('sellerSku')}: {e}")
                        errors += 1

                next_token = (resp.payload or {}).get("nextPageToken")
                if not next_token:
                    break

        except Exception as e:
            logger.error(f"[amazon_import] SP-API call failed: {e}")
            errors += 1

        log_event("catalog_import", "system", "amazon", "success",
                  f"created={created} updated={updated} errors={errors}")
        return {"channel": "amazon", "created": created, "updated": updated, "errors": errors}
