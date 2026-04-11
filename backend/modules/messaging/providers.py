"""
Messaging providers: Direct SMTP Email + Meta WhatsApp Business API.
No third-party intermediaries (no SendGrid, no Twilio).
Supports sandbox/test/live modes.
"""
import logging
import smtplib
import time
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .models import ProviderType

logger = logging.getLogger(__name__)


class ProviderMode:
    LIVE = "live"
    SANDBOX = "sandbox"
    TEST = "test"


class BaseProvider:
    provider_type: str = "base"

    async def send(self, recipient: str, body: str, subject: str | None = None,
                   credentials: dict = None, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        raise NotImplementedError

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        return {"status": "unknown", "checked_at": datetime.now(UTC).isoformat()}

    def classify_error(self, error_msg: str) -> str:
        lower = error_msg.lower() if error_msg else ""
        if "auth" in lower or "credential" in lower or "401" in lower or "403" in lower or "535" in lower:
            return "authentication_error"
        if "rate" in lower or "429" in lower or "throttl" in lower:
            return "rate_limit"
        if "invalid" in lower or "not found" in lower or "404" in lower or "550" in lower:
            return "invalid_recipient"
        if "timeout" in lower:
            return "timeout"
        if "bounce" in lower:
            return "bounce"
        return "unknown_error"


class SMTPEmailProvider(BaseProvider):
    """Direct SMTP Email provider — kendi mail sunucunuz uzerinden gonderim."""

    provider_type = ProviderType.SMTP_EMAIL.value

    async def send(self, recipient: str, body: str, subject: str | None = None,
                   credentials: dict = None, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        creds = credentials or {}
        smtp_host = creds.get("smtp_host", "")
        smtp_port = int(creds.get("smtp_port", 587))
        smtp_username = creds.get("smtp_username", "")
        smtp_password = creds.get("smtp_password", "")
        from_email = creds.get("from_email", "")
        from_name = creds.get("from_name", "Otel")
        use_tls = creds.get("use_tls", True)

        if mode == ProviderMode.TEST or mode == ProviderMode.SANDBOX:
            return {
                "success": True,
                "provider_message_id": f"sandbox_{int(time.time())}",
                "error": None,
                "mode": mode,
                "latency_ms": 5,
                "note": f"[SANDBOX] Email {recipient} adresine gonderildi (simule)",
            }

        if not smtp_host or not smtp_username or not smtp_password or not from_email:
            return {
                "success": False,
                "error": "SMTP yapilandirmasi eksik (host, username, password, from_email gerekli)",
                "provider_message_id": None,
                "error_class": "authentication_error",
            }

        start = time.time()
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject or "Otel Bilgilendirme"
            msg["From"] = f"{from_name} <{from_email}>"
            msg["To"] = recipient

            # Check if body looks like HTML
            if "<html" in body.lower() or "<div" in body.lower() or "<p>" in body.lower():
                msg.attach(MIMEText(body, "html", "utf-8"))
            else:
                msg.attach(MIMEText(body, "plain", "utf-8"))

            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            if use_tls:
                server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(from_email, recipient, msg.as_string())
            server.quit()

            latency_ms = round((time.time() - start) * 1000, 2)
            return {
                "success": True,
                "provider_message_id": f"smtp_{int(time.time())}",
                "error": None,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            logger.exception("SMTP send error")
            err_str = str(e)[:300]
            return {
                "success": False,
                "error": err_str,
                "provider_message_id": None,
                "error_class": self.classify_error(err_str),
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        if mode in (ProviderMode.TEST, ProviderMode.SANDBOX):
            return {"status": "healthy", "mode": mode, "checked_at": datetime.now(UTC).isoformat()}
        smtp_host = credentials.get("smtp_host", "")
        smtp_port = int(credentials.get("smtp_port", 587))
        smtp_username = credentials.get("smtp_username", "")
        smtp_password = credentials.get("smtp_password", "")
        if not smtp_host or not smtp_username:
            return {"status": "unhealthy", "error": "SMTP bilgileri eksik", "checked_at": datetime.now(UTC).isoformat()}
        try:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.quit()
            return {"status": "healthy", "checked_at": datetime.now(UTC).isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200], "checked_at": datetime.now(UTC).isoformat()}


class WhatsAppProvider(BaseProvider):
    """Meta WhatsApp Business Cloud API — dogrudan Meta API, araci yok."""

    provider_type = ProviderType.WHATSAPP.value

    async def send(self, recipient: str, body: str, subject: str | None = None,
                   credentials: dict = None, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        creds = credentials or {}
        access_token = creds.get("access_token", "")
        phone_number_id = creds.get("phone_number_id", "")

        if mode == ProviderMode.TEST or mode == ProviderMode.SANDBOX:
            return {
                "success": True,
                "provider_message_id": f"sandbox_wa_{int(time.time())}",
                "error": None,
                "mode": mode,
                "latency_ms": 8,
                "note": f"[SANDBOX] WhatsApp {recipient} numarasina gonderildi (simule)",
            }

        if not access_token or not phone_number_id:
            return {
                "success": False,
                "error": "WhatsApp API bilgileri eksik (access_token ve phone_number_id gerekli)",
                "provider_message_id": None,
                "error_class": "authentication_error",
            }

        start = time.time()
        try:
            import httpx
            url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": body},
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json=payload,
                )
            latency_ms = round((time.time() - start) * 1000, 2)
            if resp.status_code in (200, 201):
                data = resp.json()
                msg_id = data.get("messages", [{}])[0].get("id", "")
                return {"success": True, "provider_message_id": msg_id, "error": None, "latency_ms": latency_ms}
            else:
                err = f"WhatsApp HTTP {resp.status_code}: {resp.text[:200]}"
                return {"success": False, "error": err, "provider_message_id": None,
                        "error_class": self.classify_error(err), "latency_ms": latency_ms}
        except Exception as e:
            logger.exception("WhatsApp send error")
            err_str = str(e)[:300]
            return {"success": False, "error": err_str, "provider_message_id": None,
                    "error_class": self.classify_error(err_str),
                    "latency_ms": round((time.time() - start) * 1000, 2)}

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        if mode in (ProviderMode.TEST, ProviderMode.SANDBOX):
            return {"status": "healthy", "mode": mode, "checked_at": datetime.now(UTC).isoformat()}
        access_token = credentials.get("access_token", "")
        phone_number_id = credentials.get("phone_number_id", "")
        if not access_token or not phone_number_id:
            return {"status": "unhealthy", "error": "WhatsApp API bilgileri eksik", "checked_at": datetime.now(UTC).isoformat()}
        try:
            import httpx
            url = f"https://graph.facebook.com/v21.0/{phone_number_id}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
            return {"status": "healthy" if resp.status_code == 200 else "unhealthy",
                    "checked_at": datetime.now(UTC).isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200], "checked_at": datetime.now(UTC).isoformat()}


# ── Provider registry ──
PROVIDER_MAP = {
    ProviderType.SMTP_EMAIL.value: SMTPEmailProvider(),
    ProviderType.WHATSAPP.value: WhatsAppProvider(),
}

# Channel -> preferred provider type
CHANNEL_PROVIDER_MAP = {
    "email": ProviderType.SMTP_EMAIL.value,
    "whatsapp": ProviderType.WHATSAPP.value,
}

# Fallback chain: if primary channel fails, try these
FALLBACK_CHAIN = {
    "whatsapp": ["email"],
    "email": [],
}
