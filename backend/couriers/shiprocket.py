"""
Shiprocket API wrapper.
Covers all major Indian couriers (Delhivery, BlueDart, Ecom Express, DTDC, etc.)
through one aggregator API.
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from ..config import get_settings
from ..database import get_db
from ..automation.logger import log_event

logger = logging.getLogger(__name__)

SHIPROCKET_BASE = "https://apiv2.shiprocket.in/v1/external"


class ShiprocketClient:

    def _get_token(self) -> str:
        db = get_db()
        # Check cached token
        cached = (
            db.table("shiprocket_tokens")
            .select("token, expires_at")
            .gt("expires_at", datetime.now(timezone.utc).isoformat())
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if cached.data:
            return cached.data[0]["token"]

        # Fresh login
        s = get_settings()
        resp = httpx.post(f"{SHIPROCKET_BASE}/auth/login", json={
            "email": s.shiprocket_email,
            "password": s.shiprocket_password,
        }, timeout=15)
        resp.raise_for_status()
        token = resp.json()["token"]

        db.table("shiprocket_tokens").insert({
            "token": token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=9)).isoformat(),
        }).execute()
        return token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Create Shipment & Get AWB
    # ------------------------------------------------------------------ #
    def create_shipment(self, order: dict, items: list[dict], sku_weights: dict) -> dict:
        """
        Create a Shiprocket order and auto-assign the best courier.
        Returns: {shiprocket_order_id, awb, courier, label_url}
        """
        addr = order.get("shipping_address") or {}

        # Calculate total weight with dead-weight rules
        total_weight_grams = sum(
            sku_weights.get(item.get("sku"), 500) * item.get("qty", 1)
            for item in items
        )
        total_weight_kg = max(total_weight_grams / 1000, 0.1)

        payload = {
            "order_id": order["channel_order_id"],
            "order_date": order.get("created_at", datetime.now().isoformat()),
            "pickup_location": "Primary",  # Set in Shiprocket dashboard
            "channel_id": "",
            "billing_customer_name": order.get("customer_name", ""),
            "billing_address": addr.get("address1") or addr.get("AddressLine1") or addr.get("address", ""),
            "billing_city": addr.get("city", ""),
            "billing_pincode": order.get("pincode", ""),
            "billing_state": order.get("state", ""),
            "billing_country": "India",
            "billing_email": order.get("customer_email", ""),
            "billing_phone": order.get("customer_phone", ""),
            "shipping_is_billing": True,
            "order_items": [
                {
                    "name": item.get("name", item.get("sku", "")),
                    "sku": item.get("sku", ""),
                    "units": item.get("qty", 1),
                    "selling_price": str(item.get("unit_price", 0)),
                }
                for item in items
            ],
            "payment_method": "COD" if order.get("payment_mode") == "cod" else "Prepaid",
            "sub_total": order.get("total_amount", 0),
            "length": 10,  # cm — update from SKU master
            "breadth": 10,
            "height": 10,
            "weight": total_weight_kg,
        }

        resp = httpx.post(f"{SHIPROCKET_BASE}/orders/create/adhoc",
                          headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        sr_order_id = data.get("order_id")
        shipment_id = data.get("shipment_id")

        # Auto-assign best courier
        courier_resp = httpx.post(
            f"{SHIPROCKET_BASE}/courier/assign/awb",
            headers=self._headers(),
            json={"shipment_id": str(shipment_id)},
            timeout=30,
        )
        courier_resp.raise_for_status()
        courier_data = courier_resp.json().get("response", {}).get("data", {})

        awb = courier_data.get("awb_code", "")
        courier_name = courier_data.get("courier_name", "")

        # Generate label
        label_url = self._generate_label(shipment_id)

        log_event("shipment_created", "order", order["channel_order_id"], "success",
                  f"AWB={awb} Courier={courier_name}")

        return {
            "shiprocket_order_id": str(sr_order_id),
            "awb": awb,
            "courier": courier_name,
            "label_url": label_url,
        }

    def _generate_label(self, shipment_id) -> str:
        resp = httpx.post(
            f"{SHIPROCKET_BASE}/courier/generate/label",
            headers=self._headers(),
            json={"shipment_id": [shipment_id]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("label_url", "")

    # ------------------------------------------------------------------ #
    # Schedule Pickup
    # ------------------------------------------------------------------ #
    def schedule_pickup(self, shipment_ids: list[int], pickup_date: str = None) -> bool:
        if not pickup_date:
            pickup_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        resp = httpx.post(
            f"{SHIPROCKET_BASE}/courier/generate/pickup",
            headers=self._headers(),
            json={"shipment_id": shipment_ids, "pickup_date": [pickup_date]},
            timeout=30,
        )
        resp.raise_for_status()
        log_event("pickup_scheduled", "shipment", str(shipment_ids), "success",
                  f"Pickup scheduled for {pickup_date}")
        return True

    # ------------------------------------------------------------------ #
    # Track Shipment
    # ------------------------------------------------------------------ #
    def track_awb(self, awb: str) -> dict:
        resp = httpx.get(
            f"{SHIPROCKET_BASE}/courier/track/awb/{awb}",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # NDR (Non-Delivery Report) Handler
    # ------------------------------------------------------------------ #
    def get_ndrs(self) -> list[dict]:
        resp = httpx.get(f"{SHIPROCKET_BASE}/ndr/all", headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def process_ndrs(self):
        """Fetch NDRs, update order status, alert customer and founder."""
        from ..notifications.whatsapp import WhatsAppNotifier
        db = get_db()
        s = get_settings()
        wa = WhatsAppNotifier()

        ndrs = self.get_ndrs()
        for ndr in ndrs:
            awb = ndr.get("awb")
            if not awb:
                continue

            # Find matching order
            order_res = db.table("orders").select("id, channel_order_id, customer_name, customer_phone").eq("awb", awb).execute()
            if not order_res.data:
                continue
            order = order_res.data[0]

            # Log NDR
            db.table("ndrs").insert({
                "order_id": order["id"],
                "awb": awb,
                "reason": ndr.get("ndr_reason", ""),
                "action_taken": "customer_contacted",
            }).execute()

            # Alert customer
            if order.get("customer_phone"):
                wa.send_ndr_customer_alert(
                    phone=order["customer_phone"],
                    name=order["customer_name"] or "Customer",
                    order_id=order["channel_order_id"],
                    reason=ndr.get("ndr_reason", "delivery attempt failed"),
                )

            # Alert founder
            wa.send_text(
                s.founder_whatsapp,
                f"⚠️ NDR: Order #{order['channel_order_id']} | AWB: {awb} | Reason: {ndr.get('ndr_reason', 'N/A')}",
            )
            log_event("ndr_processed", "order", order["channel_order_id"])

    # ------------------------------------------------------------------ #
    # Bulk auto-create shipments for all RTD orders
    # ------------------------------------------------------------------ #
    def auto_ship_rtd_orders(self):
        db = get_db()
        rtd_orders = (
            db.table("orders")
            .select("*, order_items(*)")
            .eq("status", "rtd")
            .is_("awb", "null")
            .execute()
        )

        # Fetch SKU weights
        skus = db.table("skus").select("sku, weight_grams").execute()
        sku_weights = {s["sku"]: s["weight_grams"] for s in skus.data}

        for order in rtd_orders.data:
            try:
                result = self.create_shipment(order, order.get("order_items", []), sku_weights)
                db.table("orders").update({
                    "awb": result["awb"],
                    "courier": result["courier"],
                    "shiprocket_order_id": result["shiprocket_order_id"],
                    "label_url": result["label_url"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", order["id"]).execute()
            except Exception as e:
                log_event("auto_ship_failed", "order", order["channel_order_id"], "failed", str(e))
                logger.error(f"Auto-ship failed for {order['channel_order_id']}: {e}")
