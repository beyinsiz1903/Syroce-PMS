"""
Night Audit — Timezone helper (Task #362)

The in-process asyncio scheduler that used to live here has been retired in
favour of per-tenant Celery tasks:

  * ``celery_tasks.night_audit_dispatch_task`` — a once-a-minute beat dispatcher
    that enqueues each tenant's audit when its LOCAL wall-clock time matches.
  * ``celery_tasks.night_audit_for_tenant``    — runs the hardened engine for a
    single tenant under ``tenant_context`` and records the outcome.

Only the DST-aware UTC->local conversion is kept here, because the dispatcher
needs it to decide whether a tenant's configured ``hour:minute`` has arrived in
that tenant's own timezone.
"""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def utc_to_local(utc_dt: datetime, tz_name: str) -> datetime:
    """Convert a UTC datetime to a tenant's local wall-clock time.

    Uses :mod:`zoneinfo` so daylight-saving transitions are handled correctly
    (the old hand-written offset table ignored DST and silently shifted any
    unlisted timezone to Istanbul +3). Unknown/invalid IANA names now fail
    *safe* to UTC with a warning instead of guessing a wrong offset.
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=UTC)
    if not tz_name:
        return utc_dt.astimezone(UTC)
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError) as exc:
        logger.warning(
            "Night-audit schedule has unknown timezone %r; falling back to UTC (%s)",
            tz_name,
            exc,
        )
        tz = UTC
    return utc_dt.astimezone(tz)
