"""
Task #31 — Süresi dolan push aboneliklerinin otomatik temizliği.

Web push abonelikleri zamanla bayatlar:
- Kullanıcı tarayıcı cache'ini temizler / extension'ı kapatır.
- VAPID anahtarları döndürülür (tarayıcı tarafında abonelik invalid olur).
- Cihaz değişir, eski abonelik artık bir yere ulaşmaz.

Mevcut akış: bir bildirim gönderilirken push gateway 404/410 dönerse
`web_push.send_internal_message` ilgili kaydı zaten siliyor. Ancak
HİÇ BİLDİRİM GÖNDERİLMEYEN aboneliklere asla dokunulmuyor — bunlar
veritabanında birikmeye devam ediyor (örn. devre dışı kullanıcılar,
hiç mesajlaşmamış departmanlar).

Bu modül, periyodik bir worker ile yaş tabanlı temizlik yapar:
- `updated_at` (son upsert zamanı) `max_age_days` günden eski olan
  kayıtlar silinir. Çünkü kullanıcı aktif tarayıcı oturumunda iken
  service worker subscription'u her sayfa yüklemesinde refresh edip
  `store_subscription` ile updated_at'ı tazeler.

Konfigürasyon (ortam değişkenleri):
- WEB_PUSH_CLEANUP_INTERVAL_SECONDS (default 86400 = 24 saat)
- WEB_PUSH_CLEANUP_MAX_AGE_DAYS     (default 60 gün)
- WEB_PUSH_CLEANUP_ENABLED          ("0"/"false" ile devre dışı)

Worker idempotent + tek instance: aynı anda birden fazla web sunucu
ayağa kalkarsa hepsi worker'ı çalıştırır, ancak `delete_many` doğal
olarak idempotent (hedefe ulaşmış olan kayıt zaten yok). Pahalı bir
sorgu olmadığı için lock'lamaya gerek yok.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Worker handle'ı; shutdown'da iptal edebilmek için modül seviyesinde tutulur.
_worker_task: asyncio.Task | None = None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("web_push_cleanup: invalid %s=%r, using default %d",
                       name, raw, default)
        return default


def _is_enabled() -> bool:
    raw = (os.getenv("WEB_PUSH_CLEANUP_ENABLED") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


async def prune_inactive_subscriptions(
    *,
    db: Any,
    max_age_days: int | None = None,
    now: datetime | None = None,
) -> int:
    """`updated_at` eski olan tüm web push aboneliklerini siler.

    `db` parametre olarak alınır → testte mock geçilebilir.
    Dönen değer silinen kayıt sayısıdır.
    """
    if max_age_days is None:
        max_age_days = _env_int("WEB_PUSH_CLEANUP_MAX_AGE_DAYS", 60)
    if max_age_days <= 0:
        # Yanlış/agresif konfigürasyona karşı emniyet supabı.
        logger.warning(
            "web_push_cleanup: max_age_days=%d <= 0, skipping prune",
            max_age_days,
        )
        return 0

    cutoff = (now or datetime.now(UTC)) - timedelta(days=max_age_days)
    cutoff_iso = cutoff.isoformat()

    # Hem ISO string (mevcut yazım biçimi) hem datetime kayıtlarına karşı
    # uyumlu sorgu: store_subscription ISO yazıyor, ama eski yazılar
    # native datetime olabilir. Mongo $or ile her iki türü de yakalarız.
    query: dict[str, Any] = {
        "$or": [
            {"updated_at": {"$lt": cutoff_iso}},
            {"updated_at": {"$lt": cutoff}},
            # `updated_at` hiç olmayan eski kayıtlar için created_at fallback.
            {
                "updated_at": {"$exists": False},
                "$or": [
                    {"created_at": {"$lt": cutoff_iso}},
                    {"created_at": {"$lt": cutoff}},
                ],
            },
        ],
    }

    res = await db.web_push_subscriptions.delete_many(query)
    deleted = int(res.deleted_count or 0)
    if deleted:
        logger.info(
            "web_push_cleanup: pruned %d stale subscriptions (older than %d days)",
            deleted, max_age_days,
        )
    return deleted


async def _worker_loop(interval_seconds: int) -> None:
    logger.info(
        "web_push_cleanup: worker started (interval=%ds)",
        interval_seconds,
    )
    # İlk çalıştırma: server boot sırasında işi blocklamamak için kısa
    # bir gecikme ile başla.
    try:
        await asyncio.sleep(min(60, interval_seconds))
    except asyncio.CancelledError:
        return

    while True:
        try:
            from core.database import db  # late import: web_push ile aynı kaynak
            await prune_inactive_subscriptions(db=db)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover — worker hiç durmamalı
            logger.exception("web_push_cleanup: prune cycle error")

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return


def start_web_push_cleanup_worker() -> None:
    """Background prune worker'ı başlatır. Tekrar çağrılırsa no-op."""
    global _worker_task
    if not _is_enabled():
        logger.info("web_push_cleanup: disabled by env, worker not started")
        return
    if _worker_task and not _worker_task.done():
        return
    interval = _env_int("WEB_PUSH_CLEANUP_INTERVAL_SECONDS", 86_400)
    if interval < 60:
        logger.warning(
            "web_push_cleanup: interval=%d <0 60s, clamping to 60s",
            interval,
        )
        interval = 60
    _worker_task = asyncio.create_task(
        _worker_loop(interval),
        name="web_push_cleanup_worker",
    )


async def stop_web_push_cleanup_worker() -> None:
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
