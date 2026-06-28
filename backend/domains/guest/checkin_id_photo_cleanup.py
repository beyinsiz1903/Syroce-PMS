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

from core.transient_db_guard import TransientFailureTracker

logger = logging.getLogger(__name__)

_transient_tracker = TransientFailureTracker("checkin-id-photo-cleanup")

DEFAULT_RETENTION_DAYS = 90
DEFAULT_ORPHAN_TTL_HOURS = 24
DEFAULT_INTERVAL_SECONDS = 3600  # hourly tick — orphan TTL granularity

# Task #124 — KVKK saklama süresi için makul üst/alt sınırlar.
# 1 günden kısa: pratik olarak fotoğrafı yüklenir yüklenmez silmek demek;
# bu da resepsiyonun çekilen fotoğrafı görme şansını ortadan kaldırır.
# 365 günden uzun: KVKK amaç-sınırlandırma ilkesine aykırı düşer ve
# diskte gereksiz risk birikimine yol açar.
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365

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
            name,
            raw,
            default,
        )
        return default


def clamp_retention_days(value: int) -> int:
    """Saklama süresini [MIN_RETENTION_DAYS, MAX_RETENTION_DAYS] aralığına sıkıştırır.

    Hem env değerini hem tenant ayarını okurken hem de ayar PUT eden API
    katmanında çağrılır; tek noktadan sınırlandırma yaparak DB'ye veya
    sorgu cutoff'una geçersiz değerin sızmasını engeller.
    """
    if value < MIN_RETENTION_DAYS:
        return MIN_RETENTION_DAYS
    if value > MAX_RETENTION_DAYS:
        return MAX_RETENTION_DAYS
    return value


def env_default_retention_days() -> int:
    """`ID_PHOTO_RETENTION_DAYS` env değerini okur ve sınırlara sıkıştırır.

    Tenant ayarı yoksa **global default** olarak bu değer kullanılır;
    Task #124 öncesindeki davranış (tüm kiracılar için tek değer) bu
    fonksiyon üzerinden korunur.
    """
    return clamp_retention_days(_env_int("ID_PHOTO_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))


async def resolve_tenant_retention_days(db: Any, tenant_id: str) -> int:
    """Tenant'ın efektif saklama süresini gün cinsinden döner.

    Çözümleme sırası (Task #124):

    1. ``tenant_settings.id_photo_retention_days`` — tenant özel değeri.
    2. ``ID_PHOTO_RETENTION_DAYS`` env — tüm kiracılar için global
       varsayılan (mevcut davranış).
    3. ``DEFAULT_RETENTION_DAYS`` (90) — env de yoksa son çare.

    Her durumda dönen değer ``clamp_retention_days`` ile [1, 365]
    aralığına sıkıştırılır; bu sayede kötü-niyetli ya da bozuk bir DB
    kaydı silme cutoff'unu absurd bir noktaya kaydıramaz.
    """
    if not tenant_id:
        return env_default_retention_days()
    try:
        settings = await db.tenant_settings.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0, "id_photo_retention_days": 1},
        )
    except Exception:
        logger.exception(
            "checkin_id_photo_cleanup: tenant_settings read failed for tenant=%s",
            tenant_id,
        )
        return env_default_retention_days()
    raw = (settings or {}).get("id_photo_retention_days")
    if raw is None:
        return env_default_retention_days()
    try:
        return clamp_retention_days(int(raw))
    except (TypeError, ValueError):
        logger.warning(
            "checkin_id_photo_cleanup: invalid tenant retention %r for tenant=%s, falling back to env default",
            raw,
            tenant_id,
        )
        return env_default_retention_days()


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
    actor_id: str | None = None,
) -> None:
    """Best-effort audit entry; sessizce yutar — temizliği bloklamamalı.

    ``actor_id`` Task #86 ile eklendi: manuel silme uçları (resepsiyon
    ön-görüntüleme paneli, KVKK toplu silme) silmeyi yapan personeli
    audit kaydına yazabilsin diye opsiyonel parametre olarak alınır.
    Otomatik temizlikte (worker) ``None`` kalır.
    """
    try:
        from shared_kernel.audit_helper import build_audit_entry

        entry = build_audit_entry(
            actor_id=actor_id,
            tenant_id=str(doc.get("tenant_id") or ""),
            entity_type="online_checkin_id_photo",
            entity_id=str(doc.get("photo_id") or ""),
            action="auto_delete" if actor_id is None else "manual_delete",
            metadata={
                "reason": reason,
                "file_deleted": bool(file_deleted),
                "metadata_deleted": bool(metadata_deleted),
                "claimed": bool(doc.get("claimed")),
                "uploaded_at": doc.get("uploaded_at"),
                "booking_id": doc.get("booking_id"),
                "checkin_id": doc.get("checkin_id"),
                "guest_id": doc.get("guest_id"),
            },
        )
        await db.audit_logs.insert_one(entry)
    except Exception:  # pragma: no cover — audit hatası fatal değil
        logger.exception(
            "checkin_id_photo_cleanup: audit write failed for photo_id=%s",
            doc.get("photo_id"),
        )


