"""
Returns & claim automation:
- Detect return hotspots
- Auto-file courier claims for lost shipments
- Update inventory on received returns
"""
import logging
from datetime import datetime, timezone, timedelta
from ..database import get_db
from ..config import get_settings
from .logger import log_event

logger = logging.getLogger(__name__)


class ReturnsEngine:

    def run_all(self):
        self.process_marketplace_returns()
        self.detect_rto_and_update_inventory()
        self.alert_return_hotspots()

    def process_marketplace_returns(self):
        """Pull return events from all channels and record them."""
        db = get_db()

        returned_orders = (
            db.table("orders")
            .select("id, channel, channel_order_id, pincode, state")
            .in_("status", ["returned", "rto"])
            .execute()
        )

        for order in returned_orders.data:
            existing = (
                db.table("returns")
                .select("id")
                .eq("order_id", order["id"])
                .execute()
            )
            if existing.data:
                continue

            db.table("returns").insert({
                "order_id": order["id"],
                "channel": order["channel"],
                "return_status": "initiated",
            }).execute()
            log_event("return_recorded", "order", order["channel_order_id"])

    def detect_rto_and_update_inventory(self):
        """When RTO is received, add qty back to inventory."""
        db = get_db()

        rto_orders = (
            db.table("orders")
            .select("id, channel_order_id, order_items(sku, qty)")
            .eq("status", "rto")
            .execute()
        )

        for order in rto_orders.data:
            for item in (order.get("order_items") or []):
                sku = item.get("sku")
                qty = item.get("qty", 1)
                if not sku:
                    continue

                # Add qty back to inventory
                inv = db.table("inventory").select("qty_on_hand").eq("sku", sku).execute()
                if inv.data:
                    new_qty = (inv.data[0]["qty_on_hand"] or 0) + qty
                    db.table("inventory").update({
                        "qty_on_hand": new_qty,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("sku", sku).execute()
                    log_event("rto_inventory_restored", "sku", sku, "success",
                              f"+{qty} units from RTO order {order['channel_order_id']}")

    def alert_return_hotspots(self):
        """Alert founder if any pincode crosses 30% RTO rate with >5 orders."""
        from ..notifications.whatsapp import WhatsAppNotifier
        db = get_db()
        s = get_settings()

        hotspots = (
            db.table("rto_hotspots")
            .select("pincode, state, rto_rate_pct, total_orders")
            .gt("rto_rate_pct", 30)
            .gt("total_orders", 5)
            .order("rto_rate_pct", desc=True)
            .limit(5)
            .execute()
        )

        if not hotspots.data:
            return

        lines = ["🚨 RTO Hotspot Alert:"]
        for h in hotspots.data:
            lines.append(f"Pincode {h['pincode']} ({h['state']}): {h['rto_rate_pct']}% RTO ({h['total_orders']} orders)")

        wa = WhatsAppNotifier()
        wa.send_text(s.founder_whatsapp, "\n".join(lines))
        log_event("rto_hotspot_alert", "system", "pincode_analysis", "success")

    def file_courier_claims(self):
        """Auto-flag orders eligible for courier claim (lost in transit)."""
        db = get_db()
        s = get_settings()

        # Orders dispatched >15 days ago, not delivered, not RTO
        cutoff = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        lost = (
            db.table("orders")
            .select("id, channel_order_id, awb, courier, total_amount")
            .eq("status", "dispatched")
            .lt("dispatched_at", cutoff)
            .execute()
        )

        for order in lost.data:
            existing_claim = (
                db.table("returns")
                .select("id")
                .eq("order_id", order["id"])
                .eq("claim_filed", True)
                .execute()
            )
            if existing_claim.data:
                continue

            db.table("returns").upsert({
                "order_id": order["id"],
                "channel": "courier",
                "return_status": "lost",
                "claim_filed": True,
                "claim_status": "pending",
                "claim_amount": order.get("total_amount"),
            }, on_conflict="order_id").execute()

            log_event("courier_claim_filed", "order", order["channel_order_id"], "success",
                      f"AWB={order['awb']} Courier={order['courier']}")

        if lost.data:
            from ..notifications.whatsapp import WhatsAppNotifier
            wa = WhatsAppNotifier()
            wa.send_text(
                s.founder_whatsapp,
                f"📋 {len(lost.data)} courier claims auto-filed for lost shipments. Check dashboard for details.",
            )
