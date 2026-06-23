"""
Email notifications via MoEngage Transactional Email API.
Docs: https://developers.moengage.com/hc/en-us/articles/4403912419092
"""
import httpx
import logging
from ..config import get_settings

logger = logging.getLogger(__name__)


class EmailNotifier:

    def _send(self, to: str, subject: str, html: str, to_name: str = "") -> bool:
        s = get_settings()
        if not s.moengage_app_id or not s.moengage_api_key:
            logger.warning("MoEngage not configured — skipping email to %s", to)
            return False

        payload = {
            "from": {"name": s.moengage_sender_name, "email": s.moengage_sender_email},
            "to": [{"name": to_name or to, "email": to}],
            "subject": subject,
            "html": html,
        }

        try:
            resp = httpx.post(
                f"https://{s.moengage_api_host}/v1/email/send",
                auth=(s.moengage_app_id, s.moengage_api_key),
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("MoEngage email failed to %s: %s", to, e)
            return False

    def send_dispatch_alert(self, to: str, name: str, order_id: str,
                            awb: str, courier: str) -> bool:
        html = f"""
        <p>Hi {name},</p>
        <p>Your order <strong>#{order_id}</strong> has been shipped!</p>
        <p>Courier: <strong>{courier}</strong><br/>AWB: <strong>{awb}</strong></p>
        <p>You can track your shipment on the courier's website.</p>
        <p>Thank you for your purchase!</p>
        """
        return self._send(to, f"Your order #{order_id} is on the way!", html, name)

    def send_daily_error_digest(self, to: str, errors: list[dict]) -> bool:
        rows = "".join(
            f"<tr><td>{e['event_type']}</td><td>{e['entity_id']}</td><td>{e['message']}</td></tr>"
            for e in errors
        )
        html = f"""
        <h2>Automation Error Log</h2>
        <table border='1' cellpadding='4'>
          <thead><tr><th>Event</th><th>Entity</th><th>Error</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """
        return self._send(to, f"D2C Automation Errors ({len(errors)} issues)", html)

    def send_po_draft(self, to: str, po: dict) -> bool:
        html = f"""
        <h2>Purchase Order Draft — {po['po_number']}</h2>
        <p><b>SKU:</b> {po['sku']}<br/>
           <b>Supplier:</b> {po['supplier_name']}<br/>
           <b>Qty:</b> {po['qty_ordered']}<br/>
           <b>Unit Cost:</b> ₹{po['unit_cost']}<br/>
           <b>Total:</b> ₹{po['qty_ordered'] * po['unit_cost']:.2f}<br/>
           <b>Expected By:</b> {po['expected_by']}</p>
        <p>Please review and confirm with supplier.</p>
        """
        return self._send(to, f"PO Draft: {po['sku']} — {po['qty_ordered']} units", html)
