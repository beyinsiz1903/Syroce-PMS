"""
Messaging providers: Direct SMTP Email + Meta WhatsApp Business API.
No third-party intermediaries (no SendGrid, no Twilio).
Supports sandbox/test/live modes.
"""

import asyncio
import logging
import os
import smtplib
import ssl
import time
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .meta_diagnostics import meta_error_diagnostics
from .models import ProviderType

logger = logging.getLogger(__name__)


class ProviderMode:
    LIVE = "live"
    SANDBOX = "sandbox"
    TEST = "test"


class BaseProvider:
    provider_type: str = "base"

    async def send(self, recipient: str, body: str, subject: str | None = None, credentials: dict = None, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
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
        if "timeout" in lower or "timed out" in lower:
            return "timeout"
        if "bounce" in lower:
            return "bounce"
        return "unknown_error"


class SMTPEmailProvider(BaseProvider):
    """Direct SMTP Email provider — kendi mail sunucunuz uzerinden gonderim."""

    provider_type = ProviderType.SMTP_EMAIL.value

    async def send(self, recipient: str, body: str, subject: str | None = None, credentials: dict = None, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        creds = credentials or {}
        if creds.get("email_transport") == "zoho_api" and mode == ProviderMode.LIVE:
            from .zoho_mail import send

            return await send(recipient, body, subject, creds)
        if mode in (ProviderMode.TEST, ProviderMode.SANDBOX):
            return {
                "success": True, "provider_message_id": f"sandbox_{time.time_ns()}",
                "error": None, "mode": mode, "latency_ms": 5,
                "note": "[SANDBOX] E-posta simüle edildi; gerçek gönderim yapılmadı.",
            }
        # DNS, connect, STARTTLS and SMTP are synchronous. Never block every
        # request handled by this ASGI event loop during the SMTP timeout.
        return await asyncio.to_thread(self._send_smtp, recipient, body, subject, creds)

    @staticmethod
    def _open_smtp(creds: dict, timeout: int):
        from integrations.xchange.safety import assert_safe_host

        host = creds.get("smtp_host", "")
        port = int(creds.get("smtp_port", 587))
        pinned_ip = assert_safe_host(host, port)
        server = smtplib.SMTP(pinned_ip, port, timeout=timeout)
        # The TCP destination remains DNS-pinned. Certificate verification/SNI
        # must use the configured hostname, not that public IP address.
        server._host = host
        return server

    def _smtp_failure(self, exc: Exception, stage: str) -> dict:
        from integrations.xchange.safety import EgressDenied

        definitive_rejection = isinstance(exc, (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused))
        unknown = stage == "submit" and not definitive_rejection
        error_class = self.classify_error(str(exc))
        error_code = "smtp_error"
        error = "SMTP işlemi tamamlanamadı. E-posta ayarlarını ve sunucu bağlantısını kontrol edin."
        if isinstance(exc, EgressDenied):
            error_class, error_code = "configuration_error", "smtp_egress_denied"
            error = "SMTP sunucusuna erişim güvenli ağ politikası tarafından engellendi. Sistem yöneticisine başvurun."
        elif isinstance(exc, TimeoutError):
            error_class, error_code = "timeout", f"smtp_{stage}_timeout"
            error = "SMTP bağlantısı zaman aşımına uğradı. Sunucunun dış ağ/SMTP erişimini kontrol edin; SMTP çıkışı kısıtlıysa Zoho HTTPS API kullanın."
        elif isinstance(exc, ssl.SSLError):
            error_class, error_code = "configuration_error", "smtp_tls_error"
            error = "SMTP TLS doğrulaması başarısız. Sunucu adını ve sertifikasını kontrol edin; TLS doğrulamasını kapatmayın."
        elif isinstance(exc, smtplib.SMTPAuthenticationError):
            error_class, error_code = "authentication_error", "smtp_authentication_error"
            error = "SMTP kimlik doğrulaması başarısız. Kullanıcı adı ve uygulama parolasını kontrol edin; bunlar Zoho OAuth anahtarı yerine geçmez."
        elif isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused)):
            error_class, error_code = "invalid_recipient", "smtp_address_rejected"
            error = "SMTP sunucusu gönderen veya alıcı adresini reddetti."
        elif isinstance(exc, smtplib.SMTPResponseException):
            error_class = "temporary_rejection" if 400 <= exc.smtp_code < 500 else "provider_rejection"
            error_code = "smtp_rejected"
            error = "SMTP sunucusu işlemi reddetti. Posta sağlayıcısının gönderim kurallarını kontrol edin."
        elif isinstance(exc, OSError):
            error_class, error_code = "connection_error", "smtp_connection_error"
            error = "SMTP sunucusuna bağlantı kurulamadı. DNS, güvenlik duvarı ve dış ağ erişimini kontrol edin."
        if unknown:
            error_code = "smtp_delivery_unknown"
            error = "SMTP gönderiminin sonucu belirsiz. Çift gönderimi önlemek için yeniden denemeyin; gönderen hesabındaki Gönderilenler kaydını kontrol edin."
        # Do not attach exception locals (message body, recipient, credentials)
        # to Sentry for expected transport/configuration failures.
        logger.warning("SMTP operation failed stage=%s error_class=%s exception=%s", stage, error_class, type(exc).__name__)
        return {"success": False, "outcome_unknown": unknown, "error": error,
                "error_class": error_class, "error_code": error_code, "delivery_stage": stage,
                "retryable": not unknown and error_class not in {"authentication_error", "configuration_error", "invalid_recipient", "provider_rejection"},
                "provider_message_id": None}

    @staticmethod
    def _close_smtp(server):
        if server is not None:
            try:
                server.close()
            except Exception:
                logger.debug("SMTP close failed")

    def _send_smtp(self, recipient: str, body: str, subject: str | None, creds: dict) -> dict:
        smtp_host = creds.get("smtp_host", "")
        smtp_username = creds.get("smtp_username", "")
        smtp_password = creds.get("smtp_password", "")
        from_email = creds.get("from_email", "")
        from_name = creds.get("from_name", "Otel")
        use_tls = creds.get("use_tls", True)

        if not smtp_host or not smtp_username or not smtp_password or not from_email:
            return {
                "success": False,
                "error": "SMTP yapilandirmasi eksik (host, username, password, from_email gerekli)",
                "provider_message_id": None,
                "error_class": "authentication_error",
                "error_code": "smtp_configuration_missing",
                "delivery_stage": "prepare",
                "retryable": False,
            }

        start = time.monotonic()
        server = None
        stage = "prepare"
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

            stage = "connect"
            server = self._open_smtp(creds, timeout=15)
            if use_tls:
                stage = "tls"
                server.starttls(context=ssl.create_default_context())
            stage = "authenticate"
            server.login(smtp_username, smtp_password)
            stage = "submit"
            server.sendmail(from_email, recipient, msg.as_string())
            # A failed QUIT after sendmail acceptance must not turn a delivered
            # message into a retryable failure (which creates duplicates).
            try:
                server.quit()
            except Exception:
                logger.warning("SMTP accepted message but connection teardown failed")

            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return {
                "success": True,
                "provider_message_id": f"smtp_{time.time_ns()}",
                "error": None,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            return {**self._smtp_failure(e, stage), "latency_ms": round((time.monotonic() - start) * 1000, 2)}
        finally:
            self._close_smtp(server)

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        if mode in (ProviderMode.TEST, ProviderMode.SANDBOX):
            return {"status": "healthy", "mode": mode, "checked_at": datetime.now(UTC).isoformat()}
        if credentials.get("email_transport") == "zoho_api":
            from .zoho_mail import check_health

            return {**await check_health(credentials), "checked_at": datetime.now(UTC).isoformat()}
        return await asyncio.to_thread(self._check_smtp_health, credentials)

    def _check_smtp_health(self, credentials: dict) -> dict:
        smtp_host = credentials.get("smtp_host", "")
        smtp_username = credentials.get("smtp_username", "")
        smtp_password = credentials.get("smtp_password", "")
        if not smtp_host or not smtp_username or not smtp_password:
            return {"status": "unhealthy", "error": "SMTP bilgileri eksik", "checked_at": datetime.now(UTC).isoformat()}
        server = None
        stage = "connect"
        try:
            server = self._open_smtp(credentials, timeout=10)
            if credentials.get("use_tls", True):
                stage = "tls"
                server.starttls(context=ssl.create_default_context())
            stage = "authenticate"
            server.login(smtp_username, smtp_password)
            try:
                server.quit()
            except Exception:
                logger.debug("SMTP health connection teardown failed")
            return {"status": "healthy", "checked_at": datetime.now(UTC).isoformat()}
        except Exception as e:
            failure = self._smtp_failure(e, stage)
            return {"status": "unhealthy", "error": failure["error"], "error_class": failure["error_class"],
                    "error_code": failure["error_code"], "checked_at": datetime.now(UTC).isoformat()}
        finally:
            self._close_smtp(server)


class WhatsAppProvider(BaseProvider):
    """Meta WhatsApp Business Cloud API — dogrudan Meta API, araci yok."""

    provider_type = ProviderType.WHATSAPP.value

    async def send(self, recipient: str, body: str, subject: str | None = None, credentials: dict = None, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
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
                return {"success": False, "error": err, "provider_message_id": None, "error_class": self.classify_error(err), "latency_ms": latency_ms}
        except Exception as e:
            logger.exception("WhatsApp send error")
            err_str = str(e)[:300]
            return {"success": False, "error": err_str, "provider_message_id": None, "error_class": self.classify_error(err_str), "latency_ms": round((time.time() - start) * 1000, 2)}

    async def send_template(
        self,
        recipient: str,
        template_name: str,
        language_code: str = "tr",
        components: list | None = None,
        credentials: dict | None = None,
        mode: str = ProviderMode.LIVE,
    ) -> dict[str, Any]:
        """Meta WhatsApp template (HSM) message gönderimi.

        24 saatlik konuşma penceresi dışında veya ilk temas için Meta
        zorunlu olarak onaylı template ister. `components` Meta'nın
        beklediği yapıdadır:
          [{"type": "body", "parameters": [{"type": "text", "text": "..."}]}]
        """
        creds = credentials or {}
        access_token = creds.get("access_token", "")
        phone_number_id = creds.get("phone_number_id", "")

        if mode in (ProviderMode.TEST, ProviderMode.SANDBOX):
            return {
                "success": True,
                "provider_message_id": f"sandbox_wa_tpl_{int(time.time())}",
                "error": None,
                "mode": mode,
                "latency_ms": 8,
                "note": f"[SANDBOX] WhatsApp template '{template_name}' → {recipient}",
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
            template_payload: dict[str, Any] = {
                "name": template_name,
                "language": {"code": language_code},
            }
            if components:
                template_payload["components"] = components
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "template",
                "template": template_payload,
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
                return {"success": bool(msg_id), "outcome_unknown": not bool(msg_id), "provider_message_id": msg_id, "error": None, "latency_ms": latency_ms}
            err = f"WhatsApp template HTTP {resp.status_code}: {resp.text[:200]}"
            return {"success": False, "error": err, "provider_message_id": None, "error_class": self.classify_error(err), "latency_ms": latency_ms, "outcome_unknown": resp.status_code >= 500}
        except Exception as e:
            logger.exception("WhatsApp send_template error")
            err_str = type(e).__name__
            return {"outcome_unknown": True, "success": False, "error": err_str, "provider_message_id": None, "error_class": self.classify_error(err_str), "latency_ms": round((time.time() - start) * 1000, 2)}

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
            if resp.status_code == 200:
                return {"status": "healthy", "checked_at": datetime.now(UTC).isoformat()}
            return {"status": "unhealthy", **meta_error_diagnostics(resp),
                    "checked_at": datetime.now(UTC).isoformat()}
        except httpx.TimeoutException:
            error = "Meta bağlantısı zaman aşımına uğradı. Sunucu ağ bağlantısını kontrol edip yeniden deneyin."
        except httpx.RequestError:
            error = "Sunucudan Meta hizmetine bağlantı kurulamadı. DNS, TLS ve dış ağ erişimini kontrol edin."
        except Exception:
            error = "WhatsApp bağlantı testi tamamlanamadı. Sistem yöneticisine başvurun."
        return {"status": "unhealthy", "error": error, "checked_at": datetime.now(UTC).isoformat()}


class TwilioWhatsAppProvider(BaseProvider):
    provider_type = "twilio_whatsapp"

    async def send(
        self,
        recipient: str,
        body: str,
        subject: str | None = None,
        credentials: dict = None,
        mode: str = ProviderMode.LIVE,
    ) -> dict[str, Any]:
        creds = credentials or {}
        account_sid = creds.get("account_sid") or os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        auth_token = creds.get("auth_token") or os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        from_number = creds.get("from_number") or os.getenv("TWILIO_WHATSAPP_FROM", "").strip()

        if mode == ProviderMode.TEST:
            return {"success": True, "provider_message_id": f"sandbox_wa_{int(time.time())}", "status": "simulated", "delivered": False, "note": "Test modu: Mesaj gerçek WhatsApp’a gönderilmedi."}

        if mode == ProviderMode.SANDBOX:
            from_number = "whatsapp:+14155238886"

        if not account_sid or not auth_token or not from_number:
            return {
                "success": False,
                "error": "Twilio WhatsApp credentials missing.",
                "provider_message_id": None,
                "error_class": "authentication_error",
            }

        sender = from_number
        if not sender.startswith("whatsapp:"):
            sender = f"whatsapp:{sender}"

        to_formatted = recipient
        if not to_formatted.startswith("whatsapp:"):
            to_formatted = f"whatsapp:{to_formatted}"

        start = time.time()
        try:
            from twilio.rest import Client

            client = Client(account_sid, auth_token)

            base = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
            status_callback_url = f"{base}/api/voice/whatsapp/status" if base else None

            kwargs = {"body": body, "from_": sender, "to": to_formatted}
            if status_callback_url:
                kwargs["status_callback"] = status_callback_url

            msg = client.messages.create(**kwargs)
            latency_ms = round((time.time() - start) * 1000, 2)
            return {"success": True, "provider_message_id": msg.sid, "status": "queued", "error": None, "latency_ms": latency_ms}
        except Exception as e:
            logger.exception("Twilio WhatsApp send error")
            err_str = str(e)[:300]
            return {"success": False, "error": err_str, "provider_message_id": None, "error_class": self.classify_error(err_str), "latency_ms": round((time.time() - start) * 1000, 2)}

    async def send_template(
        self,
        recipient: str,
        template_name: str,
        language_code: str = "tr",
        components: list | None = None,
        credentials: dict | None = None,
        mode: str = ProviderMode.LIVE,
    ) -> dict[str, Any]:
        template_bodies = {
            "hello_world": "Hello World",
            "reservation_confirmation": "Rezervasyonunuz onaylanmıştır.",
            "checkin_welcome": "Otelimize hoş geldiniz!",
            "checkout_thank_you": "Bizi tercih ettiğiniz için teşekkür ederiz.",
        }
        body = template_bodies.get(template_name, f"Template: {template_name}")
        return await self.send(recipient=recipient, body=body, credentials=credentials, mode=mode)

    async def check_health(self, credentials: dict, mode: str = ProviderMode.LIVE) -> dict[str, Any]:
        if mode in (ProviderMode.TEST, ProviderMode.SANDBOX):
            return {"status": "healthy", "mode": mode, "checked_at": datetime.now(UTC).isoformat()}
        creds = credentials or {}
        account_sid = creds.get("account_sid") or os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        auth_token = creds.get("auth_token") or os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        if not account_sid or not auth_token:
            return {"status": "unhealthy", "error": "Twilio API bilgileri eksik", "checked_at": datetime.now(UTC).isoformat()}
        try:
            from twilio.rest import Client

            client = Client(account_sid, auth_token)
            client.api.v2010.accounts(account_sid).fetch()
            return {"status": "healthy", "checked_at": datetime.now(UTC).isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200], "checked_at": datetime.now(UTC).isoformat()}


# ── Provider registry ──
PROVIDER_MAP = {
    ProviderType.SMTP_EMAIL.value: SMTPEmailProvider(),
    ProviderType.WHATSAPP.value: WhatsAppProvider(),
    "twilio_whatsapp": TwilioWhatsAppProvider(),
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
