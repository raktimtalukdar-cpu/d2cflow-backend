"""
Team invite emails — sends a real HTML email via SMTP.
"""
import smtplib
import secrets
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from ..config import get_settings

router = APIRouter(prefix="/api", tags=["invite"])


class InvitePayload(BaseModel):
    emails: List[EmailStr]
    role: str
    workspace_name: str = "d2cflow"
    inviter_name: str = "Your team admin"
    inviter_email: str = ""


ROLE_LABELS = {
    "admin": "Admin — Full access including billing",
    "member": "Member — Orders, shipping, returns",
    "viewer": "Viewer — Read-only access",
    "ops": "Operations — Orders & shipping only",
}


def _send_invite_email(to_email: str, payload: InvitePayload, settings) -> None:
    invite_token = secrets.token_urlsafe(24)
    accept_url = f"{settings.app_base_url}/accept-invite?token={invite_token}&email={to_email}"
    role_label = ROLE_LABELS.get(payload.role, payload.role)

    inviter_line = payload.inviter_name
    if payload.inviter_email:
        inviter_line += f' <a href="mailto:{payload.inviter_email}" style="color:#3395FF;">{payload.inviter_email}</a>'

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f4f4f5; margin: 0; padding: 40px 20px; }}
    .card {{ background: #fff; border-radius: 12px; max-width: 520px; margin: 0 auto; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .header {{ background: #1a1d27; padding: 24px 32px; }}
    .logo {{ color: #fff; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
    .logo span {{ color: #3395FF; }}
    .body {{ padding: 32px; }}
    h2 {{ margin: 0 0 8px; font-size: 20px; color: #111; }}
    p {{ color: #6b7280; font-size: 14px; line-height: 1.6; margin: 0 0 16px; }}
    .inviter-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; color: #374151; }}
    .role-badge {{ display: inline-block; background: #EBF4FF; color: #1d4ed8; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 6px; margin-bottom: 24px; }}
    .cta {{ display: block; background: #3395FF; color: #fff !important; text-decoration: none; text-align: center; padding: 13px 24px; border-radius: 8px; font-weight: 600; font-size: 15px; margin-bottom: 20px; }}
    .footer {{ font-size: 11px; color: #9ca3af; text-align: center; padding: 16px 32px; border-top: 1px solid #f3f4f6; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="logo">d2c<span>flow</span></div>
    </div>
    <div class="body">
      <h2>You're invited to {payload.workspace_name}</h2>
      <p>You've been invited to join a d2cflow workspace to help manage orders, shipping, and returns.</p>
      <div class="inviter-box">
        <strong>Invited by:</strong> {inviter_line}
      </div>
      <div class="role-badge">{role_label}</div>
      <a href="{accept_url}" class="cta">Accept Invitation →</a>
      <p style="font-size:12px;color:#9ca3af;">
        This invite expires in 7 days. If you have questions, reply directly to this email — it goes to {payload.inviter_email or payload.inviter_name}.
        If you weren't expecting this, you can safely ignore it.
      </p>
    </div>
    <div class="footer">d2cflow · Indian D2C Operating System</div>
  </div>
</body>
</html>
"""

    # FROM = the admin's own email so recipients see it came directly from them
    sender_email = payload.inviter_email or settings.email_from
    sender_display = f"{payload.inviter_name} via d2cflow <{sender_email}>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{payload.inviter_name} invited you to join {payload.workspace_name} on d2cflow"
    msg["From"] = sender_display
    msg["To"] = to_email
    msg["Reply-To"] = f"{payload.inviter_name} <{sender_email}>"
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        # Envelope sender is the SMTP authenticated user; display FROM is admin's email
        smtp.sendmail(settings.smtp_user, [to_email], msg.as_string())


@router.post("/invite")
async def send_invites(payload: InvitePayload):
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Add SMTP_HOST, SMTP_USER, and SMTP_PASSWORD to your .env file."
        )

    if not payload.inviter_email and not settings.email_from:
        raise HTTPException(
            status_code=400,
            detail="Admin email address is missing. Set your contact email in Settings → Brand Profile before sending invites."
        )

    if not payload.emails:
        raise HTTPException(status_code=400, detail="No email addresses provided")

    sent = []
    failed = []

    for email in payload.emails:
        try:
            _send_invite_email(email, payload, settings)
            sent.append(email)
        except smtplib.SMTPAuthenticationError:
            raise HTTPException(
                status_code=401,
                detail="SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD in .env"
            )
        except smtplib.SMTPRecipientsRefused:
            failed.append({"email": email, "reason": "Recipient refused by server"})
        except Exception as e:
            failed.append({"email": email, "reason": str(e)})

    if not sent and failed:
        raise HTTPException(status_code=500, detail=f"All emails failed: {failed[0]['reason']}")

    return {
        "sent": sent,
        "failed": failed,
        "message": f"{len(sent)} invite(s) sent successfully" + (f", {len(failed)} failed" if failed else ""),
    }
