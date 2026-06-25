"""Syroce Contact Center — pluggable communication provider adapter (Faz 0).

``messaging_gateway`` desenini aynalar: sağlayıcı-bağımsız soyut arayüz +
kiracı-bazlı seçim. Faz 0'da YALNIZCA ``MockProvider`` kayıtlıdır; gerçek
transport (WhatsApp Cloud API, Twilio, on-prem PBX) bağlı DEĞİL.

Doktrin (fail-closed, no fake-green):
- Mock sağlayıcı giden mesajı GÖNDERMİŞ gibi davranmaz — ``send_message``
  açıkça ``success=False`` / ``status="not_configured"`` döner.
- Gerçek sağlayıcı istenip kimlik bilgisi yoksa sessizce canlıya geçilmez;
  fail-closed olarak mock'a düşülür.
- Telefon/medya gibi PII asla loglanmaz (httpx token-leak dersi); yalnızca
  kanal ve uzunluk gibi PII-içermeyen alanlar loglanır.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class CommunicationProviderError(Exception):
    """Sağlayıcı yapılandırılmamış / transport kullanılamıyor."""


class CommunicationProvider:
    """Soyut iletişim sağlayıcı arayüzü (WhatsApp/voice/web/social/email).

    Faz 1+ gerçek sağlayıcılar bu sözleşmeyi uygular.
    """
    provider_name: str = "base"
    supports_inbound: bool = False
    supports_outbound: bool = False

    async def send_message(
        self,
        *,
        to_hash: str,
        channel: str,
        body: str,
        template_vars: dict | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def check_health(self) -> dict[str, Any]:
        return {"provider": self.provider_name, "status": "unknown"}


class MockProvider(CommunicationProvider):
    """Faz 0 yer-tutucu sağlayıcı — gerçek transport YOK.

    ``send_message`` gönderim YAPMAZ: fail-closed ``not_configured`` döner,
    böylece hiçbir çağıran sahte başarı (fake-green) alamaz. Yalnızca
    iskelet/health amaçlıdır.
    """
    provider_name = "mock"
    supports_inbound = False
    supports_outbound = False

    async def send_message(
        self,
        *,
        to_hash: str,
        channel: str,
        body: str,
        template_vars: dict | None = None,
    ) -> dict[str, Any]:
        # PII loglanmaz: yalnızca kanal ve gövde uzunluğu.
        logger.info(
            "[CONTACT-CENTER][MOCK] outbound suppressed channel=%s len=%d "
            "(transport not configured)",
            channel,
            len(body or ""),
        )
        return {
            "success": False,
            "provider": self.provider_name,
            "mode": "mock",
            "status": "not_configured",
            "detail": "Contact Center transport henüz bağlı değil (Faz 1).",
        }

    async def check_health(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "status": "mock",
            "has_credentials": False,
            "supports_inbound": self.supports_inbound,
            "supports_outbound": self.supports_outbound,
        }


class WhatsAppCloudProvider(CommunicationProvider):
    """Faz 1 gerçek WhatsApp sağlayıcısı — MEVCUT transport'a köprü.

    Transport'u ÇOĞALTMAZ: kiracı kimlik bilgisini ``messaging_provider_configs``
    üzerinden çözüp ``modules.messaging.providers.WhatsAppProvider`` (Meta Cloud
    API) üzerinden gönderir. Kimlik bilgisi yoksa fail-closed ``not_configured``
    döner; ASLA sahte başarı üretmez; telefon/gövde gibi PII'yi ASLA loglamaz.

    Gerçek gönderim kiracı bağlamı gerektirdiği için ``send_whatsapp`` ile yapılır
    (yetki-kapılı uç tarafından kiracı + çözülmüş alıcı ile çağrılır). Soyut
    ``send_message`` sözleşmesi jenerik registry yolundan sahte gönderim
    yapılamasın diye fail-closed bırakılır.
    """

    provider_name = "whatsapp_cloud"
    supports_inbound = True
    supports_outbound = True

    async def send_message(
        self,
        *,
        to_hash: str,
        channel: str,
        body: str,
        template_vars: dict | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "[CONTACT-CENTER][WHATSAPP] generic send_message reddedildi "
            "(kiracı bağlamı gerekir) channel=%s len=%d",
            channel,
            len(body or ""),
        )
        return {
            "success": False,
            "provider": self.provider_name,
            "status": "context_required",
            "detail": "Gönderim için kiracı bağlamı gerekir (send_whatsapp).",
        }

    @staticmethod
    def _resolve_mode(cfg: dict) -> str:
        from modules.messaging.providers import ProviderMode

        if cfg.get("is_sandbox"):
            return ProviderMode.SANDBOX
        if cfg.get("mode") == "test":
            return ProviderMode.TEST
        return ProviderMode.LIVE

    async def _load_config(self, db, tenant_id: str) -> dict | None:
        if db is None or not tenant_id:
            return None
        return await db.messaging_provider_configs.find_one(
            {"tenant_id": tenant_id, "provider_type": "whatsapp", "enabled": True},
            {"_id": 0},
        )

    async def send_whatsapp(
        self,
        *,
        db,
        tenant_id: str,
        recipient: str,
        body: str | None = None,
        in_session: bool = True,
        template_name: str | None = None,
        language_code: str = "tr",
        template_components: list | None = None,
    ) -> dict[str, Any]:
        """Çözülmüş alıcıya WhatsApp gönderir (mevcut transport'a delege).

        24 saatlik konuşma penceresi açıkken (``in_session``) serbest metin;
        kapalıyken onaylı template (HSM) gerekir. Fail-closed: yapılandırma yoksa
        ``not_configured``; pencere kapalı ve template yoksa ``session_expired``.
        """
        cfg = await self._load_config(db, tenant_id)
        if not cfg:
            return {
                "success": False,
                "provider": self.provider_name,
                "status": "not_configured",
                "detail": "WhatsApp sağlayıcısı bu kiracı için yapılandırılmadı.",
            }

        from modules.messaging.providers import PROVIDER_MAP
        from modules.messaging.service import _decrypt_provider_creds

        creds = _decrypt_provider_creds(cfg.get("credentials_encrypted", {}) or {}, "whatsapp")
        mode = self._resolve_mode(cfg)
        wap = PROVIDER_MAP.get("whatsapp")
        if wap is None:
            return {
                "success": False,
                "provider": self.provider_name,
                "status": "transport_unavailable",
                "detail": "WhatsApp transport kullanılamıyor.",
            }

        if in_session and body:
            result = await wap.send(recipient, body, credentials=creds, mode=mode)
        else:
            if not template_name:
                return {
                    "success": False,
                    "provider": self.provider_name,
                    "status": "session_expired",
                    "detail": "24 saatlik pencere kapalı; onaylı template (HSM) gerekir.",
                }
            result = await wap.send_template(
                recipient,
                template_name,
                language_code,
                template_components,
                creds,
                mode,
            )
        result.setdefault("provider", self.provider_name)
        return result

    async def check_health(self, *, db=None, tenant_id=None) -> dict[str, Any]:
        cfg = await self._load_config(db, tenant_id)
        if db is None or not tenant_id:
            status = "unknown"
        else:
            status = "configured" if cfg else "not_configured"
        return {
            "provider": self.provider_name,
            "status": status,
            "supports_inbound": self.supports_inbound,
            "supports_outbound": self.supports_outbound,
        }


# Kiracı-bazlı sağlayıcı seçimi.
# Faz 1: ``whatsapp`` artık gerçek (ancak fail-closed) sağlayıcıya çözülür;
# bilinmeyen/yapılandırılmamış anahtar HÂLÂ sessizce canlıya geçmez —
# MockProvider'a (transport-yok) düşülür (sahte canlı YOK).
_PROVIDER_REGISTRY: dict[str, type[CommunicationProvider]] = {
    "mock": MockProvider,
    "whatsapp": WhatsAppCloudProvider,
    "whatsapp_cloud": WhatsAppCloudProvider,
}


def get_communication_provider(provider_key: str | None = None) -> CommunicationProvider:
    """Sağlayıcı örneği döndürür (fail-closed).

    Bilinmeyen/yapılandırılmamış anahtar sessizce canlı sağlayıcıya düşmez —
    MockProvider'a (transport-yok) döner. ``whatsapp`` Faz 1'de gerçek (fail-closed)
    sağlayıcıya çözülür; kimlik bilgisi yoksa ``not_configured`` döner.
    """
    key = (provider_key or "mock").lower()
    provider_cls = _PROVIDER_REGISTRY.get(key, MockProvider)
    return provider_cls()
