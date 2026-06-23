"""
SKU/barcode auto-mapping.

When an order arrives with a channel_sku_id (FSN, ASIN, Nykaa SKU etc.),
this mapper tries to resolve it to the seller's own internal SKU so that
inventory deductions, profit tracking, and listings sync all work off one
consistent SKU master.

Resolution priority:
  1. Exact match in listings table (channel + channel_sku_id → sku)
  2. Barcode match in skus table
  3. Name fuzzy match (last resort — creates a placeholder if nothing found)
"""
import logging
from ..database import get_db

logger = logging.getLogger(__name__)


class SKUMapper:

    def __init__(self):
        self._cache: dict[str, str] = {}  # (channel, channel_sku_id) → sku

    def resolve(self, channel: str, channel_sku_id: str, product_name: str = "", barcode: str = "") -> str | None:
        """
        Return the internal SKU string for a given channel item.
        Returns None if no match can be made.
        """
        if not channel_sku_id:
            return None

        cache_key = f"{channel}:{channel_sku_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        db = get_db()

        # 1 — exact listing match
        row = (
            db.table("listings")
            .select("sku")
            .eq("channel", channel)
            .eq("channel_sku_id", channel_sku_id)
            .limit(1)
            .execute()
        )
        if row.data:
            sku = row.data[0]["sku"]
            self._cache[cache_key] = sku
            return sku

        # 2 — barcode match
        if barcode:
            row = db.table("skus").select("sku").eq("barcode", barcode).limit(1).execute()
            if row.data:
                sku = row.data[0]["sku"]
                self._register_mapping(db, channel, channel_sku_id, sku)
                self._cache[cache_key] = sku
                return sku

        # 3 — name match (case-insensitive, products table)
        if product_name:
            row = (
                db.table("products")
                .select("id")
                .ilike("name", f"%{product_name[:40]}%")
                .limit(1)
                .execute()
            )
            if row.data:
                product_id = row.data[0]["id"]
                sku_row = db.table("skus").select("sku").eq("product_id", product_id).limit(1).execute()
                if sku_row.data:
                    sku = sku_row.data[0]["sku"]
                    self._register_mapping(db, channel, channel_sku_id, sku)
                    self._cache[cache_key] = sku
                    return sku

        return None

    def resolve_or_create(self, channel: str, channel_sku_id: str, product_name: str = "",
                          price: float = 0.0) -> str:
        """
        Like resolve() but creates a placeholder SKU when nothing matches,
        so orders are never dropped due to missing mapping.
        """
        sku = self.resolve(channel, channel_sku_id, product_name)
        if sku:
            return sku

        # Create a placeholder product + SKU
        db = get_db()
        placeholder_sku = f"{channel.upper()}-{channel_sku_id}"[:64]

        existing = db.table("skus").select("sku").eq("sku", placeholder_sku).execute()
        if not existing.data:
            product = db.table("products").insert({
                "name": product_name or placeholder_sku,
                "is_active": True,
                "tags": [channel, "auto-imported"],
            }).execute()
            product_id = product.data[0]["id"]
            db.table("skus").insert({
                "sku": placeholder_sku,
                "product_id": product_id,
                "selling_price": price,
            }).execute()
            logger.info(f"[sku_mapper] Created placeholder SKU {placeholder_sku} for {channel}:{channel_sku_id}")

        self._register_mapping(db, channel, channel_sku_id, placeholder_sku)
        self._cache[f"{channel}:{channel_sku_id}"] = placeholder_sku
        return placeholder_sku

    def _register_mapping(self, db, channel: str, channel_sku_id: str, sku: str):
        """Persist the mapping so future lookups are instant."""
        db.table("listings").upsert({
            "sku": sku,
            "channel": channel,
            "channel_sku_id": channel_sku_id,
            "is_active": True,
            "last_synced_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }, on_conflict="sku,channel").execute()

    def bulk_map_unmapped_orders(self):
        """
        One-off job: scan order_items with no resolved SKU and attempt to map them.
        """
        db = get_db()
        unmapped = (
            db.table("order_items")
            .select("id, sku, channel_sku_id, name, orders(channel)")
            .is_("sku", "null")
            .limit(500)
            .execute()
        )
        resolved = 0
        for item in unmapped.data:
            channel = (item.get("orders") or {}).get("channel", "")
            channel_sku_id = item.get("channel_sku_id", "")
            name = item.get("name", "")
            if not channel_sku_id:
                continue
            sku = self.resolve_or_create(channel, channel_sku_id, name)
            if sku:
                db.table("order_items").update({"sku": sku}).eq("id", item["id"]).execute()
                resolved += 1

        logger.info(f"[sku_mapper] bulk_map resolved {resolved}/{len(unmapped.data)} unmapped items")
        return {"resolved": resolved, "total": len(unmapped.data)}
