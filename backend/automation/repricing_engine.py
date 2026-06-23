"""
Repricing engine — track competitor prices and auto-adjust to stay competitive.
Supports minimum price floor and maximum markup cap.
"""
import logging
import httpx
from datetime import datetime, timezone
from ..database import get_db
from ..config import get_settings
from ..automation.logger import log_event

logger = logging.getLogger(__name__)


class RepricingEngine:

    def run_all(self):
        self.fetch_competitor_prices()
        self.apply_repricing_rules()

    # ------------------------------------------------------------------ #
    # Fetch competitor prices from marketplaces
    # ------------------------------------------------------------------ #
    def fetch_competitor_prices(self):
        db = get_db()
        listings = (
            db.table("listings")
            .select("sku, channel, channel_sku_id, listing_id")
            .eq("is_active", True)
            .execute()
        )

        for listing in listings.data:
            try:
                price_data = self._fetch_channel_price(listing)
                if price_data:
                    db.table("competitor_prices").upsert({
                        "sku": listing["sku"],
                        "channel": listing["channel"],
                        "min_competitor_price": price_data.get("min_price"),
                        "max_competitor_price": price_data.get("max_price"),
                        "our_price": price_data.get("our_price"),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }, on_conflict="sku,channel").execute()
            except Exception as e:
                logger.debug(f"Could not fetch competitor price for {listing['sku']} on {listing['channel']}: {e}")

    def _fetch_channel_price(self, listing: dict) -> dict:
        channel = listing["channel"]
        s = get_settings()

        if channel == "amazon":
            return self._amazon_competitive_price(listing["channel_sku_id"])
        elif channel == "flipkart":
            return self._flipkart_competitive_price(listing["channel_sku_id"])
        return {}

    def _amazon_competitive_price(self, asin: str) -> dict:
        try:
            from sp_api.api import Products
            from sp_api.base import Marketplaces, Credentials
            s = get_settings()
            creds = Credentials(
                refresh_token=s.amazon_refresh_token,
                lwa_app_id=s.amazon_client_id,
                lwa_client_secret=s.amazon_client_secret,
            )
            client = Products(credentials=creds, marketplace=Marketplaces.IN)
            resp = client.get_competitive_pricing_for_asins(asins=[asin])
            items = resp.payload or []
            prices = []
            for item in items:
                competitive = item.get("Product", {}).get("CompetitivePricing", {})
                for cp in competitive.get("CompetitivePrices", []):
                    p = cp.get("Price", {}).get("LandedPrice", {}).get("Amount", 0)
                    if p:
                        prices.append(float(p))
            if prices:
                return {"min_price": min(prices), "max_price": max(prices), "our_price": None}
        except Exception as e:
            logger.debug(f"Amazon competitive price error for {asin}: {e}")
        return {}

    def _flipkart_competitive_price(self, fsn: str) -> dict:
        try:
            from ..ingestion.flipkart import FlipkartIngester
            fi = FlipkartIngester()
            resp = httpx.get(
                f"https://api.flipkart.net/sellers/listings/{fsn}/competitive-price",
                headers=fi._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "min_price": float(data.get("minimumPrice", {}).get("amount", 0)),
                    "max_price": float(data.get("maximumPrice", {}).get("amount", 0)),
                    "our_price": float(data.get("yourPrice", {}).get("amount", 0)),
                }
        except Exception as e:
            logger.debug(f"Flipkart competitive price error for {fsn}: {e}")
        return {}

    # ------------------------------------------------------------------ #
    # Apply repricing rules
    # ------------------------------------------------------------------ #
    def apply_repricing_rules(self):
        db = get_db()
        rules = db.table("repricing_rules").select("*").eq("is_active", True).execute()

        for rule in rules.data:
            try:
                self._apply_rule(rule)
            except Exception as e:
                log_event("repricing_failed", "sku", rule.get("sku", ""), "failed", str(e))

    def _apply_rule(self, rule: dict):
        db = get_db()
        sku = rule["sku"]
        channel = rule.get("channel")

        # Get current SKU data
        sku_data = db.table("skus").select("selling_price, mrp, cost_price").eq("sku", sku).execute()
        if not sku_data.data:
            return

        current_price = float(sku_data.data[0].get("selling_price") or 0)
        cost_price = float(sku_data.data[0].get("cost_price") or 0)
        mrp = float(sku_data.data[0].get("mrp") or current_price)

        # Get competitor prices
        comp_query = db.table("competitor_prices").select("min_competitor_price").eq("sku", sku)
        if channel:
            comp_query = comp_query.eq("channel", channel)
        comp = comp_query.execute()

        min_competitor = min(
            [float(r["min_competitor_price"]) for r in comp.data if r.get("min_competitor_price")],
            default=None
        )

        # Determine new price based on strategy
        strategy = rule.get("strategy", "beat_by_pct")
        new_price = current_price

        if strategy == "beat_by_pct" and min_competitor:
            pct = float(rule.get("beat_by_pct", 1)) / 100
            new_price = round(min_competitor * (1 - pct), 2)

        elif strategy == "match_lowest" and min_competitor:
            new_price = min_competitor

        elif strategy == "fixed_markup":
            markup_pct = float(rule.get("markup_pct", 20)) / 100
            new_price = round(cost_price * (1 + markup_pct), 2)

        # Apply floor and ceiling
        min_price = max(
            float(rule.get("min_price") or 0),
            cost_price * 1.05,  # never sell below 5% margin
        )
        max_price = float(rule.get("max_price") or mrp)
        new_price = max(min_price, min(new_price, max_price))
        new_price = round(new_price, 2)

        if abs(new_price - current_price) < 1:  # skip negligible changes
            return

        # Update price in SKU master
        db.table("skus").update({"selling_price": new_price}).eq("sku", sku).execute()

        # Push to channel(s)
        from ..listings.engine import ListingEngine
        listings = db.table("listings").select("*").eq("sku", sku).eq("is_active", True)
        if channel:
            listings = listings.eq("channel", channel)
        for listing in listings.execute().data:
            try:
                ListingEngine()._update_channel_price(listing, {"selling_price": new_price, "mrp": mrp})
            except Exception as e:
                logger.error(f"Failed to push repriced price to {listing['channel']}: {e}")

        log_event("repricing_applied", "sku", sku, "success",
                  f"old={current_price} new={new_price} strategy={strategy}")

        # Log to repricing history
        db.table("repricing_history").insert({
            "sku": sku,
            "channel": channel or "all",
            "old_price": current_price,
            "new_price": new_price,
            "competitor_min": min_competitor,
            "strategy": strategy,
            "rule_id": rule["id"],
        }).execute()
