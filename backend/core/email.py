"""Generic email helper using Resend (https://resend.com).

Falls back to logging the email body to the console when RESEND_API_KEY is not
configured, which keeps development workflows usable without a real provider.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_FROM = os.environ.get("RESEND_FROM", "Syroce <onboarding@resend.dev>")


def _frontend_base_url() -> str:
    """Return the public frontend URL for building links inside emails."""
    candidates = [
        os.environ.get("FRONTEND_URL"),
        os.environ.get("PUBLIC_APP_URL"),
        os.environ.get("REPLIT_DEV_DOMAIN") and f"https://{os.environ['REPLIT_DEV_DOMAIN']}",
        "http://localhost:5000",
    ]
    return next((c for c in candidates if c), "http://localhost:5000")


async def send_email(
    to: str,
    subject: str,
    html: str,
    *,
    text: Optional[str] = None,
    from_addr: Optional[str] = None,
) -> dict:
    """Send a transactional email.

    Returns a dict with at least `{"sent": bool, "provider": str, "id"?: str}`.
    Never raises – on failure it logs and returns ``sent=False`` so callers can
    keep using a graceful "if email is registered…" response pattern.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    sender = from_addr or DEFAULT_FROM

    if not api_key:
        logger.warning(
            "[email] RESEND_API_KEY missing — printing email instead.\n"
            "    To: %s\n    Subject: %s\n    Body:\n%s",
            to,
            subject,
            html,
        )
        return {"sent": False, "provider": "console"}

    try:
        import resend  # local import keeps app boot fast when not used

        resend.api_key = api_key
        params = {
            "from": sender,
            "to": [to] if isinstance(to, str) else list(to),
            "subject": subject,
            "html": html,
        }
        if text:
            params["text"] = text
        result = resend.Emails.send(params)
        msg_id = (result or {}).get("id") if isinstance(result, dict) else None
        logger.info("[email] Resend sent to=%s id=%s subject=%r", to, msg_id, subject)
        return {"sent": True, "provider": "resend", "id": msg_id}
    except Exception as exc:  # noqa: BLE001 — we want to never crash auth flow
        logger.exception("[email] Resend send failed: %s", exc)
        return {"sent": False, "provider": "resend", "error": str(exc)}


def render_password_reset_email(
    *,
    name: Optional[str],
    reset_link: str,
    code: str,
    expires_in_minutes: int = 30,
) -> tuple[str, str]:
    """Return (subject, html) for the password reset email."""
    subject = "Syroce şifre sıfırlama"
    greeting = f"Merhaba {name}," if name else "Merhaba,"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #111827;">
      <div style="text-align:center; margin-bottom:24px;">
        <h1 style="margin:0; font-size:22px; color:#4f46e5;">Syroce</h1>
        <p style="margin:4px 0 0; font-size:13px; color:#6b7280;">Otel Yönetim Platformu</p>
      </div>
      <h2 style="font-size:18px; margin:0 0 12px;">Şifrenizi sıfırlayın</h2>
      <p style="font-size:14px; line-height:1.6; margin:0 0 16px;">{greeting}</p>
      <p style="font-size:14px; line-height:1.6; margin:0 0 20px;">
        Aşağıdaki butona tıklayarak yeni bir şifre belirleyebilirsiniz. Bu bağlantı
        <strong>{expires_in_minutes} dakika</strong> içinde geçersiz olur.
      </p>
      <p style="text-align:center; margin:28px 0;">
        <a href="{reset_link}" style="background:#4f46e5; color:#ffffff; padding:12px 24px; border-radius:8px; text-decoration:none; font-weight:600; font-size:14px;">
          Şifremi Sıfırla
        </a>
      </p>
      <p style="font-size:13px; color:#6b7280; line-height:1.6; margin:0 0 8px;">
        Buton çalışmazsa şu adresi tarayıcınıza yapıştırın:
      </p>
      <p style="font-size:12px; word-break:break-all; color:#4f46e5; margin:0 0 24px;">
        <a href="{reset_link}" style="color:#4f46e5;">{reset_link}</a>
      </p>
      <div style="border-top:1px solid #e5e7eb; padding-top:16px; font-size:12px; color:#6b7280;">
        Alternatif olarak şu doğrulama kodunu kullanabilirsiniz:
        <div style="margin-top:8px; font-family: monospace; font-size:18px; letter-spacing:4px; color:#111827; font-weight:600;">{code}</div>
      </div>
      <p style="font-size:12px; color:#9ca3af; margin-top:24px;">
        Bu isteği siz yapmadıysanız bu e-postayı yok sayabilirsiniz.
      </p>
    </div>
    """
    return subject, html
