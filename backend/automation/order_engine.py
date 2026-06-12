"""
Core order automation engine.
Runs on every ingestion cycle and processes orders through automation rules.
"""
import logging
from datetime import datetime, timedelta, timezone
from ..database import get_db
from ..config import get_settings
from .logger import log_event

logger = logging.getLogger(__name__)


class OrderAutomationEngine:

    def run_all(self):
        """Entry point — run all order automations in sequence."""
        self.flag_rtd_orders()
        self.confirm_cod_orders()
        self.score_rto_risk()
        self.push_awb_to_marketplaces()
        self.send_dispatch_notifications()

    # ------------------------------------------------------------------ #
    # RTD Detection
    # ------------------------------------------------------------------ #
    def flag_rtd_orders(self):
        """Flag orders as RTD if they've been confirmed for > N hours."""
        s = get_settings()
        db = get_db()
        threshold = datetime.now(timezone.utc) - timedelta(hours=s.rtd_hours_threshold)

        result = (
            db.table("orders")
            .select("id, channel, channel_order_id")
            .eq("status", "confirmed")
            .lt("created_at", threshold.isoformat())
            .execute()
        )
        for order in result.data:
            db.table("orders").update({"status": "rtd", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", order["id"]).execute()
            log_event("rtd_flagged", "order", order["channel_order_id"], "success",
                      f"Order auto-flagged RTD after {s.rtd_hours_threshold}h")

        if result.data:
            logger.info(f"Flagged {len(result.data)} orders as RTD")

    # ------------------------------------------------------------------ #
    # COD Confirmation
    # ------------------------------------------------------------------ #
    def confirm_cod_orders(self):
        """Send COD confirmation WA message for new COD orders that haven't been confirmed."""
        from ..notifications.whatsapp import WhatsAppNotifier
        s = get_settings()
        db = get_db()

        # Orders that are COD, new (within 30 min), not yet messaged
        cutoff = datetime.now(timezone.utc) - timedelta(hours=s.cod_confirm_timeout_hours)
        result = (
            db.table("orders")
            .select("id, channel_order_id, customer_name, customer_phone, total_amount, channel")
            .eq("payment_mode", "cod")
            .eq("status", "confirmed")
            .is_("cod_confirmed", "null")
            .gt("created_at", cutoff.isoformat())
            .execute()
        )

        wa = WhatsAppNotifier()
        for order in result.data:
            if not order.get("customer_phone"):
                continue

            # Check if we already sent a confirmation message
            already_sent = (
                db.table("notification_log")
                .select("id")
                .eq("template", "cod_confirmation")
                .eq("entity_id", order["id"])
                .execute()
            )
            if already_sent.data:
                continue

            sent = wa.send_cod_confirmation(
                phone=order["customer_phone"],
                name=order["customer_name"] or "Customer",
                order_id=order["channel_order_id"],
                amount=order["total_amount"],
            )

            if sent:
                db.table("notification_log").insert({
                    "channel": "whatsapp",
                    "recipient": order["customer_phone"],
                    "template": "cod_confirmation",
                    "entity_id": order["id"],
                }).execute()
                log_event("cod_confirmation_sent", "order", order["channel_order_id"])

    # ------------------------------------------------------------------ #
    # RTO Risk Scoring
    # ------------------------------------------------------------------ #
    def score_rto_risk(self):
        """Score RTO risk per order based on pincode history + COD flag."""
        db = get_db()

        # Get all unscored COD orders
        unscored = (
            db.table("orders")
            .select("id, pincode, payment_mode, channel")
            .is_("rto_risk_score", "null")
            .eq("payment_mode", "cod")
            .in_("status", ["confirmed", "rtd"])
            .execute()
        )

        if not unscored.data:
            return

        # Get pincode RTO rates from historical data
        hotspots = db.table("rto_hotspots").select("pincode, rto_rate_pct").execute()
        pincode_risk = {row["pincode"]: float(row["rto_rate_pct"] or 0) / 100 for row in hotspots.data}

        for order in unscored.data:
            pincode = order.get("pincode", "")
            base_risk = pincode_risk.get(pincode, 0.15)  # default 15% if no data
            # COD adds +10% risk
            risk_score = min(base_risk + 0.10, 1.0)

            db.table("orders").update({
                "rto_risk_score": round(risk_score, 2),
                "rto_flag": risk_score > 0.4,
            }).eq("id", order["id"]).execute()

        logger.info(f"Scored RTO risk for {len(unscored.data)} orders")

    # ------------------------------------------------------------------ #
    # Push AWB to Marketplaces
    # ------------------------------------------------------------------ #
    def push_awb_to_marketplaces(self):
        """After courier assigns AWB, push tracking back to each marketplace."""
        db = get_db()

        orders_with_awb = (
            db.table("orders")
            .select("id, channel, channel_order_id, channel_suborder_id, courier, awb")
            .eq("status", "rtd")
            .not_.is_("awb", "null")
            .execute()
        )

        for order in orders_with_awb.data:
            try:
                self._push_awb_to_channel(order)
                db.table("orders").update({
                    "status": "dispatched",
                    "dispatched_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", order["id"]).execute()
                log_event("awb_pushed", "order", order["channel_order_id"], "success",
                          f"AWB {order['awb']} pushed to {order['channel']}")
            except Exception as e:
                log_event("awb_push_failed", "order", order["channel_order_id"], "failed", str(e))

    def _push_awb_to_channel(self, order: dict):
        channel = order["channel"]
        awb = order["awb"]
        courier = order["courier"]

        if channel == "amazon":
            self._amazon_confirm_shipment(order["channel_order_id"], awb, courier)
        elif channel == "flipkart":
            self._flipkart_dispatch(order["channel_suborder_id"] or order["channel_order_id"], awb)
        elif channel == "meesho":
            self._meesho_dispatch(order["channel_order_id"], awb)
        # Myntra dispatches through Myntra logistics only; Shopify is informational

    def _amazon_confirm_shipment(self, order_id: str, awb: str, courier: str):
        from sp_api.api import Orders
        from sp_api.base import Marketplaces, Credentials
        s = get_settings()
        creds = Credentials(
            refresh_token=s.amazon_refresh_token,
            lwa_app_id=s.amazon_client_id,
            lwa_client_secret=s.amazon_client_secret,
        )
        client = Orders(credentials=creds, marketplace=Marketplaces.IN)
        client.confirm_shipment(order_id=order_id, body={
            "marketplaceId": s.amazon_marketplace_id,
            "shippingSpeedCategory": "Standard",
            "shipmentTrackingInformation": {
                "trackingId": awb,
                "carrierCode": courier.upper(),
            },
        })

    def _flipkart_dispatch(self, suborder_id: str, awb: str):
        import httpx
        from ..ingestion.flipkart import FlipkartIngester
        fi = FlipkartIngester()
        httpx.post(
            "https://api.flipkart.net/sellers/shipments/dispatch",
            headers=fi._headers(),
            json={"shipments": [{"subOrderId": suborder_id, "trackingId": awb}]},
            timeout=15,
        ).raise_for_status()

    def _meesho_dispatch(self, order_id: str, awb: str):
        import httpx
        s = get_settings()
        httpx.post(
            "https://external.meesho.com/api/v1/supplier/orders/dispatch",
            headers={"api-token": s.meesho_api_token},
            json={"order_id": order_id, "awb": awb},
            timeout=15,
        ).raise_for_status()

    # ------------------------------------------------------------------ #
    # Dispatch Notifications to Customer
    # ------------------------------------------------------------------ #
    def send_dispatch_notifications(self):
        """Send WA + email to customer when order is dispatched."""
        from ..notifications.whatsapp import WhatsAppNotifier
        from ..notifications.email import EmailNotifier
        db = get_db()

        recently_dispatched = (
            db.table("orders")
            .select("id, channel_order_id, customer_name, customer_phone, customer_email, awb, courier")
            .eq("status", "dispatched")
            .is_("dispatched_at", "not.null")
            .execute()
        )

        wa = WhatsAppNotifier()
        emailer = EmailNotifier()

        for order in recently_dispatched.data:
            # Check dedup
            already = (
                db.table("notification_log")
                .select("id")
                .eq("template", "dispatch_alert")
                .eq("entity_id", order["id"])
                .execute()
            )
            if already.data:
                continue

            phone = order.get("customer_phone")
            email = order.get("customer_email")

            if phone:
                wa.send_dispatch_alert(
                    phone=phone,
                    name=order["customer_name"] or "Customer",
                    order_id=order["channel_order_id"],
                    awb=order["awb"],
                    courier=order["courier"],
                )
            if email:
                emailer.send_dispatch_alert(
                    to=email,
                    name=order["customer_name"] or "Customer",
                    order_id=order["channel_order_id"],
                    awb=order["awb"],
                    courier=order["courier"],
                )

            db.table("notification_log").insert({
                "channel": "whatsapp+email",
                "recipient": phone or email or "",
                "template": "dispatch_alert",
                "entity_id": order["id"],
            }).execute()
