"""Generic email helper using Resend (https://resend.com).

Falls back to logging the email body to the console when RESEND_API_KEY is not
configured, which keeps development workflows usable without a real provider.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

DEFAULT_FROM = os.environ.get("RESEND_FROM", "Syroce <onboarding@resend.dev>")

# Lightweight RFC-5322-ish guard: catches the common cases (empty string,
# missing @, whitespace, no TLD, "Name <addr>" with bad addr) BEFORE we hit
# the Resend API. Resend rejects malformed addresses with a hard validation
# error which Sentry then surfaces as a high-priority alert; we'd rather
# log+skip locally than spam Sentry every time a hotel admin row has a
# typo in the email column.
_EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

# Resend (and SES) accept the ``from`` header in two forms only:
#   * a bare address      ->  "noreply@hotel.com"
#   * a display-name form ->  "Syroce <noreply@hotel.com>"
# Anything else (a bare name, an empty value, a malformed address) is rejected
# by Resend with a HARD "Invalid `from` field" validation error that Sentry then
# surfaces as a high-priority alert. We pre-flight the sender with the SAME
# intent as the recipient guard so a misconfigured RESEND_FROM (or a bad caller
# from_addr) is logged + skipped locally instead of paging on every send.
_FROM_NAMED_RE = re.compile(r"^[^<>]+<\s*[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+\s*>$")


def _is_valid_email(addr: str | None) -> bool:
    if not addr or not isinstance(addr, str):
        return False
    return bool(_EMAIL_RE.match(addr.strip()))


def _is_valid_sender(sender: str | None) -> bool:
    """Validate a ``from``/sender value as a bare address or ``Name <addr>``."""
    if not sender or not isinstance(sender, str):
        return False
    s = sender.strip()
    return bool(_EMAIL_RE.match(s) or _FROM_NAMED_RE.match(s))


def _provider() -> str:
    """Choose mail provider. Defaults to resend; switch to ses by setting MAIL_PROVIDER=ses.
    Falls back to resend if ses is requested but AWS keys are missing."""
    p = (os.environ.get("MAIL_PROVIDER") or "").lower()
    if p == "ses" and os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return "ses"
    return "resend"


async def _send_via_ses(*, to: str, subject: str, html: str, text: str | None,
                       sender: str, reply_to: str | None) -> dict:
    """Send a single email via Amazon SES (used when MAIL_PROVIDER=ses)."""
    try:
        import boto3  # type: ignore
        client = boto3.client(
            "ses",
            region_name=os.environ.get("AWS_REGION", "eu-central-1"),
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        body = {"Html": {"Data": html, "Charset": "UTF-8"}}
        if text:
            body["Text"] = {"Data": text, "Charset": "UTF-8"}
        kwargs = {
            "Source": sender,
            "Destination": {"ToAddresses": [to]},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": body,
            },
        }
        if reply_to:
            kwargs["ReplyToAddresses"] = [reply_to]
        result = client.send_email(**kwargs)
        msg_id = result.get("MessageId")
        logger.info("[email] SES sent to=%s id=%s subject=%r", to, msg_id, subject)
        return {"sent": True, "provider": "ses", "id": msg_id}
    except Exception as exc:
        logger.exception("[email] SES send failed: %s", exc)
        return {"sent": False, "provider": "ses", "error": str(exc)}


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
    text: str | None = None,
    from_addr: str | None = None,
    reply_to: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Send a transactional email.

    Returns a dict with at least `{"sent": bool, "provider": str, "id"?: str}`.
    Never raises – on failure it logs and returns ``sent=False`` so callers can
    keep using a graceful "if email is registered…" response pattern.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    sender = from_addr or DEFAULT_FROM

    # Pre-flight: skip obviously malformed recipients so Resend's hard
    # validation error doesn't bubble to Sentry as an alert.
    if not _is_valid_email(to):
        logger.warning("[email] skipping send — invalid recipient %r (subject=%r)", to, subject)
        return {"sent": False, "provider": "skipped", "error": "invalid_recipient"}

    # Pre-flight the sender too: a malformed RESEND_FROM (or caller from_addr)
    # otherwise reaches Resend as a hard "Invalid `from` field" validation error
    # that pages Sentry on EVERY send. We log at WARNING (not ERROR) so the
    # actionable config-fix signal stays in the console without paging — the
    # value must be "email@domain" or "Name <email@domain>".
    if not _is_valid_sender(sender):
        logger.warning(
            "[email] skipping send — invalid sender %r; set RESEND_FROM to "
            "'email@domain' or 'Name <email@domain>' (subject=%r)",
            sender, subject,
        )
        return {"sent": False, "provider": "skipped", "error": "invalid_sender"}

    if _provider() == "ses":
        return await _send_via_ses(to=to, subject=subject, html=html, text=text,
                                    sender=sender, reply_to=reply_to)

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
        if reply_to:
            params["reply_to"] = reply_to
        if attachments:
            # Resend SDK accepts {filename, content} where content is a
            # base64-encoded string OR a list of byte values. We accept both
            # raw bytes and base64-string from callers and normalize here.
            import base64 as _b64
            norm = []
            for a in attachments:
                if not isinstance(a, dict):
                    continue
                fname = str(a.get("filename") or "attachment.bin")
                content = a.get("content")
                if isinstance(content, (bytes, bytearray)):
                    content = _b64.b64encode(bytes(content)).decode("ascii")
                if not content:
                    continue
                item = {"filename": fname, "content": content}
                if a.get("content_type"):
                    item["content_type"] = a["content_type"]
                norm.append(item)
            if norm:
                params["attachments"] = norm
        result = resend.Emails.send(params)
        msg_id = (result or {}).get("id") if isinstance(result, dict) else None
        logger.info("[email] Resend sent to=%s id=%s subject=%r", to, msg_id, subject)
        return {"sent": True, "provider": "resend", "id": msg_id}
    except Exception as exc:  # noqa: BLE001 — we want to never crash auth flow
        logger.exception("[email] Resend send failed: %s", exc)
        return {"sent": False, "provider": "resend", "error": str(exc)}


def render_password_reset_email(
    *,
    name: str | None,
    reset_link: str,
    code: str,
    expires_in_minutes: int = 30,
) -> tuple[str, str]:
    """Return (subject, html) for the password reset email."""
    # Bug CN (architect Round-1 ek bulgu): user.name profil alanından gelir
    # ve raw f-string'e konuyordu — saldırgan profilini `<a href=phish>` yapıp
    # şifre sıfırlama mailine HTML zerk edebilirdi (yardım masası operatörünün
    # in-app preview'ında XSS, veya self-forward sosyal mühendislik). reset_link
    # ve `code` backend-üretimi sabit-format — escape gerekmiyor ama defansif
    # olarak escape ediyoruz.
    from core.mailing_safe import safe_html_value
    escaped_name = safe_html_value(name) if name else None
    escaped_reset_link = safe_html_value(reset_link)
    escaped_code = safe_html_value(code)
    subject = "Syroce şifre sıfırlama"
    greeting = f"Merhaba {escaped_name}," if escaped_name else "Merhaba,"
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
        <a href="{escaped_reset_link}" style="background:#4f46e5; color:#ffffff; padding:12px 24px; border-radius:8px; text-decoration:none; font-weight:600; font-size:14px;">
          Şifremi Sıfırla
        </a>
      </p>
      <p style="font-size:13px; color:#6b7280; line-height:1.6; margin:0 0 8px;">
        Buton çalışmazsa şu adresi tarayıcınıza yapıştırın:
      </p>
      <p style="font-size:12px; word-break:break-all; color:#4f46e5; margin:0 0 24px;">
        <a href="{escaped_reset_link}" style="color:#4f46e5;">{escaped_reset_link}</a>
      </p>
      <div style="border-top:1px solid #e5e7eb; padding-top:16px; font-size:12px; color:#6b7280;">
        Alternatif olarak şu doğrulama kodunu kullanabilirsiniz:
        <div style="margin-top:8px; font-family: monospace; font-size:18px; letter-spacing:4px; color:#111827; font-weight:600;">{escaped_code}</div>
      </div>
      <p style="font-size:12px; color:#9ca3af; margin-top:24px;">
        Bu isteği siz yapmadıysanız bu e-postayı yok sayabilirsiniz.
      </p>
    </div>
    """
    return subject, html
