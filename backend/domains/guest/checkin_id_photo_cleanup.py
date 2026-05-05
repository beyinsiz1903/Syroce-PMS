"""
Task #72 — Süresi dolan kimlik fotoğraflarının periyodik temizliği.

Online check-in sırasında yüklenen kimlik fotoğrafları AES-256-GCM ile
şifrelenmiş olarak ``SECURE_UPLOAD_DIR/checkin_id_photos/<tenant>/<id>.bin``
altında, metadata kaydı ise ``db.online_checkin_id_photos`` koleksiyonunda
tutuluyor. Bu modül iki temizlik işini periyodik olarak yürütür:

1. **Saklama süresi dolan fotoğraflar** — ``ID_PHOTO_RETENTION_DAYS``
   (varsayılan 90) günden eski yüklemeler KVKK/GDPR ve otelin denetim
   politikası gereği silinir; hem dosya hem metadata kaydı.
2. **Yetim yüklemeler** — Check-in formuna bağlanmamış (``claimed=false``)
   yüklemeler ``ID_PHOTO_ORPHAN_TTL_HOURS`` (varsayılan 24) saatten daha
   eski ise temizlenir. Bu sayede misafir formu tamamlamadan vazgeçtiğinde
   fotoğraf günlerce diskte kalmaz.

Her silme için ``audit_logs`` koleksiyonuna ``auto_delete`` aksiyonu yazılır
(actor_id=None, sebep + claimed durumu metadata'da). Böylece denetimde
"bu fotoğrafı kim, ne zaman, neden sildi?" sorusu yanıtlanabilir.

Konfigürasyon (ortam değişkenleri):
- ``ID_PHOTO_RETENTION_DAYS``           (varsayılan 90 gün)
- ``ID_PHOTO_ORPHAN_TTL_HOURS``         (varsayılan 24 saat)
- ``ID_PHOTO_CLEANUP_INTERVAL_SECONDS`` (varsayılan 3600 = 1 saat;
   yetim temizliği saatlik gerektiği için saatlik tarama makul)
- ``ID_PHOTO_CLEANUP_ENABLED``          ("0"/"false" ile devre dışı)

Worker ``web_push_cleanup`` ile aynı paterni izler: process-level singleton,
boot'ta kısa gecikme, sleep sırasında güvenli iptal. Çoklu sunucu durumunda
tüm instance'lar worker çalıştırır; ``delete_one`` doğal olarak idempotent
olduğu için bu sorun değil — pahalı bir sorgu da değil.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90
DEFAULT_ORPHAN_TTL_HOURS = 24
DEFAULT_INTERVAL_SECONDS = 3600  # hourly tick — orphan TTL granularity

_worker_task: asyncio.Task | None = None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "checkin_id_photo_cleanup: invalid %s=%r, using default %d",
            name, raw, default,
        )
        return default


def _is_enabled() -> bool:
    raw = (os.getenv("ID_PHOTO_CLEANUP_ENABLED") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


async def _audit_delete(
    *,
    db: Any,
    doc: dict[str, Any],
    reason: str,
    file_deleted: bool,
    metadata_deleted: bool,
) -> None:
    """Best-effort audit entry; sessizce yutar — temizliği bloklamamalı."""
    try:
        from shared_kernel.audit_helper import build_audit_entry
        entry = build_audit_entry(
            actor_id=None,  # otomatik silme — kullanıcı yok
            tenant_id=str(doc.get("tenant_id") or ""),
            entity_type="online_checkin_id_photo",
            entity_id=str(doc.get("photo_id") or ""),
            action="auto_delete",
            metadata={
                "reason": reason,
                "file_deleted": bool(file_deleted),
                "metadata_deleted": bool(metadata_deleted),
                "claimed": bool(doc.get("claimed")),
                "uploaded_at": doc.get("uploaded_at"),
                "booking_id": doc.get("booking_id"),
                "checkin_id": doc.get("checkin_id"),
            },
        )
        await db.audit_logs.insert_one(entry)
    except Exception:  # pragma: no cover — audit hatası fatal değil
        logger.exception(
            "checkin_id_photo_cleanup: audit write failed for photo_id=%s",
            doc.get("photo_id"),
        )


async def _delete_one(*, db: Any, doc: dict[str, Any], reason: str) -> bool:
    """Bir kaydı sil: önce şifrelenmiş dosya, sonra metadata, sonra audit.

    Sırayla yapılması önemli — dosya silme başarısız olsa bile metadata
    kaydı silinmeli; aksi hâlde dosya hayalet metadata ile koleksiyonda
    kalmaya devam eder ve bir sonraki tarama yine aynı kaydı dener.
    """
    photo_id = doc.get("photo_id")
    tenant_id = doc.get("tenant_id")
    if not photo_id or not tenant_id:
        logger.warning(
            "checkin_id_photo_cleanup: skipping malformed metadata doc (missing photo_id/tenant_id)"
        )
        return False

    file_deleted = False
    try:
        from domains.guest.checkin_id_photo_storage import delete_id_photo
        file_deleted = bool(delete_id_photo(tenant_id=tenant_id, photo_id=photo_id))
    except Exception:
        logger.exception(
            "checkin_id_photo_cleanup: file delete failed for photo_id=%s",
            photo_id,
        )

    metadata_deleted = False
    try:
        res = await db.online_checkin_id_photos.delete_one(
            {"photo_id": photo_id, "tenant_id": tenant_id},
        )
        metadata_deleted = bool(getattr(res, "deleted_count", 0))
    except Exception:
        logger.exception(
            "checkin_id_photo_cleanup: metadata delete failed for photo_id=%s",
            photo_id,
        )

    await _audit_delete(
        db=db,
        doc=doc,
        reason=reason,
        file_deleted=file_deleted,
        metadata_deleted=metadata_deleted,
    )
    return file_deleted or metadata_deleted


async def _iter_and_delete(
    *,
    db: Any,
    query: dict[str, Any],
    reason: str,
) -> int:
    """``find`` sonucunu tarayıp her dokümanı tek tek siler.

    Birden fazla kayıt için ``delete_many`` daha verimli olurdu ama dosya
    sistemini de paralel temizlememiz gerektiği için tek tek dolaşmak
    zorundayız. Tarama sırasında oluşan beklenmeyen hatalar bireysel
    kaydı atlatır, döngü devam eder.
    """
    deleted = 0
    try:
        cursor = db.online_checkin_id_photos.find(query, {"_id": 0})
        async for doc in cursor:
            try:
                if await _delete_one(db=db, doc=doc, reason=reason):
                    deleted += 1
            except Exception:
                logger.exception(
                    "checkin_id_photo_cleanup: unexpected error deleting photo_id=%s",
                    doc.get("photo_id"),
                )
    except Exception:
        logger.exception(
            "checkin_id_photo_cleanup: scan failed for reason=%s", reason,
        )
    return deleted


async def prune_expired_id_photos(
    *,
    db: Any,
    retention_days: int | None = None,
    orphan_ttl_hours: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Süresi dolan ve yetim kalan kimlik fotoğraflarını temizler.

    Dönen değer: ``{"expired": int, "orphans": int}``. ``db`` parametre
    olarak alınır; testte mock geçilebilir.

    İki tarama ayrı sorgu olarak yürütülür: yetim taraması ``claimed=False``
    filtresi içerdiği için retention taramasında zaten silinmiş yetim
    kayıtları tekrar ziyaret etmez. Retention taraması da yetimleri
    yakalayabilir (90 günden eski yetim varsa) — bu durumda ikinci tarama
    o kayıtları görmez (zaten silindi), sayaçlar tutarlı kalır.
    """
    if retention_days is None:
        retention_days = _env_int("ID_PHOTO_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
    if orphan_ttl_hours is None:
        orphan_ttl_hours = _env_int("ID_PHOTO_ORPHAN_TTL_HOURS", DEFAULT_ORPHAN_TTL_HOURS)

    now = now or datetime.now(UTC)
    counts = {"expired": 0, "orphans": 0}

    # 1) Saklama süresi dolan TÜM kayıtlar (claimed/unclaimed fark etmez).
    if retention_days > 0:
        cutoff = now - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()
        # ``uploaded_at`` ISO string olarak yazılıyor; eski kayıtlarda
        # native datetime ihtimali için iki tipi de yakalıyoruz.
        retention_query: dict[str, Any] = {
            "$or": [
                {"uploaded_at": {"$lt": cutoff_iso}},
                {"uploaded_at": {"$lt": cutoff}},
            ],
        }
        counts["expired"] = await _iter_and_delete(
            db=db, query=retention_query, reason="retention_expired",
        )
    else:
        logger.warning(
            "checkin_id_photo_cleanup: retention_days=%d <= 0, skipping retention prune",
            retention_days,
        )

    # 2) Yetim yüklemeler: claimed=false ve TTL'i dolmuş.
    if orphan_ttl_hours > 0:
        orphan_cutoff = now - timedelta(hours=orphan_ttl_hours)
        orphan_cutoff_iso = orphan_cutoff.isoformat()
        orphan_query: dict[str, Any] = {
            "claimed": False,
            "$or": [
                {"uploaded_at": {"$lt": orphan_cutoff_iso}},
                {"uploaded_at": {"$lt": orphan_cutoff}},
            ],
        }
        counts["orphans"] = await _iter_and_delete(
            db=db, query=orphan_query, reason="orphan_unclaimed",
        )
    else:
        logger.warning(
            "checkin_id_photo_cleanup: orphan_ttl_hours=%d <= 0, skipping orphan prune",
            orphan_ttl_hours,
        )

    if counts["expired"] or counts["orphans"]:
        logger.info(
            "checkin_id_photo_cleanup: deleted %d expired + %d orphan ID photos "
            "(retention=%dd, orphan_ttl=%dh)",
            counts["expired"], counts["orphans"], retention_days, orphan_ttl_hours,
        )
    return counts


async def _worker_loop(interval_seconds: int) -> None:
    logger.info(
        "checkin_id_photo_cleanup: worker started (interval=%ds)",
        interval_seconds,
    )
    # İlk çalıştırma: server boot sırasında işi blocklamamak için kısa bir
    # gecikme ile başla.
    try:
        await asyncio.sleep(min(60, interval_seconds))
    except asyncio.CancelledError:
        return

    while True:
        try:
            from core.database import db  # late import: storage ile aynı kaynak
            await prune_expired_id_photos(db=db)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover — worker hiç durmamalı
            logger.exception("checkin_id_photo_cleanup: prune cycle error")

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return


def start_checkin_id_photo_cleanup_worker() -> None:
    """Background prune worker'ı başlatır. Tekrar çağrılırsa no-op."""
    global _worker_task
    if not _is_enabled():
        logger.info(
            "checkin_id_photo_cleanup: disabled by env, worker not started"
        )
        return
    if _worker_task and not _worker_task.done():
        return
    interval = _env_int(
        "ID_PHOTO_CLEANUP_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS,
    )
    if interval < 60:
        logger.warning(
            "checkin_id_photo_cleanup: interval=%d <60s, clamping to 60s",
            interval,
        )
        interval = 60
    _worker_task = asyncio.create_task(
        _worker_loop(interval),
        name="checkin_id_photo_cleanup_worker",
    )


async def stop_checkin_id_photo_cleanup_worker() -> None:
    """Graceful shutdown: worker görevini iptal et."""
    global _worker_task
    task = _worker_task
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # pragma: no cover
        pass
    _worker_task = None
