"""
Listing management engine — push products to marketplace channels,
sync prices, detect deactivated listings, manage SKU/barcode mapping.
"""
import logging
import httpx
from datetime import datetime, timezone
from ..database import get_db
from ..config import get_settings
from ..automation.logger import log_event

logger = logging.getLogger(__name__)


class ListingEngine:

    def run_all(self):
        self.detect_deactivated_listings()
        self.sync_prices_to_channels()
        self.sync_listing_status()

    # ------------------------------------------------------------------ #
    # Detect deactivated listings on marketplaces
    # ------------------------------------------------------------------ #
    def detect_deactivated_listings(self):
        db = get_db()
        listings = (
            db.table("listings")
            .select("id, sku, channel, channel_sku_id, listing_id, is_active")
            .eq("is_active", True)
            .execute()
        )

        for listing in listings.data:
            try:
                active = self._check_listing_active(listing)
                if not active:
                    db.table("listings").update({
                        "is_deactivated_by_channel": True,
                        "last_synced_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", listing["id"]).execute()
                    log_event("listing_deactivated", "sku", listing["sku"], "warning",
                              f"Deactivated on {listing['channel']}")
                    self._alert_deactivated(listing)
            except Exception as e:
                logger.debug(f"Could not check listing {listing['id']}: {e}")

    def _check_listing_active(self, listing: dict) -> bool:
        channel = listing["channel"]
        s = get_settings()

        if channel == "shopify":
            resp = httpx.get(
                f"https://{s.shopify_store_url}/admin/api/2024-01/products/{listing['listing_id']}.json",
                headers={"X-Shopify-Access-Token": s.shopify_access_token},
                timeout=10,
            )
            if resp.status_code == 404:
                return False
            data = resp.json().get("product", {})
            return data.get("status") == "active"

        elif channel == "flipkart":
            from ..ingestion.flipkart import FlipkartIngester
            fi = FlipkartIngester()
            resp = httpx.get(
                f"https://api.flipkart.net/sellers/listings/{listing['channel_sku_id']}",
                headers=fi._headers(),
                timeout=10,
            )
            if resp.status_code == 404:
                return False
            data = resp.json()
            return data.get("active", True)

        return True

    def _alert_deactivated(self, listing: dict):
        from ..notifications.whatsapp import WhatsAppNotifier
        s = get_settings()
        wa = WhatsAppNotifier()
        wa.send_text(
            s.founder_whatsapp,
            f"⚠️ Listing deactivated: SKU {listing['sku']} on {listing['channel']}. "
            f"Check marketplace dashboard to re-activate."
        )

    # ------------------------------------------------------------------ #
    # Push prices to all channels
    # ------------------------------------------------------------------ #
    def sync_prices_to_channels(self):
        db = get_db()
        listings = (
            db.table("listings")
            .select("sku, channel, channel_sku_id, listing_id, channel_price, channel_mrp")
            .eq("is_active", True)
            .eq("is_deactivated_by_channel", False)
            .execute()
        )

        for listing in listings.data:
            # Get latest price from SKU master
            sku_data = db.table("skus").select("selling_price, mrp").eq("sku", listing["sku"]).execute()
            if not sku_data.data:
                continue

            sku = sku_data.data[0]
            if listing.get("channel_price") != sku.get("selling_price"):
                try:
                    self._update_channel_price(listing, sku)
                    db.table("listings").update({
                        "channel_price": sku["selling_price"],
                        "channel_mrp": sku.get("mrp"),
                        "last_synced_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("sku", listing["sku"]).eq("channel", listing["channel"]).execute()
                    log_event("price_synced", "sku", listing["sku"], "success",
                              f"channel={listing['channel']} price={sku['selling_price']}")
                except Exception as e:
                    log_event("price_sync_failed", "sku", listing["sku"], "failed",
                              f"channel={listing['channel']} err={e}")

    def _update_channel_price(self, listing: dict, sku: dict):
        s = get_settings()
        channel = listing["channel"]

        if channel == "shopify":
            httpx.put(
                f"https://{s.shopify_store_url}/admin/api/2024-01/variants/{listing['channel_sku_id']}.json",
                headers={"X-Shopify-Access-Token": s.shopify_access_token},
                json={"variant": {"id": listing["channel_sku_id"], "price": str(sku["selling_price"]),
                                  "compare_at_price": str(sku.get("mrp", ""))}},
                timeout=15,
            ).raise_for_status()

        elif channel == "flipkart":
            from ..ingestion.flipkart import FlipkartIngester
            fi = FlipkartIngester()
            httpx.post(
                "https://api.flipkart.net/sellers/listings/v3/update/price",
                headers=fi._headers(),
                json={"skuId": listing["channel_sku_id"], "mrp": sku.get("mrp"), "sellingPrice": sku["selling_price"]},
                timeout=15,
            ).raise_for_status()

        elif channel == "amazon":
            self._amazon_update_price(listing["channel_sku_id"], sku)

    def _amazon_update_price(self, seller_sku: str, sku: dict):
        from sp_api.api import Feeds
        from sp_api.base import Marketplaces, Credentials
        s = get_settings()
        feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<AmazonEnvelope>
  <Header><DocumentVersion>1.01</DocumentVersion><MerchantIdentifier>{s.amazon_client_id}</MerchantIdentifier></Header>
  <MessageType>Price</MessageType>
  <Message><MessageID>1</MessageID>
    <Price><SKU>{seller_sku}</SKU>
      <StandardPrice currency="INR">{sku['selling_price']}</StandardPrice>
    </Price>
  </Message>
</AmazonEnvelope>"""
        creds = Credentials(refresh_token=s.amazon_refresh_token, lwa_app_id=s.amazon_client_id,
                            lwa_client_secret=s.amazon_client_secret)
        Feeds(credentials=creds, marketplace=Marketplaces.IN).submit_feed(
            feed_type="_POST_PRODUCT_PRICING_DATA_", file=feed.encode(), content_type="text/xml"
        )

    # ------------------------------------------------------------------ #
    # Sync listing status (active/inactive) from marketplace
    # ------------------------------------------------------------------ #
    def sync_listing_status(self):
        db = get_db()
        deactivated = (
            db.table("listings")
            .select("id, sku, channel, channel_sku_id, last_synced_at")
            .eq("is_deactivated_by_channel", True)
            .execute()
        )
        # Re-check if previously deactivated listings are now active
        for listing in deactivated.data:
            try:
                active = self._check_listing_active(listing)
                if active:
                    db.table("listings").update({
                        "is_deactivated_by_channel": False,
                        "last_synced_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", listing["id"]).execute()
                    log_event("listing_reactivated", "sku", listing["sku"], "success",
                              f"Re-activated on {listing['channel']}")
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Create/push a new listing to a channel
    # ------------------------------------------------------------------ #
    def push_listing_to_channel(self, product_id: str, channel: str) -> dict:
        db = get_db()
        s = get_settings()

        product = db.table("products").select("*").eq("id", product_id).single().execute()
        if not product.data:
            raise ValueError(f"Product {product_id} not found")

        p = product.data
        result = {}

        if channel == "shopify":
            result = self._create_shopify_listing(p)
        elif channel == "flipkart":
            result = self._create_flipkart_listing(p)
        else:
            raise ValueError(f"Channel {channel} not yet supported for listing push")

        if result.get("listing_id"):
            db.table("listings").upsert({
                "sku": p["sku"],
                "channel": channel,
                "channel_sku_id": result.get("channel_sku_id"),
                "listing_id": result.get("listing_id"),
                "channel_price": p.get("selling_price"),
                "is_active": True,
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="sku,channel").execute()
            log_event("listing_created", "sku", p["sku"], "success", f"channel={channel}")

        return result

    def _create_shopify_listing(self, product: dict) -> dict:
        s = get_settings()
        payload = {
            "product": {
                "title": product["name"],
                "body_html": product.get("description", ""),
                "vendor": product.get("brand", ""),
                "product_type": product.get("category", ""),
                "tags": ",".join(product.get("tags", [])),
                "variants": [{
                    "sku": product["sku"],
                    "price": str(product.get("selling_price", 0)),
                    "compare_at_price": str(product.get("mrp", "")),
                    "weight": float(product.get("weight_grams", 500)) / 1000,
                    "weight_unit": "kg",
                    "inventory_management": "shopify",
                }],
                "images": [{"src": url} for url in product.get("images", [])[:10]],
                "status": "active",
            }
        }
        resp = httpx.post(
            f"https://{s.shopify_store_url}/admin/api/2024-01/products.json",
            headers={"X-Shopify-Access-Token": s.shopify_access_token},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        p = resp.json()["product"]
        return {
            "listing_id": str(p["id"]),
            "channel_sku_id": str(p["variants"][0]["id"]) if p.get("variants") else "",
        }

    def _create_flipkart_listing(self, product: dict) -> dict:
        from ..ingestion.flipkart import FlipkartIngester
        fi = FlipkartIngester()
        payload = {
            "listing": {
                "sku_id": product["sku"],
                "listing_status": "ACTIVE",
                "selling_price": {"amount": product.get("selling_price", 0), "currency": "INR"},
                "mrp": {"amount": product.get("mrp", product.get("selling_price", 0)), "currency": "INR"},
                "procurement_time": 3,
                "stock_unit": {"unit_id": product["sku"], "quantity": 0},
                "hsn": product.get("hsn_code", ""),
            }
        }
        resp = httpx.post(
            "https://api.flipkart.net/sellers/listings",
            headers=fi._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"listing_id": data.get("fsn", ""), "channel_sku_id": product["sku"]}

    # ------------------------------------------------------------------ #
    # Scheduled Myntra offer file upload
    # ------------------------------------------------------------------ #
    def upload_myntra_offer_file(self, offer_data: list[dict]) -> dict:
        s = get_settings()
        import csv, io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["sku_id", "mrp", "selling_price", "discount_pct", "offer_valid_from", "offer_valid_to"])
        writer.writeheader()
        for row in offer_data:
            writer.writerow(row)

        resp = httpx.post(
            "https://api.myntra.com/seller/v1/offers/upload",
            headers={
                "Authorization": f"Bearer {s.myntra_api_key}",
                "X-Supplier-Id": s.myntra_supplier_id,
            },
            files={"file": ("offers.csv", buf.getvalue().encode(), "text/csv")},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
