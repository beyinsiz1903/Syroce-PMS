"""Contact Center — Faz 2 çağrı kaydı deposu (S3/Spaces, fail-closed).

Doktrin:
- Kayıt baytları at-rest ŞİFRELİ saklanır (AES-256-GCM, AAD: tenant+call+recording);
  yerel ID-foto blob desenini aynalar. Saklanan tek meta ``recording_ref`` =
  nesne-deposu ANAHTARI; imzalı/URL ASLA persist edilmez, ASLA loglanmaz.
- Twilio'dan kayıt indirme kimlik-doğrulamalıdır (Account SID + Auth Token).
- Yapılandırma yoksa (S3 veya Twilio) boru hattı fail-closed: kayıt indirilmez,
  ``not_configured`` döner; çağrı kaydı yine de durum/metadata ile tutulur.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from typing import Any

from core.crypto.engine import AADContext, AESGCMEngine
from core.crypto.errors import CryptoError, DecryptionError, TamperDetectedError
from core.crypto.keys import load_keyring
from domains.contact_center.voice_config import (
    get_recording_storage_config,
    get_twilio_voice_config,
)

logger = logging.getLogger(__name__)

_BLOB_MAGIC = b"SYRREC1\0"  # 8 bytes — voice recording blob format marker
_NONCE_SIZE = 12

_engine: AESGCMEngine | None = None


def _get_engine() -> AESGCMEngine:
    global _engine
    if _engine is None:
        _engine = AESGCMEngine(load_keyring())
    return _engine


def _aad(tenant_id: str, call_id: str, recording_id: str) -> AADContext:
    return AADContext(
        tenant_id=tenant_id,
        provider="contact_center_voice",
        property_id=call_id,
        environment=os.environ.get("APP_ENV", "development"),
        context_type=f"call_recording:{recording_id}",
    )


def _encrypt_blob(
    plaintext: bytes, *, tenant_id: str, call_id: str, recording_id: str
) -> bytes:
    """AES-256-GCM, AAD-bağlı kayıt blob'u (file-swap tamper tespiti)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    engine = _get_engine()
    kid, key = engine._keyring.encryption_key()  # noqa: SLF001 — adjacent module
    kid_bytes = kid.encode("utf-8")
    if len(kid_bytes) > 0xFFFF:
        raise CryptoError("kid too long")
    nonce = secrets.token_bytes(_NONCE_SIZE)
    aad = _aad(tenant_id, call_id, recording_id).to_bytes()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return (
        _BLOB_MAGIC
        + len(kid_bytes).to_bytes(2, "big")
        + kid_bytes
        + nonce
        + ciphertext
    )


def _decrypt_blob(
    blob: bytes, *, tenant_id: str, call_id: str, recording_id: str
) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(_BLOB_MAGIC):
        raise DecryptionError("bad_magic")
    pos = len(_BLOB_MAGIC)
    if len(blob) < pos + 2:
        raise DecryptionError("truncated_header")
    kid_len = int.from_bytes(blob[pos : pos + 2], "big")
    pos += 2
    if len(blob) < pos + kid_len + _NONCE_SIZE + 16:
        raise DecryptionError("truncated_body")
    kid = blob[pos : pos + kid_len].decode("utf-8")
    pos += kid_len
    nonce = blob[pos : pos + _NONCE_SIZE]
    pos += _NONCE_SIZE
    ciphertext = blob[pos:]
    key = _get_engine()._keyring.decryption_key(kid)  # noqa: SLF001
    aad = _aad(tenant_id, call_id, recording_id).to_bytes()
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise TamperDetectedError(kid=kid) from exc


def _object_key(tenant_id: str, call_id: str, recording_id: str) -> str:
    safe_tenant = "".join(c for c in tenant_id if c.isalnum() or c in "-_") or "unknown"
    safe_call = "".join(c for c in call_id if c.isalnum() or c in "-_") or "unknown"
    safe_rec = "".join(c for c in recording_id if c.isalnum() or c in "-_") or "rec"
    return f"call_recordings/{safe_tenant}/{safe_call}/{safe_rec}.enc"


