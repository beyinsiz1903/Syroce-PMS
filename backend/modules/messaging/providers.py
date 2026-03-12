"""
Real messaging provider implementations.
Twilio SMS, SendGrid Email, WhatsApp abstraction.
Supports sandbox/test/live modes with credential vault integration.
"""
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from .models import ProviderType

logger = logging.getLogger(__name__)


class ProviderMode:
    LIVE = "live"
    SANDBOX = "sandbox"
    TEST = "test"


class BaseProvider:
    """Abstract base for messaging providers."""

    provider_type: str = "base"

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        raise NotImplementedError

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        return {"status": "unknown", "checked_at": datetime.now(timezone.utc).isoformat()}

    def classify_error(self, error_msg: str) -> str:
        """Classify provider errors for alerting."""
        lower = error_msg.lower() if error_msg else ""
        if "auth" in lower or "credential" in lower or "401" in lower or "403" in lower:
            return "authentication_error"
        if "rate" in lower or "429" in lower or "throttl" in lower:
            return "rate_limit"
        if "invalid" in lower or "not found" in lower or "404" in lower:
            return "invalid_recipient"
        if "timeout" in lower:
            return "timeout"
        if "bounce" in lower:
            return "bounce"
        return "unknown_error"


class TwilioSMSProvider(BaseProvider):
    """Twilio SMS provider — live + sandbox + test modes."""

    provider_type = ProviderType.TWILIO_SMS.value

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        creds = credentials or {}
        account_sid = creds.get("account_sid", "")
        auth_token = creds.get("auth_token", "")
        from_number = creds.get("from_number", "")

        if not account_sid or not auth_token or not from_number:
            return {"success": False, "error": "Missing Twilio credentials",
                    "provider_message_id": None, "error_class": "authentication_error"}

        # Test mode: simulate success without real API call
        if mode == ProviderMode.TEST:
            return {"success": True, "provider_message_id": f"test_{int(time.time())}",
                    "error": None, "mode": "test", "latency_ms": 0}

        start = time.time()
        try:
            import httpx
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    auth=(account_sid, auth_token),
                    data={"To": recipient, "From": from_number, "Body": body},
                )
            latency_ms = round((time.time() - start) * 1000, 2)
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"success": True, "provider_message_id": data.get("sid"),
                        "error": None, "latency_ms": latency_ms}
            else:
                err = f"Twilio HTTP {resp.status_code}: {resp.text[:200]}"
                return {"success": False, "error": err, "provider_message_id": None,
                        "error_class": self.classify_error(err), "latency_ms": latency_ms}
        except Exception as e:
            logger.exception("Twilio send error")
            err_str = str(e)[:300]
            return {"success": False, "error": err_str, "provider_message_id": None,
                    "error_class": self.classify_error(err_str),
                    "latency_ms": round((time.time() - start) * 1000, 2)}

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        if mode == ProviderMode.TEST:
            return {"status": "healthy", "mode": "test", "checked_at": datetime.now(timezone.utc).isoformat()}
        account_sid = credentials.get("account_sid", "")
        auth_token = credentials.get("auth_token", "")
        if not account_sid or not auth_token:
            return {"status": "unhealthy", "error": "Missing credentials",
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        try:
            import httpx
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, auth=(account_sid, auth_token))
            healthy = resp.status_code == 200
            return {"status": "healthy" if healthy else "unhealthy",
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200],
                    "checked_at": datetime.now(timezone.utc).isoformat()}


