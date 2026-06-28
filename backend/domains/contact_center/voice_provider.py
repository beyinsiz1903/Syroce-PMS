"""Contact Center — Faz 2 Twilio Voice sağlayıcısı (fail-closed).

Sorumluluklar:
- ``generate_access_token``: WebRTC softphone için kısa-ömürlü AccessToken üretir
  (VoiceGrant). Kimlik bilgisi yoksa / SDK kurulu değilse ``not_configured`` döner —
  ASLA sahte token üretmez.
- ``build_inbound_twiml``: gelen çağrıyı ajan client kimliğine bağlayan TwiML üretir
  (kayıt açık). TwiML XML elle ve güvenli kaçışla kurulur; twilio SDK kurulu olmasa
  da gelen çağrı yanıtı bozulmaz.
- ``validate_signature``: gelen Twilio webhook'unun gerçekliğini ``X-Twilio-Signature``
  ile doğrular. Doğrulayamıyorsa (yapılandırma/SDK yok) fail-closed ``False`` döner —
  doğrulanmamış istek ASLA güvenilmez.

Doktrin: telefon/medya/sır gibi PII ASLA loglanmaz; yalnızca PII'siz durum alanları.
"""

from __future__ import annotations

import logging
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from domains.contact_center.voice_config import (
    get_twilio_voice_config,
    token_ttl_seconds,
)

logger = logging.getLogger(__name__)