def _s3_client():
    """boto3 S3/Spaces istemcisi (fail-closed). Yoksa None döner."""
    cfg = get_recording_storage_config()
    if not cfg.is_configured:
        return None
    try:
        import boto3
    except ImportError:
        logger.warning("[CC-VOICE] boto3 kurulu değil — kayıt deposu fail-closed")
        return None
    kwargs: dict[str, Any] = {
        "region_name": cfg.region,
        "aws_access_key_id": cfg.access_key_id,
        "aws_secret_access_key": cfg.secret_access_key,
    }
    if cfg.endpoint_url:
        kwargs["endpoint_url"] = cfg.endpoint_url
    return boto3.client("s3", **kwargs)


async def fetch_twilio_recording(recording_url: str) -> bytes | None:
    """Twilio'dan kaydı kimlik-doğrulamalı indirir (fail-closed).

    URL veya kimlik bilgisi yoksa None döner. Telefon/URL/sır ASLA loglanmaz.
    """
    tw = get_twilio_voice_config()
    if not recording_url or not tw.account_sid or not tw.auth_token:
        return None
    try:
        import httpx
    except ImportError:
        logger.warning("[CC-VOICE] httpx kurulu değil — kayıt indirilemiyor")
        return None
    media_url = recording_url if recording_url.endswith(".mp3") else f"{recording_url}.mp3"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(media_url, auth=(tw.account_sid, tw.auth_token))
        if resp.status_code != 200:
            logger.warning(
                "[CC-VOICE] kayıt indirme başarısız status=%s", resp.status_code
            )
            return None
        return resp.content
    except Exception:
        logger.warning("[CC-VOICE] kayıt indirme hatası (PII'siz)")
        return None


def store_recording_bytes(
    audio: bytes, *, tenant_id: str, call_id: str
) -> str | None:
    """Kayıt baytlarını şifreleyip nesne deposuna yazar; ``recording_ref`` döner.

    Fail-closed: depo yapılandırılmamışsa None döner (kayıt saklanmaz).
    """
    client = _s3_client()
    if client is None or not audio:
        return None
    cfg = get_recording_storage_config()
    recording_id = uuid.uuid4().hex
    key = _object_key(tenant_id, call_id, recording_id)
    blob = _encrypt_blob(
        audio, tenant_id=tenant_id, call_id=call_id, recording_id=recording_id
    )
    try:
        client.put_object(
            Bucket=cfg.bucket,
            Key=key,
            Body=blob,
            ContentType="application/octet-stream",
        )
    except Exception:
        logger.warning("[CC-VOICE] kayıt yükleme hatası (PII'siz)")
        return None
    return key


def load_recording_bytes(
    recording_ref: str, *, tenant_id: str, call_id: str
) -> bytes | None:
    """Kaydı depodan çekip çözer (decrypt-at-read). Fail-closed: None.

    ``recording_id`` AAD bağlaması ref anahtarından türetilir (``.../<rec>.enc``).
    """
    client = _s3_client()
    if client is None or not recording_ref:
        return None
    cfg = get_recording_storage_config()
    recording_id = recording_ref.rsplit("/", 1)[-1].removesuffix(".enc") or "rec"
    try:
        obj = client.get_object(Bucket=cfg.bucket, Key=recording_ref)
        blob = obj["Body"].read()
    except Exception:
        logger.warning("[CC-VOICE] kayıt okuma hatası (PII'siz)")
        return None
    try:
        return _decrypt_blob(
            blob, tenant_id=tenant_id, call_id=call_id, recording_id=recording_id
        )
    except (DecryptionError, TamperDetectedError):
        logger.error("[CC-VOICE] kayıt çözme/tamper hatası ref-only")
        return None


def delete_recording(recording_ref: str) -> bool:
    """Kaydı nesne deposundan siler (retention). Fail-closed: False."""
    client = _s3_client()
    if client is None or not recording_ref:
        return False
    cfg = get_recording_storage_config()
    try:
        client.delete_object(Bucket=cfg.bucket, Key=recording_ref)
        return True
    except Exception:
        logger.warning("[CC-VOICE] kayıt silme hatası (PII'siz)")
        return False
