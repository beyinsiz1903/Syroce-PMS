"""Contact Center — Faz 2 çağrı kaydı boru hattı (fail-closed).

İndir (Twilio, kimlik-doğrulamalı) → şifrele (AES-256-GCM) → ayrı nesne deposuna
yükle (S3/Spaces) → çağrıya yalnızca ``recording_ref`` (nesne anahtarı) bağla.
Retention: süresi dolan kayıtları depodan siler ve referansı kaldırır.

Doktrin: imzalı URL ASLA persist/loglanmaz; PII loglanmaz; depo/Twilio yoksa
boru hattı fail-closed (kayıt indirilmez/saklanmaz).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from domains.contact_center.recording_storage import (
    delete_recording,
    fetch_twilio_recording,
    store_recording_bytes,
)
from domains.contact_center.voice_config import get_recording_storage_config
from domains.contact_center.voice_ingest import attach_recording_ref

logger = logging.getLogger(__name__)

_COLLECTION = "contact_center_calls"


async def process_call_recording(
    db,
    *,
    tenant_id: str,
    provider_call_sid: str,
    recording_url: str,
    duration_seconds: int = 0,
) -> dict:
    """Tek bir çağrı kaydını indir→şifrele→yükle→bağla (fail-closed).

    Hata/yapılandırma-yokluğu durumunda durum kodu döner; raise etmez.
    """
    if not tenant_id or not provider_call_sid or not recording_url:
        return {"status": "invalid_input"}
    try:
        audio = await fetch_twilio_recording(recording_url)
        if not audio:
            return {"status": "fetch_not_configured_or_unavailable"}
        ref = store_recording_bytes(audio, tenant_id=tenant_id, call_id=provider_call_sid)
        if not ref:
            return {"status": "storage_not_configured"}
        await attach_recording_ref(
            db,
            tenant_id=tenant_id,
            provider_call_sid=provider_call_sid,
            recording_ref=ref,
            duration_seconds=duration_seconds,
        )
        return {"status": "stored"}
    except Exception:
        logger.exception("[CC-VOICE] kayıt boru hattı başarısız (bastırıldı, PII'siz)")
        return {"status": "error"}


async def purge_expired_recordings(db) -> dict:
    """Retention: süresi dolan kayıtları depodan siler, referansı kaldırır.

    ``CC_RECORDING_RETENTION_DAYS`` gün öncesinden eski (``ended_at``) ve kaydı olan
    çağrılar taranır. Nesne silinince ``recording_ref`` unset + ``disposition``
    ``recording_purged`` yazılır. Depo yapılandırılmamışsa no-op (fail-closed).
    """
    cfg = get_recording_storage_config()
    if not cfg.is_configured:
        return {"status": "not_configured", "purged": 0}
    cutoff = datetime.now(UTC) - timedelta(days=cfg.retention_days)
    purged = 0
    scanned = 0
    try:
        cursor = db[_COLLECTION].find(
            {
                "recording_ref": {"$type": "string"},
                "ended_at": {"$lt": cutoff},
            },
            {"_id": 0, "id": 1, "tenant_id": 1, "provider_call_sid": 1, "recording_ref": 1},
        )
        async for doc in cursor:
            scanned += 1
            ref = doc.get("recording_ref")
            if not ref:
                continue
            if delete_recording(ref):
                await db[_COLLECTION].update_one(
                    {
                        "tenant_id": doc.get("tenant_id"),
                        "provider_call_sid": doc.get("provider_call_sid"),
                    },
                    {
                        "$set": {
                            "recording_ref": None,
                            "disposition": "recording_purged",
                            "updated_at": datetime.now(UTC),
                        }
                    },
                )
                purged += 1
    except Exception:
        logger.exception("[CC-VOICE] retention taraması başarısız (bastırıldı)")
    return {"status": "ok", "scanned": scanned, "purged": purged}
