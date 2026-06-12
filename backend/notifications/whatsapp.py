"""
WhatsApp notifications via Meta Cloud API.
Free tier: 1000 business-initiated conversations/month — plenty for 100-1000 orders.

Template names must be pre-approved in Meta Business Manager.
All templates below use 'utility' category (transactional) to avoid marketing restrictions.
"""
import httpx
import logging
from ..config import get_settings

logger = logging.getLogger(__name__)

META_WA_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppNotifier:

    def _send(self, phone: str, payload: dict) -> bool:
        s = get_settings()
        # Normalize phone: strip leading 0, add 91 country code if needed
        phone = phone.replace(" ", "").replace("-", "").replace("+", "")
        if phone.startswith("0"):
            phone = phone[1:]
        if not phone.startswith("91"):
            phone = "91" + phone

        try:
            resp = httpx.post(
                f"{META_WA_BASE}/{s.whatsapp_phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {s.whatsapp_access_token}",
                    "Content-Type": "application/json",
                },
                json={"messaging_product": "whatsapp", "to": phone, **payload},
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"WhatsApp send failed to {phone}: {e}")
            return False

    def send_text(self, phone: str, message: str) -> bool:
        return self._send(phone, {"type": "text", "text": {"body": message}})

    def send_cod_confirmation(self, phone: str, name: str, order_id: str, amount: float) -> bool:
        """
        Template: cod_confirmation
        Body: "Hi {{1}}, your COD order #{{2}} for ₹{{3}} has been placed.
               Reply YES to confirm or NO to cancel."
        """
        return self._send(phone, {
            "type": "template",
            "template": {
                "name": "cod_confirmation",
                "language": {"code": "en"},
                "components": [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name},
                        {"type": "text", "text": order_id},
                        {"type": "text", "text": str(int(amount))},
                    ],
                }],
            },
        })

    def send_dispatch_alert(self, phone: str, name: str, order_id: str,
                            awb: str, courier: str) -> bool:
        """
        Template: dispatch_alert
        Body: "Hi {{1}}, your order #{{2}} has been shipped via {{3}}.
               Track it with AWB: {{4}}"
        """
        return self._send(phone, {
            "type": "template",
            "template": {
                "name": "dispatch_alert",
                "language": {"code": "en"},
                "components": [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name},
                        {"type": "text", "text": order_id},
                        {"type": "text", "text": courier or "courier"},
                        {"type": "text", "text": awb or "N/A"},
                    ],
                }],
            },
        })

    def send_low_stock_alert(self, phone: str, sku: str, sku_name: str, qty: int) -> bool:
        """
        Template: low_stock_alert (founder alert)
        Body: "LOW STOCK ALERT: {{1}} ({{2}}) has only {{3}} units left. Time to reorder!"
        """
        return self._send(phone, {
            "type": "template",
            "template": {
                "name": "low_stock_alert",
                "language": {"code": "en"},
                "components": [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": sku_name},
                        {"type": "text", "text": sku},
                        {"type": "text", "text": str(qty)},
                    ],
                }],
            },
        })

    def send_ndr_customer_alert(self, phone: str, name: str, order_id: str, reason: str) -> bool:
        """
        Template: ndr_customer_alert
        Body: "Hi {{1}}, we tried delivering order #{{2}} but couldn't ({{3}}).
               Please call 1800-XXX to reschedule."
        """
        return self._send(phone, {
            "type": "template",
            "template": {
                "name": "ndr_customer_alert",
                "language": {"code": "en"},
                "components": [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name},
                        {"type": "text", "text": order_id},
                        {"type": "text", "text": reason or "delivery attempt failed"},
                    ],
                }],
            },
        })

    def send_founder_daily_summary(self, phone: str, summary: dict) -> bool:
        """Plain text daily digest to founder."""
        lines = [
            f"📦 D2C Daily Summary - {summary.get('date', 'Today')}",
            f"Orders: {summary.get('total_orders', 0)}",
            f"GMV: ₹{summary.get('gmv', 0):,.0f}",
            f"Dispatched: {summary.get('dispatched', 0)}",
            f"RTO: {summary.get('rto', 0)}",
            f"Fulfillment Rate: {summary.get('fulfillment_rate', 0)}%",
            f"Pending RTD: {summary.get('pending_rtd', 0)}",
        ]
        return self.send_text(phone, "\n".join(lines))
