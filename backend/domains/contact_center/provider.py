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


# Kiracı-bazlı sağlayıcı seçimi — Faz 0 yer-tutucu.
# İleride tenants.contact_center_provider alanından okunacak; gerçek sağlayıcı
# kimlik bilgisi yoksa fail-closed olarak MockProvider'a düşülür (sahte canlı YOK).
_PROVIDER_REGISTRY: dict[str, type[CommunicationProvider]] = {
    "mock": MockProvider,
}


def get_communication_provider(provider_key: str | None = None) -> CommunicationProvider:
    """Sağlayıcı örneği döndürür (fail-closed).

    Faz 0: yalnızca ``mock`` kayıtlı. Bilinmeyen/yapılandırılmamış anahtar
    sessizce canlı sağlayıcıya düşmez — MockProvider'a (transport-yok) döner.
    """
    key = (provider_key or "mock").lower()
    provider_cls = _PROVIDER_REGISTRY.get(key, MockProvider)
    return provider_cls()
