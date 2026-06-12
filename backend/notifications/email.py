import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ..config import get_settings

logger = logging.getLogger(__name__)


class EmailNotifier:

    def _send(self, to: str, subject: str, html: str, text: str = "") -> bool:
        s = get_settings()
        if not s.smtp_user or not s.email_from:
            logger.warning("Email not configured — skipping send")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = s.email_from
            msg["To"] = to
            if text:
                msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(s.smtp_host, s.smtp_port) as server:
                server.starttls()
                server.login(s.smtp_user, s.smtp_password)
                server.sendmail(s.email_from, to, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email send failed to {to}: {e}")
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
        return self._send(to, f"Your order #{order_id} is on the way!", html)

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
        return self._send(to, f"⚠️ D2C Automation Errors ({len(errors)} issues)", html)

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
