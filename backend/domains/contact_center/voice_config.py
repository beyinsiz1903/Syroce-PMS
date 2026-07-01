"""Contact Center — Faz 2 sesli softphone (Twilio Voice) yapılandırması.

Doktrin (fail-closed, no fake-green):
- Kimlik bilgileri YALNIZCA ortam değişkeninden (DigitalOcean Secrets / deploy env)
  okunur; eksikse ``has_credentials``/``is_configured`` False döner ve çağıran
  ``not_configured`` ile sessizce canlıya GEÇMEZ.
- Sır değerleri ASLA loglanmaz; bu modül yalnızca varlık (bool) bilgisini açar.
- Çağrı kaydı deposu ayrı bir S3/Spaces bucket'tır (operatör seçimi); yapılandırma
  yoksa kayıt boru hattı fail-closed çalışır (kayıt indirilmez/saklanmaz).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_TOKEN_TTL_SECONDS = 3600
_DEFAULT_RETENTION_DAYS = 90


@dataclass(frozen=True)
class TwilioVoiceConfig:
    """Twilio Voice (WebRTC softphone) kimlik bilgileri — salt-okunur."""

    account_sid: str
    api_key_sid: str
    api_key_secret: str
    twiml_app_sid: str
    auth_token: str

    @property
    def has_credentials(self) -> bool:
        """AccessToken üretebilmek için gereken asgari kümeyi taşıyor mu?"""
        return all(
            [
                self.account_sid,
                self.api_key_sid,
                self.api_key_secret,
                self.twiml_app_sid,
            ]
        )

    @property
    def can_validate_signatures(self) -> bool:
        """Gelen webhook imzasını (X-Twilio-Signature) doğrulayabilir mi?"""
        return bool(self.account_sid and self.auth_token)


def get_twilio_voice_config() -> TwilioVoiceConfig:
    """Ortamdan Twilio Voice yapılandırmasını okur (fail-closed)."""
    return TwilioVoiceConfig(
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
        api_key_sid=os.getenv("TWILIO_API_KEY_SID", "").strip(),
        api_key_secret=os.getenv("TWILIO_API_KEY_SECRET", "").strip(),
        twiml_app_sid=os.getenv("TWILIO_TWIML_APP_SID", "").strip(),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
    )


def token_ttl_seconds() -> int:
    """AccessToken geçerlilik süresi (geçersiz değerde güvenli varsayılan)."""
    raw = os.getenv("TWILIO_VOICE_TOKEN_TTL", str(_DEFAULT_TOKEN_TTL_SECONDS))
    try:
        val = int(raw)
        return val if 60 <= val <= 86400 else _DEFAULT_TOKEN_TTL_SECONDS
    except (TypeError, ValueError):
        return _DEFAULT_TOKEN_TTL_SECONDS


@dataclass(frozen=True)
class RecordingStorageConfig:
    """Çağrı kaydı nesne deposu (S3/DigitalOcean Spaces) yapılandırması."""

    bucket: str
    region: str
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    retention_days: int

    @property
    def is_configured(self) -> bool:
        """Kayıt yükleme/okuma için gereken asgari kümeyi taşıyor mu?"""
        return all([self.bucket, self.access_key_id, self.secret_access_key])


def _retention_days() -> int:
    raw = os.getenv("CC_RECORDING_RETENTION_DAYS", str(_DEFAULT_RETENTION_DAYS))
    try:
        val = int(raw)
        return val if val > 0 else _DEFAULT_RETENTION_DAYS
    except (TypeError, ValueError):
        return _DEFAULT_RETENTION_DAYS


def get_recording_storage_config() -> RecordingStorageConfig:
    """Ortamdan çağrı-kaydı depo yapılandırmasını okur (fail-closed)."""
    return RecordingStorageConfig(
        bucket=os.getenv("CC_RECORDING_S3_BUCKET", "").strip(),
        region=os.getenv("CC_RECORDING_S3_REGION", "").strip() or "us-east-1",
        endpoint_url=os.getenv("CC_RECORDING_S3_ENDPOINT", "").strip(),
        access_key_id=os.getenv("CC_RECORDING_S3_ACCESS_KEY_ID", "").strip(),
        secret_access_key=os.getenv("CC_RECORDING_S3_SECRET_ACCESS_KEY", "").strip(),
        retention_days=_retention_days(),
    )
