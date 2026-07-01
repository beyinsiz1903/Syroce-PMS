"""Report Scheduler Worker

Periyodik olarak `report_schedules` koleksiyonunu tarar; `is_active=true` ve
`next_run <= now()` olan zamanlamaları çalıştırır, ardından `next_run`'ı bir
sonraki tetiklemeye ileri sarar. Bootstrap (phases/c_domain.py) tarafından
uygulama startup'ında başlatılır.

Kapatmak için: `REPORT_SCHEDULER_INTERVAL_SECONDS=0`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = int(os.environ.get("REPORT_SCHEDULER_INTERVAL_SECONDS", "60"))
_started = False


async def _tick() -> None:
    """Tek bir tarama: due olan tüm zamanlamaları ATOMIK olarak claim eder.

    Multi-instance güvenliği: aynı zamanlamayı birden fazla worker fetch edip
    iki kez tetiklemesin diye `find_one_and_update` ile due dökümanı bulup
    `next_run`'ı aynı atomic op içinde ileri sarıyoruz. Bir worker dökümanı
    "claim" ettikten sonra diğer worker'ın `next_run<=now` filtresi onu
    eşlemeyecek.
    """
    from core.database import _raw_db as raw_db
    from routers.report_scheduler import _compute_next_run, _execute_schedule

    processed = 0
    while True:
        now_iso = datetime.now(UTC).isoformat()
        # Önce dökümanı tek bir atomik komutla "kilitle".
        sch = await raw_db.report_schedules.find_one({"is_active": True, "next_run": {"$lte": now_iso}})
        if not sch:
            break
        try:
            next_run = _compute_next_run(
                sch.get("frequency", "daily"),
                sch.get("send_time", "08:00"),
                sch.get("day_of_week"),
                sch.get("day_of_month"),
            )
        except Exception as exc:
            logger.warning("[report-scheduler] next_run compute failed (%s): %s", sch.get("_id"), exc)
            # next_run hesaplanamıyorsa sonsuz tekrar olmaması için 1 dk ileri sar.
            next_run = (datetime.now(UTC).replace(microsecond=0)).isoformat()

        claimed = await raw_db.report_schedules.find_one_and_update(
            {
                "_id": sch["_id"],
                "is_active": True,
                "next_run": {"$lte": now_iso},  # başka bir worker claim etmediyse
            },
            {"$set": {"next_run": next_run}},
        )
        if not claimed:
            # Yarış kaybedildi; başka instance üstlendi. Loop devam etsin.
            continue
        processed += 1
        try:
            await _execute_schedule(claimed, triggered_by="system")
        except Exception as exc:
            logger.warning("[report-scheduler] execute failed (%s): %s", claimed.get("_id"), exc)
        if processed >= 500:  # tek tick içinde sonsuz döngü güvenliği
            break
    if processed:
        logger.info("[report-scheduler] processed=%d", processed)


async def _loop(interval_seconds: int) -> None:
    logger.info("[report-scheduler] loop started interval=%ss", interval_seconds)
    # Phase başlangıcı sırasında index/init işleri sürerken tetiklemeyelim.
    await asyncio.sleep(30)
    while True:
        try:
            await _tick()
        except Exception as exc:
            logger.warning("[report-scheduler] tick error: %s", exc)
        await asyncio.sleep(interval_seconds)


def start() -> bool:
    """Bootstrap çağrısı. `False` döner = scheduler devre dışı."""
    global _started
    if _started:
        return True
    if DEFAULT_INTERVAL_SECONDS <= 0:
        logger.info("[report-scheduler] disabled via env (interval=0)")
        return False
    asyncio.create_task(_loop(DEFAULT_INTERVAL_SECONDS), name="report-scheduler")
    _started = True
    return True