class SendGridEmailProvider(BaseProvider):
    """SendGrid Email provider — live + sandbox + test modes."""

    provider_type = ProviderType.SENDGRID_EMAIL.value

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        creds = credentials or {}
        api_key = creds.get("api_key", "")
        from_email = creds.get("from_email", "noreply@hotel.com")

        if not api_key:
            return {"success": False, "error": "Missing SendGrid API key",
                    "provider_message_id": None, "error_class": "authentication_error"}

        if mode == ProviderMode.TEST:
            return {"success": True, "provider_message_id": f"test_{int(time.time())}",
                    "error": None, "mode": "test", "latency_ms": 0}

        start = time.time()
        try:
            import httpx
            payload = {
                "personalizations": [{"to": [{"email": recipient}]}],
                "from": {"email": from_email},
                "subject": subject or "Hotel Notification",
                "content": [{"type": "text/html", "value": body}],
            }
            if mode == ProviderMode.SANDBOX:
                payload["mail_settings"] = {"sandbox_mode": {"enable": True}}

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            latency_ms = round((time.time() - start) * 1000, 2)
            if resp.status_code in (200, 202):
                msg_id = resp.headers.get("X-Message-Id", "")
                return {"success": True, "provider_message_id": msg_id,
                        "error": None, "latency_ms": latency_ms}
            else:
                err = f"SendGrid HTTP {resp.status_code}: {resp.text[:200]}"
                return {"success": False, "error": err, "provider_message_id": None,
                        "error_class": self.classify_error(err), "latency_ms": latency_ms}
        except Exception as e:
            logger.exception("SendGrid send error")
            err_str = str(e)[:300]
            return {"success": False, "error": err_str, "provider_message_id": None,
                    "error_class": self.classify_error(err_str),
                    "latency_ms": round((time.time() - start) * 1000, 2)}

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        if mode == ProviderMode.TEST:
            return {"status": "healthy", "mode": "test", "checked_at": datetime.now(timezone.utc).isoformat()}
        api_key = credentials.get("api_key", "")
        if not api_key:
            return {"status": "unhealthy", "error": "Missing API key",
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.sendgrid.com/v3/scopes",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            healthy = resp.status_code == 200
            return {"status": "healthy" if healthy else "unhealthy",
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200],
                    "checked_at": datetime.now(timezone.utc).isoformat()}


class WhatsAppProvider(BaseProvider):
    """WhatsApp Business API provider — live + test modes."""

    provider_type = ProviderType.WHATSAPP.value

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        creds = credentials or {}
        access_token = creds.get("access_token", "")
        phone_number_id = creds.get("phone_number_id", "")

        if not access_token or not phone_number_id:
            return {"success": False, "error": "Missing WhatsApp credentials",
                    "provider_message_id": None, "error_class": "authentication_error"}

        if mode == ProviderMode.TEST:
            return {"success": True, "provider_message_id": f"test_{int(time.time())}",
                    "error": None, "mode": "test", "latency_ms": 0}

        start = time.time()
        try:
            import httpx
            url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
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
                return {"success": True, "provider_message_id": msg_id,
                        "error": None, "latency_ms": latency_ms}
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

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> Dict[str, Any]:
        if mode == ProviderMode.TEST:
            return {"status": "healthy", "mode": "test", "checked_at": datetime.now(timezone.utc).isoformat()}
        access_token = credentials.get("access_token", "")
        if not access_token:
            return {"status": "unhealthy", "error": "Missing access token",
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        return {"status": "healthy", "checked_at": datetime.now(timezone.utc).isoformat()}


# ── Provider registry ──
PROVIDER_MAP = {
    ProviderType.TWILIO_SMS.value: TwilioSMSProvider(),
    ProviderType.SENDGRID_EMAIL.value: SendGridEmailProvider(),
    ProviderType.WHATSAPP.value: WhatsAppProvider(),
}

# Channel → preferred provider type
CHANNEL_PROVIDER_MAP = {
    "sms": ProviderType.TWILIO_SMS.value,
    "email": ProviderType.SENDGRID_EMAIL.value,
    "whatsapp": ProviderType.WHATSAPP.value,
}

# Fallback chain: if primary channel fails, try these in order
FALLBACK_CHAIN = {
    "whatsapp": ["sms", "email"],
    "sms": ["email"],
    "email": [],
}
