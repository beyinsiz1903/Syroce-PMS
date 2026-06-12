"""KBS gece güvenlik taraması (00:00 kiracı yerel saati).

Otomatik enqueue check-in/out anında çalışır; ancak bir gün içinde gözden
kaçan (auto-enqueue kapalıyken oluşan, eksik-veri nedeniyle dead'e düşüp veri
sonradan tamamlanan vb.) konaklamalar olabilir. Bu güvenlik ağı, her kiracının
YEREL saatiyle gece yarısında, KAPANAN günün gönderilmemiş konaklamalarını
mevcut doğrulanmış ``auto_enqueue_kbs`` yoluyla yeniden kuyruğa alır.

Idempotent: bir (booking, action) için açık (pending/in_progress) VEYA tamamlanmış
(done) iş varsa atlanır; yalnızca hiç iş olmayan veya dead kalmış konaklamalar
yeniden enqueue edilir. Eksik veri yine ``kbs_alerts`` missing_data yoluna düşer.

Celery: çağıran taze, loop'a bağlı RAW db geçirir. ``auto_enqueue_kbs`` modül
seviyesinde ``core.database.db``'yi yakaladığı için, tarama süresince
``core.kbs_auto_enqueue.db`` taze raw db'ye yeniden bağlanır (night-audit'in
engine-rebind kalıbının aynısı; prefork tek-task-per-process olduğundan güvenli).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger("core.kbs_nightly_sweep")

QUEUE_KIND = "queue_job"
_ACTIVE_STATUSES = ["checked_in", "confirmed", "guaranteed", "checked_out"]


async def _has_job_for(raw_db, tenant_id: str, booking_id: str, action: str) -> bool:
    """(booking, action) için açık veya tamamlanmış iş var mı? (dead → yok sayılır)."""
    existing = await raw_db.kbs_reports.find_one(
        {
            "_kind": QUEUE_KIND,
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "action": action,
            "status": {"$in": ["pending", "in_progress", "done"]},
        },
        {"_id": 0, "id": 1},
    )
    return existing is not None


async def sweep_tenant_kbs(raw_db, tenant_id: str, day_iso: str) -> dict:
    """Bir kiracı için verilen yerel gününün gönderilmemiş konaklamalarını enqueue et.

    Args:
        raw_db: taze, loop'a bağlı RAW Motor db (proxy DEĞİL — tenant_context yok).
        tenant_id: kiracı.
        day_iso: taranacak yerel gün, "YYYY-MM-DD".

    Returns: özet.
    """
    import core.kbs_auto_enqueue as ae

    lo = day_iso + "T00:00:00"
    hi = day_iso + "T23:59:59"

    enqueued = 0
    skipped = 0
    blocked = 0  # missing_data / booking-not-found (auto_enqueue None döndü)

    saved_db = ae.db
    ae.db = raw_db
    try:
        # Check-in bildirimi: o gün giriş yapan aktif/çıkış-yapmış konaklamalar
        checkin_cursor = raw_db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": _ACTIVE_STATUSES},
                "check_in": {"$gte": lo, "$lte": hi},
            },
            {"_id": 0, "id": 1, "check_out": 1, "status": 1},
        )
        async for b in checkin_cursor:
            booking_id = b.get("id")
            if not booking_id:
                continue
            if await _has_job_for(raw_db, tenant_id, booking_id, "checkin"):
                skipped += 1
                continue
            result = await ae.auto_enqueue_kbs(
                tenant_id, booking_id, "checkin", actor="system:nightly_sweep",
            )
            if result:
                enqueued += 1
            else:
                blocked += 1

        # Check-out bildirimi: o gün çıkış yapan konaklamalar
        checkout_cursor = raw_db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": "checked_out",
                "check_out": {"$gte": lo, "$lte": hi},
            },
            {"_id": 0, "id": 1},
        )
        async for b in checkout_cursor:
            booking_id = b.get("id")
            if not booking_id:
                continue
            if await _has_job_for(raw_db, tenant_id, booking_id, "checkout"):
                skipped += 1
                continue
            result = await ae.auto_enqueue_kbs(
                tenant_id, booking_id, "checkout", actor="system:nightly_sweep",
            )
            if result:
                enqueued += 1
            else:
                blocked += 1
    finally:
        ae.db = saved_db

    return {
        "tenant_id": tenant_id,
        "day": day_iso,
        "enqueued": enqueued,
        "skipped": skipped,
        "blocked": blocked,
    }


def previous_local_day(local_now: datetime) -> str:
    """00:00 tick'inde KAPANAN günün yerel tarihi (YYYY-MM-DD)."""
    return (local_now - timedelta(days=1)).strftime("%Y-%m-%d")


async def resolve_tenant_timezone(raw_db, tenant_id: str) -> str:
    """Kiracı IANA timezone adını çöz (tenant_settings öncelikli, fallback Istanbul)."""
    doc = await raw_db.tenant_settings.find_one(
        {"tenant_id": tenant_id}, {"_id": 0, "timezone": 1}
    ) or {}
    return doc.get("timezone") or "Europe/Istanbul"


def _now_utc() -> datetime:
    return datetime.now(UTC)
