"""
Real messaging provider implementations.
Twilio SMS, SendGrid Email, WhatsApp abstraction.
"""
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from .models import DeliveryStatus, ProviderType

logger = logging.getLogger(__name__)


class BaseProvider:
    """Abstract base for messaging providers."""

    provider_type: str = "base"

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, is_sandbox: bool = False) -> Dict[str, Any]:
        raise NotImplementedError

    async def check_health(self, credentials: dict, is_sandbox: bool = False) -> Dict[str, Any]:
        return {"status": "unknown", "checked_at": datetime.now(timezone.utc).isoformat()}


class TwilioSMSProvider(BaseProvider):
    """Twilio SMS provider."""

    provider_type = ProviderType.TWILIO_SMS.value

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, is_sandbox: bool = False) -> Dict[str, Any]:
        creds = credentials or {}
        account_sid = creds.get("account_sid", "")
        auth_token = creds.get("auth_token", "")
        from_number = creds.get("from_number", "")

        if not account_sid or not auth_token or not from_number:
            return {"success": False, "error": "Missing Twilio credentials", "provider_message_id": None}

        try:
            import httpx
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    auth=(account_sid, auth_token),
                    data={"To": recipient, "From": from_number, "Body": body},
                )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"success": True, "provider_message_id": data.get("sid"), "error": None}
            else:
                return {"success": False, "error": f"Twilio HTTP {resp.status_code}: {resp.text[:200]}", "provider_message_id": None}
        except Exception as e:
            logger.exception("Twilio send error")
            return {"success": False, "error": str(e)[:300], "provider_message_id": None}

    async def check_health(self, credentials: dict, is_sandbox: bool = False) -> Dict[str, Any]:
        account_sid = credentials.get("account_sid", "")
        auth_token = credentials.get("auth_token", "")
        if not account_sid or not auth_token:
            return {"status": "unhealthy", "error": "Missing credentials", "checked_at": datetime.now(timezone.utc).isoformat()}
        try:
            import httpx
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, auth=(account_sid, auth_token))
            healthy = resp.status_code == 200
            return {"status": "healthy" if healthy else "unhealthy", "checked_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200], "checked_at": datetime.now(timezone.utc).isoformat()}


class SendGridEmailProvider(BaseProvider):
    """SendGrid Email provider."""

    provider_type = ProviderType.SENDGRID_EMAIL.value

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, is_sandbox: bool = False) -> Dict[str, Any]:
        creds = credentials or {}
        api_key = creds.get("api_key", "")
        from_email = creds.get("from_email", "noreply@hotel.com")

        if not api_key:
            return {"success": False, "error": "Missing SendGrid API key", "provider_message_id": None}

        try:
            import httpx
            payload = {
                "personalizations": [{"to": [{"email": recipient}]}],
                "from": {"email": from_email},
                "subject": subject or "Hotel Notification",
                "content": [{"type": "text/html", "value": body}],
            }
            if is_sandbox:
                payload["mail_settings"] = {"sandbox_mode": {"enable": True}}

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            if resp.status_code in (200, 202):
                msg_id = resp.headers.get("X-Message-Id", "")
                return {"success": True, "provider_message_id": msg_id, "error": None}
            else:
                return {"success": False, "error": f"SendGrid HTTP {resp.status_code}: {resp.text[:200]}", "provider_message_id": None}
        except Exception as e:
            logger.exception("SendGrid send error")
            return {"success": False, "error": str(e)[:300], "provider_message_id": None}

    async def check_health(self, credentials: dict, is_sandbox: bool = False) -> Dict[str, Any]:
        api_key = credentials.get("api_key", "")
        if not api_key:
            return {"status": "unhealthy", "error": "Missing API key", "checked_at": datetime.now(timezone.utc).isoformat()}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.sendgrid.com/v3/scopes",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            healthy = resp.status_code == 200
            return {"status": "healthy" if healthy else "unhealthy", "checked_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200], "checked_at": datetime.now(timezone.utc).isoformat()}


class WhatsAppProvider(BaseProvider):
    """WhatsApp Business API provider abstraction (Meta Cloud API)."""

    provider_type = ProviderType.WHATSAPP.value

    async def send(self, recipient: str, body: str, subject: Optional[str] = None,
                   credentials: dict = None, is_sandbox: bool = False) -> Dict[str, Any]:
        creds = credentials or {}
        access_token = creds.get("access_token", "")
        phone_number_id = creds.get("phone_number_id", "")

        if not access_token or not phone_number_id:
            return {"success": False, "error": "Missing WhatsApp credentials", "provider_message_id": None}

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
            if resp.status_code in (200, 201):
                data = resp.json()
                msg_id = data.get("messages", [{}])[0].get("id", "")
                return {"success": True, "provider_message_id": msg_id, "error": None}
            else:
                return {"success": False, "error": f"WhatsApp HTTP {resp.status_code}: {resp.text[:200]}", "provider_message_id": None}
        except Exception as e:
            logger.exception("WhatsApp send error")
            return {"success": False, "error": str(e)[:300], "provider_message_id": None}

    async def check_health(self, credentials: dict, is_sandbox: bool = False) -> Dict[str, Any]:
        access_token = credentials.get("access_token", "")
        if not access_token:
            return {"status": "unhealthy", "error": "Missing access token", "checked_at": datetime.now(timezone.utc).isoformat()}
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