class TwilioVoiceProvider:
    """Twilio Voice adaptörü (fail-closed)."""

    provider_name = "twilio_voice"

    def __init__(self):
        self.config = get_twilio_voice_config()

    # ── AccessToken (giden/gelen WebRTC) ───────────────────────────────

    def generate_access_token(self, *, identity: str, ttl: int | None = None) -> dict[str, Any]:
        """Softphone için Twilio AccessToken üretir.

        ``identity`` kiracı-kapsamlı olmalı (örn. ``"<tenant_id>:<user_id>"``) ki
        gelen çağrı yalnızca doğru kiracının ajanına yönlendirilebilsin. Fail-closed:
        kimlik bilgisi yoksa ``not_configured``, SDK yoksa ``transport_unavailable``.
        """
        cfg = self.config
        if not cfg.has_credentials:
            return {
                "success": False,
                "status": "not_configured",
                "detail": "Twilio Voice bu ortamda yapılandırılmadı.",
            }
        if not identity:
            return {
                "success": False,
                "status": "invalid_identity",
                "detail": "Token için kiracı-kapsamlı kimlik gerekli.",
            }
        try:
            from twilio.jwt.access_token import AccessToken
            from twilio.jwt.access_token.grants import VoiceGrant
        except ImportError:
            logger.warning("[CC-VOICE] twilio SDK kurulu değil — token üretimi fail-closed")
            return {
                "success": False,
                "status": "transport_unavailable",
                "detail": "twilio SDK kurulu değil.",
            }

        effective_ttl = ttl if (ttl and 60 <= ttl <= 86400) else token_ttl_seconds()
        token = AccessToken(
            cfg.account_sid,
            cfg.api_key_sid,
            cfg.api_key_secret,
            identity=identity,
            ttl=effective_ttl,
        )
        token.add_grant(
            VoiceGrant(
                outgoing_application_sid=cfg.twiml_app_sid,
                incoming_allow=True,
            )
        )
        return {
            "success": True,
            "status": "ok",
            "token": token.to_jwt(),
            "identity": identity,
            "ttl": effective_ttl,
        }

    # ── Gelen çağrı TwiML ──────────────────────────────────────────────

    def build_inbound_twiml(
        self,
        *,
        agent_identity: str | None,
        recording_status_callback: str | None = None,
        dial_status_callback: str | None = None,
        timeout_seconds: int = 25,
    ) -> str:
        """Gelen çağrı için TwiML üretir.

        ``agent_identity`` varsa çağrı o WebRTC client'ına bağlanır (çift-kanal kayıt
        açık); yoksa kibar bir sesli mesajla fail-closed kapanır. XML elle ve güvenli
        kaçışla kurulur (twilio SDK bağımlılığı yok) → gelen çağrı yanıtı her durumda
        geçerli kalır.
        """
        if not agent_identity:
            return self.say_fallback("Şu anda size bağlanamıyoruz. Lütfen daha sonra tekrar arayın.")

        dial_attrs = ['record="record-from-answer-dual"', f'timeout="{int(timeout_seconds)}"']
        if recording_status_callback:
            dial_attrs.append(f"recordingStatusCallback={quoteattr(recording_status_callback)}")
            dial_attrs.append('recordingStatusCallbackEvent="completed"')
        if dial_status_callback:
            dial_attrs.append(f"action={quoteattr(dial_status_callback)}")
            dial_attrs.append('method="POST"')
        dial_attr_str = " ".join(dial_attrs)
        client = escape(agent_identity)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Dial {dial_attr_str}><Client>{client}</Client></Dial></Response>'

    # ── Giden çağrı (click-to-dial) TwiML ──────────────────────────────

    @staticmethod
    def sanitize_dial_number(raw: str | None) -> str | None:
        """İstemciden gelen hedef numarayı E.164'e yakın güvenli biçime indirger.

        Click-to-dial'de hedef numara istemci-kontrollüdür; TwiML enjeksiyonunu ve
        geçersiz çevirmeyi önlemek için yalnızca ``+`` ön eki + 7-15 hane kabul edilir,
        diğer tüm karakterler atılır. Geçersizse ``None`` (fail-closed).
        """
        if not raw:
            return None
        s = str(raw).strip()
        plus = s.startswith("+")
        digits = "".join(ch for ch in s if ch.isdigit())
        if not (7 <= len(digits) <= 15):
            return None
        return ("+" if plus else "") + digits

    def build_outbound_twiml(
        self,
        *,
        to_number: str | None,
        caller_id: str | None,
        recording_status_callback: str | None = None,
        dial_status_callback: str | None = None,
        timeout_seconds: int = 30,
    ) -> str:
        """Giden çağrı (ajan → misafir) için TwiML üretir.

        ``to_number`` istemciden gelir (sanitize edilir); ``caller_id`` ise kiracının
        sunucu-tarafı eşlenmiş Twilio numarasıdır (istemci geçemez). İkisinden biri
        eksik/geçersizse güvenli sesli fallback döner (fail-closed). Kayıt gelen çağrı
        ile aynı çift-kanal boru hattını kullanır. XML elle ve güvenli kaçışla kurulur.
        """
        sanitized = self.sanitize_dial_number(to_number)
        if not sanitized or not caller_id:
            return self.say_fallback("Çağrı başlatılamadı. Lütfen numarayı kontrol edin.")
        dial_attrs = [
            'record="record-from-answer-dual"',
            f'timeout="{int(timeout_seconds)}"',
            f"callerId={quoteattr(caller_id)}",
        ]
        if recording_status_callback:
            dial_attrs.append(f"recordingStatusCallback={quoteattr(recording_status_callback)}")
            dial_attrs.append('recordingStatusCallbackEvent="completed"')
        if dial_status_callback:
            dial_attrs.append(f"action={quoteattr(dial_status_callback)}")
            dial_attrs.append('method="POST"')
        dial_attr_str = " ".join(dial_attrs)
        number = escape(sanitized)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Dial {dial_attr_str}><Number>{number}</Number></Dial></Response>'

    @staticmethod
    def say_fallback(message: str, *, language: str = "tr-TR") -> str:
        """PII içermeyen güvenli bir sesli-mesaj TwiML'i (fail-closed yanıt)."""
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Say language="{escape(language)}">{escape(message)}</Say><Hangup/></Response>'

    # ── Webhook imza doğrulama ─────────────────────────────────────────

    def validate_signature(self, *, url: str, params: dict[str, Any], signature: str) -> bool:
        """Gelen Twilio webhook imzasını doğrular (fail-closed).

        Yapılandırma/SDK yoksa ya da imza yoksa ``False`` döner — doğrulanmamış
        çağrı asla işlenmez (spoofing savunması).
        """
        cfg = self.config
        if not cfg.can_validate_signatures or not signature:
            return False
        try:
            from twilio.request_validator import RequestValidator
        except ImportError:
            logger.warning("[CC-VOICE] twilio SDK kurulu değil — imza doğrulanamıyor (fail-closed)")
            return False
        try:
            return bool(RequestValidator(cfg.auth_token).validate(url, params, signature))
        except Exception:
            # İmza doğrulama hiçbir koşulda raise etmemeli → fail-closed reddet.
            logger.warning("[CC-VOICE] imza doğrulama hatası (fail-closed reddedildi)")
            return False