async def _delete_one(
    *,
    db: Any,
    doc: dict[str, Any],
    reason: str,
    actor_id: str | None = None,
) -> bool:
    """Bir kaydı sil: önce şifrelenmiş dosya, sonra metadata, sonra audit.

    Sırayla yapılması önemli — dosya silme başarısız olsa bile metadata
    kaydı silinmeli; aksi hâlde dosya hayalet metadata ile koleksiyonda
    kalmaya devam eder ve bir sonraki tarama yine aynı kaydı dener.
    """
    photo_id = doc.get("photo_id")
    tenant_id = doc.get("tenant_id")
    if not photo_id or not tenant_id:
        logger.warning("checkin_id_photo_cleanup: skipping malformed metadata doc (missing photo_id/tenant_id)")
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
        actor_id=actor_id,
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
            "checkin_id_photo_cleanup: scan failed for reason=%s",
            reason,
        )
    return deleted


async def prune_expired_id_photos(
    *,
    db: Any,
    retention_days: int | None = None,
    orphan_ttl_hours: int | None = None,
    tenant_id: str | None = None,
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

    Task #124: ``tenant_id`` verilirse sorgular o kiracıya skoplanır
    (``{"tenant_id": tid, ...}``); böylece per-tenant retention günü
    gerçek anlamda izole hesaplanır. ``tenant_id=None`` ise (varsayılan,
    geriye dönük uyum) sorgular eski davranıştaki gibi tüm koleksiyon
    üzerinde tek cutoff ile çalışır — bu mod manuel testler ve tek-shot
    çağrılar için tutuldu; üretim worker'ı ``prune_expired_id_photos_per_tenant``
    üzerinden tenant başına bu fonksiyonu çağırır.
    """
    if retention_days is None:
        retention_days = _env_int("ID_PHOTO_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
    if orphan_ttl_hours is None:
        orphan_ttl_hours = _env_int("ID_PHOTO_ORPHAN_TTL_HOURS", DEFAULT_ORPHAN_TTL_HOURS)

    now = now or datetime.now(UTC)
    counts = {"expired": 0, "orphans": 0}
    tenant_filter: dict[str, Any] = {"tenant_id": tenant_id} if tenant_id else {}

    # 1) Saklama süresi dolan TÜM kayıtlar (claimed/unclaimed fark etmez).
    if retention_days > 0:
        cutoff = now - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()
        # ``uploaded_at`` ISO string olarak yazılıyor; eski kayıtlarda
        # native datetime ihtimali için iki tipi de yakalıyoruz.
        retention_query: dict[str, Any] = {
            **tenant_filter,
            "$or": [
                {"uploaded_at": {"$lt": cutoff_iso}},
                {"uploaded_at": {"$lt": cutoff}},
            ],
        }
        counts["expired"] = await _iter_and_delete(
            db=db,
            query=retention_query,
            reason="retention_expired",
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
            **tenant_filter,
            "claimed": False,
            "$or": [
                {"uploaded_at": {"$lt": orphan_cutoff_iso}},
                {"uploaded_at": {"$lt": orphan_cutoff}},
            ],
        }
        counts["orphans"] = await _iter_and_delete(
            db=db,
            query=orphan_query,
            reason="orphan_unclaimed",
        )
    else:
        logger.warning(
            "checkin_id_photo_cleanup: orphan_ttl_hours=%d <= 0, skipping orphan prune",
            orphan_ttl_hours,
        )

    if counts["expired"] or counts["orphans"]:
        logger.info(
            "checkin_id_photo_cleanup: deleted %d expired + %d orphan ID photos (retention=%dd, orphan_ttl=%dh, tenant=%s)",
            counts["expired"],
            counts["orphans"],
            retention_days,
            orphan_ttl_hours,
            tenant_id or "*",
        )
    return counts


async def prune_expired_id_photos_per_tenant(
    *,
    db: Any,
    now: datetime | None = None,
) -> dict[str, int]:
    """Worker giriş noktası — tenant başına saklama süresini çözer ve temizler.

    Task #124'te eklendi: önceden tek bir global cutoff ile çalışan worker,
    artık koleksiyondaki ``distinct("tenant_id")`` kümesini iterate ederek
    her kiracıya kendi ayarını (``tenant_settings.id_photo_retention_days``,
    yoksa env defaults) uygular. Hiç fotoğrafı olmayan tenant'lar burada
    görünmez — silinecek bir şey de olmadığı için bu beklenen davranış.

    Yetim TTL (``ID_PHOTO_ORPHAN_TTL_HOURS``) per-tenant değil; KVKK
    saklama yükümlülüğüyle ilgisi yok, yalnızca yarım kalan yüklemeyi
    aklamak için bir housekeeping ayarı olduğundan global tutuldu.
    Geriye dönük uyum: değer eski env değişkeni üzerinden okunur.
    """
    counts = {"expired": 0, "orphans": 0}
    orphan_ttl_hours = _env_int(
        "ID_PHOTO_ORPHAN_TTL_HOURS",
        DEFAULT_ORPHAN_TTL_HOURS,
    )

    try:
        tenant_ids = await db.online_checkin_id_photos.distinct("tenant_id")
    except Exception:
        logger.exception(
            "checkin_id_photo_cleanup: distinct(tenant_id) failed; skipping cycle",
        )
        return counts

    # ``distinct`` None/garip değerler dönerse (eski/bozuk kayıtlar)
    # sessizce atla; tenant_id'siz bir kayıt zaten _delete_one
    # tarafından da iskartaya çıkarılır.
    seen: set[str] = set()
    for tid in tenant_ids or []:
        if not tid or not isinstance(tid, str) or tid in seen:
            continue
        seen.add(tid)
        try:
            retention = await resolve_tenant_retention_days(db, tid)
            sub = await prune_expired_id_photos(
                db=db,
                retention_days=retention,
                orphan_ttl_hours=orphan_ttl_hours,
                tenant_id=tid,
                now=now,
            )
            counts["expired"] += sub["expired"]
            counts["orphans"] += sub["orphans"]
        except Exception:
            logger.exception(
                "checkin_id_photo_cleanup: per-tenant prune failed for tenant=%s",
                tid,
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

            # Task #124: per-tenant retention. Eski global cutoff yerine
            # her kiracının kendi ayarını uygulayan orchestrator kullanılır.
            await prune_expired_id_photos_per_tenant(db=db)
            _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover — worker hiç durmamalı
            _transient_tracker.log_exception(
                logger,
                e,
                TransientFailureTracker.OUTER_LOOP_KEY,
                context="prune cycle",
                non_transient_msg="%s prune cycle error: %s",
            )

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return


def start_checkin_id_photo_cleanup_worker() -> None:
    """Background prune worker'ı başlatır. Tekrar çağrılırsa no-op."""
    global _worker_task
    if not _is_enabled():
        logger.info("checkin_id_photo_cleanup: disabled by env, worker not started")
        return
    if _worker_task and not _worker_task.done():
        return
    interval = _env_int(
        "ID_PHOTO_CLEANUP_INTERVAL_SECONDS",
        DEFAULT_INTERVAL_SECONDS,
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
