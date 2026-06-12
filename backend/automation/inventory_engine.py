"""
Inventory automation:
- Real-time qty sync across all channels
- Oversell prevention via reservation logic
- Low stock alerts → founder WhatsApp
- Auto-generate draft POs when below reorder threshold
- Dead stock detection
- Weekly stock-take reminder
"""
import logging
import httpx
from datetime import datetime, timezone, date, timedelta
from ..database import get_db
from ..config import get_settings
from .logger import log_event

logger = logging.getLogger(__name__)


class InventoryEngine:

    def run_all(self):
        self.sync_reservations()
        self.check_low_stock()
        self.generate_pos_for_low_stock()
        self.flag_dead_stock()
        self.push_inventory_to_channels()

    # ------------------------------------------------------------------ #
    # Reservation Sync
    # Reserve qty for all unfulfilled orders to prevent oversell
    # ------------------------------------------------------------------ #
    def sync_reservations(self):
        db = get_db()
        # Get pending/confirmed/rtd orders
        pending = (
            db.table("order_items")
            .select("sku, qty, orders(status)")
            .execute()
        )

        # Aggregate reserved qty per SKU
        reserved: dict[str, int] = {}
        for item in pending.data:
            order_status = (item.get("orders") or {}).get("status", "")
            if order_status in ("pending", "confirmed", "rtd"):
                sku = item.get("sku")
                if sku:
                    reserved[sku] = reserved.get(sku, 0) + (item.get("qty") or 1)

        # Update inventory table
        for sku, qty in reserved.items():
            db.table("inventory").upsert({
                "sku": sku,
                "qty_reserved": qty,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="sku").execute()

        logger.info(f"Synced reservations for {len(reserved)} SKUs")

    # ------------------------------------------------------------------ #
    # Push available qty to all marketplace channels
    # ------------------------------------------------------------------ #
    def push_inventory_to_channels(self):
        db = get_db()
        s = get_settings()
        inventory = db.table("inventory").select("sku, qty_available").execute()

        for row in inventory.data:
            sku = row["sku"]
            qty = max(row["qty_available"] or 0, 0)
            listings = (
                db.table("listings")
                .select("channel, channel_sku_id, listing_id")
                .eq("sku", sku)
                .eq("is_active", True)
                .execute()
            )
            for listing in listings.data:
                try:
                    self._push_qty_to_channel(listing["channel"], listing, qty)
                except Exception as e:
                    log_event("inventory_push_failed", "sku", sku, "failed",
                              f"channel={listing['channel']} err={e}")

    def _push_qty_to_channel(self, channel: str, listing: dict, qty: int):
        s = get_settings()
        if channel == "shopify":
            self._shopify_update_inventory(listing["channel_sku_id"], qty)
        elif channel == "amazon":
            self._amazon_update_inventory(listing["channel_sku_id"], qty)
        elif channel == "flipkart":
            self._flipkart_update_inventory(listing["channel_sku_id"], qty)
        elif channel == "meesho":
            self._meesho_update_inventory(listing["channel_sku_id"], qty)

    def _shopify_update_inventory(self, inventory_item_id: str, qty: int):
        s = get_settings()
        # First get location_id
        loc_resp = httpx.get(
            f"https://{s.shopify_store_url}/admin/api/2024-01/locations.json",
            headers={"X-Shopify-Access-Token": s.shopify_access_token},
            timeout=10,
        )
        loc_resp.raise_for_status()
        location_id = loc_resp.json()["locations"][0]["id"]

        httpx.post(
            f"https://{s.shopify_store_url}/admin/api/2024-01/inventory_levels/set.json",
            headers={"X-Shopify-Access-Token": s.shopify_access_token},
            json={"location_id": location_id, "inventory_item_id": inventory_item_id, "available": qty},
            timeout=10,
        ).raise_for_status()

    def _amazon_update_inventory(self, sku: str, qty: int):
        from sp_api.api import Feeds
        from sp_api.base import Marketplaces, Credentials
        s = get_settings()
        # Amazon inventory update via Inventory Feed
        feed_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<AmazonEnvelope>
  <Header><DocumentVersion>1.01</DocumentVersion><MerchantIdentifier>{s.amazon_client_id}</MerchantIdentifier></Header>
  <MessageType>Inventory</MessageType>
  <Message><MessageID>1</MessageID>
    <Inventory><SKU>{sku}</SKU><Quantity>{qty}</Quantity><FulfillmentLatency>1</FulfillmentLatency></Inventory>
  </Message>
</AmazonEnvelope>"""
        creds = Credentials(refresh_token=s.amazon_refresh_token, lwa_app_id=s.amazon_client_id, lwa_client_secret=s.amazon_client_secret)
        feeds_client = Feeds(credentials=creds, marketplace=Marketplaces.IN)
        feeds_client.submit_feed(feed_type="_POST_INVENTORY_AVAILABILITY_DATA_", file=feed_content.encode(), content_type="text/xml")

    def _flipkart_update_inventory(self, fsn: str, qty: int):
        from ..ingestion.flipkart import FlipkartIngester
        fi = FlipkartIngester()
        httpx.post(
            "https://api.flipkart.net/sellers/listings/v3/update/inventory",
            headers=fi._headers(),
            json={"skuId": fsn, "available": qty},
            timeout=10,
        ).raise_for_status()

    def _meesho_update_inventory(self, product_id: str, qty: int):
        s = get_settings()
        httpx.post(
            "https://external.meesho.com/api/v1/supplier/products/inventory",
            headers={"api-token": s.meesho_api_token},
            json={"product_id": product_id, "quantity": qty},
            timeout=10,
        ).raise_for_status()

    # ------------------------------------------------------------------ #
    # Low Stock Check & Alerts
    # ------------------------------------------------------------------ #
    def check_low_stock(self):
        from ..notifications.whatsapp import WhatsAppNotifier
        db = get_db()
        s = get_settings()

        low = (
            db.table("inventory")
            .select("sku, qty_available, skus(name, reorder_qty)")
            .lt("qty_available", s.low_stock_threshold)
            .execute()
        )

        if not low.data:
            return

        wa = WhatsAppNotifier()
        for row in low.data:
            sku_info = row.get("skus") or {}
            wa.send_low_stock_alert(
                phone=s.founder_whatsapp,
                sku=row["sku"],
                sku_name=sku_info.get("name", row["sku"]),
                qty=row["qty_available"] or 0,
            )
            log_event("low_stock_alert_sent", "sku", row["sku"])

    # ------------------------------------------------------------------ #
    # Auto PO Generation
    # ------------------------------------------------------------------ #
    def generate_pos_for_low_stock(self):
        from ..notifications.email import EmailNotifier
        db = get_db()
        s = get_settings()

        low = (
            db.table("inventory")
            .select("sku, qty_available, skus(name, reorder_qty, supplier_name, cost_price, lead_time_days)")
            .lt("qty_available", s.low_stock_threshold)
            .execute()
        )

        emailer = EmailNotifier()
        for row in low.data:
            sku_info = row.get("skus") or {}

            # Check if open PO already exists
            existing_po = (
                db.table("purchase_orders")
                .select("id")
                .eq("sku", row["sku"])
                .in_("status", ["draft", "sent", "acknowledged"])
                .execute()
            )
            if existing_po.data:
                continue

            po_number = f"PO-{row['sku']}-{datetime.now().strftime('%Y%m%d%H%M')}"
            reorder_qty = sku_info.get("reorder_qty") or 100
            lead_days = sku_info.get("lead_time_days") or 7
            expected_by = (date.today() + timedelta(days=lead_days)).isoformat()

            po = {
                "po_number": po_number,
                "sku": row["sku"],
                "supplier_name": sku_info.get("supplier_name", "Unknown"),
                "qty_ordered": reorder_qty,
                "unit_cost": sku_info.get("cost_price", 0),
                "status": "draft",
                "expected_by": expected_by,
            }
            db.table("purchase_orders").insert(po).execute()
            emailer.send_po_draft(s.founder_email, po)
            log_event("po_generated", "sku", row["sku"], "success", f"PO {po_number}")

    # ------------------------------------------------------------------ #
    # Dead Stock Detection
    # ------------------------------------------------------------------ #
    def flag_dead_stock(self):
        db = get_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        # SKUs with inventory but zero sales in 30 days
        sold_skus_res = (
            db.table("order_items")
            .select("sku")
            .gt("orders.created_at", cutoff)
            .execute()
        )
        sold_skus = {row["sku"] for row in sold_skus_res.data if row.get("sku")}

        all_inventory = db.table("inventory").select("sku, qty_on_hand").gt("qty_on_hand", 0).execute()
        dead = [row["sku"] for row in all_inventory.data if row["sku"] not in sold_skus]

        if dead:
            log_event("dead_stock_detected", "sku", ",".join(dead), "success",
                      f"{len(dead)} SKUs with no sales in 30 days")
            # Mark in SKUs table for dashboard visibility
            for sku in dead:
                db.table("app_settings").upsert({
                    "key": f"dead_stock_{sku}",
                    "value": "true",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).execute()

    # ------------------------------------------------------------------ #
    # Weekly Stock-Take Reminder
    # ------------------------------------------------------------------ #
    def send_stocktake_reminder(self):
        from ..notifications.whatsapp import WhatsAppNotifier
        s = get_settings()
        wa = WhatsAppNotifier()
        wa.send_text(
            s.founder_whatsapp,
            "📋 Weekly Reminder: Time to do a stock-take! Please count all SKUs and update inventory levels in the D2C dashboard.",
        )
        log_event("stocktake_reminder_sent", "system", "weekly", "success")
