"""Legacy TGA scheduler compatibility module.

TGA v6 accepts a complete monthly payload and requires a reviewed net EUR
average price. Therefore unattended daily/backfill delivery is intentionally
disabled; monthly sends are initiated from the KTB report screen.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = int(os.environ.get("TGA_SCHEDULER_INTERVAL_SECONDS", "21600"))  # 6 saat
BACKFILL_DAYS = int(os.environ.get("TGA_BACKFILL_DAYS", "7"))
# Failed outbox kayıtlarını retry için tarama sıklığı (varsayılan 60 sn).
# 0 → retry worker devre dışı.
RETRY_INTERVAL_SECONDS = int(os.environ.get("TGA_RETRY_INTERVAL_SECONDS", "60"))

_started = False
_retry_started = False


async def _tick() -> None:
    """Tek bir tarama: aktif tenant'ları sırayla işler."""
    from core.tga_outbound import list_enabled_tenants, send_batch

    end_date = (datetime.now(UTC) - timedelta(days=1)).date()  # dün dahil son 7 gün
    try:
        tenants = await list_enabled_tenants()
    except Exception as exc:
        logger.warning("[tga-scheduler] list_enabled_tenants failed: %s", exc)
        return
    if not tenants:
        return
    for tid in tenants:
        try:
            res = await send_batch(tid, end_date, days=BACKFILL_DAYS, triggered_by="scheduler")
            logger.info("[tga-scheduler] tenant=%s status=%s http=%s", tid, res.get("status"), res.get("http_status"))
        except Exception as exc:
            logger.warning("[tga-scheduler] tenant=%s send failed: %s", tid, exc)


async def _loop(interval_seconds: int) -> None:
    logger.info("[tga-scheduler] loop started interval=%ss backfill=%sd", interval_seconds, BACKFILL_DAYS)
    # Başlangıçta küçük gecikme — diğer phase'lerin index oluşturmasını bekle.
    await asyncio.sleep(60)
    while True:
        try:
            await _tick()
        except Exception as exc:
            logger.warning("[tga-scheduler] tick error: %s", exc)
        await asyncio.sleep(interval_seconds)


async def _retry_tick() -> None:
    """Failed outbox kayıtları için retry tarama."""
    from core.tga_outbound import retry_failed_outbox

    try:
        stats = await retry_failed_outbox()
    except Exception as exc:
        logger.warning("[tga-retry] tick error: %s", exc)
        return
    if stats.get("attempted"):
        logger.info(
            "[tga-retry] attempted=%s succeeded=%s failed=%s alerted=%s skipped=%s",
            stats.get("attempted"),
            stats.get("succeeded"),
            stats.get("failed"),
            stats.get("alerted"),
            stats.get("skipped"),
        )


async def _retry_loop(interval_seconds: int) -> None:
    logger.info("[tga-retry] loop started interval=%ss", interval_seconds)
    # Index'lerin oluşmasını bekle.
    await asyncio.sleep(60)
    while True:
        await _retry_tick()
        await asyncio.sleep(interval_seconds)


def start() -> bool:
    """Keep legacy bootstrap imports safe without performing old API calls."""
    logger.info("[tga-scheduler] unattended legacy daily flow disabled for TGA v6")
    return False
