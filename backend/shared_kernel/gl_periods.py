"""General-ledger fiscal period controls.

Every GL post resolves to an explicit tenant period. Calendar-year periods are
created lazily for backward compatibility, then a closed period fails closed.
The deterministic Mongo ``_id`` makes initialization race-safe without relying
on a background migration or a best-effort unique index.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime


class GLPeriodError(ValueError):
    """Posting date cannot be accepted by the fiscal-period policy."""


def normalize_posting_date(value: str | None) -> str:
    raw = (value or datetime.now(UTC).date().isoformat()).strip()
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except (TypeError, ValueError) as exc:
        raise GLPeriodError("Geçersiz muhasebe tarihi; YYYY-MM-DD bekleniyor") from exc


def calendar_periods(tenant_id: str, fiscal_year: int, *, actor: str = "system") -> list[dict]:
    if fiscal_year < 2000 or fiscal_year > 2100:
        raise GLPeriodError("Mali yıl 2000-2100 aralığında olmalıdır")
    periods = []
    created_at = datetime.now(UTC).isoformat()
    for month in range(1, 13):
        last_day = calendar.monthrange(fiscal_year, month)[1]
        period_id = f"{tenant_id}:{fiscal_year}:{month:02d}"
        periods.append(
            {
                "_id": f"gl-period:{period_id}",
                "id": period_id,
                "tenant_id": tenant_id,
                "fiscal_year": fiscal_year,
                "period_no": month,
                "name": f"{fiscal_year}-{month:02d}",
                "start_date": date(fiscal_year, month, 1).isoformat(),
                "end_date": date(fiscal_year, month, last_day).isoformat(),
                "status": "open",
                "created_by": actor,
                "created_at": created_at,
            }
        )
    return periods


async def ensure_calendar_year_periods(db, tenant_id: str, fiscal_year: int, *, actor: str = "system") -> None:
    for period in calendar_periods(tenant_id, fiscal_year, actor=actor):
        await db.gl_periods.update_one(
            {"_id": period["_id"], "tenant_id": tenant_id},
            {"$setOnInsert": period},
            upsert=True,
        )


async def get_period_for_date(db, tenant_id: str, posting_date: str, *, actor: str = "system") -> dict:
    day = normalize_posting_date(posting_date)
    period = await db.gl_periods.find_one(
        {"tenant_id": tenant_id, "start_date": {"$lte": day}, "end_date": {"$gte": day}},
        {"_id": 0},
    )
    if period:
        return period
    await ensure_calendar_year_periods(db, tenant_id, int(day[:4]), actor=actor)
    period = await db.gl_periods.find_one(
        {"tenant_id": tenant_id, "start_date": {"$lte": day}, "end_date": {"$gte": day}},
        {"_id": 0},
    )
    if not period:
        raise GLPeriodError("Muhasebe tarihi için mali dönem oluşturulamadı")
    return period


async def assert_gl_period_open(db, tenant_id: str, posting_date: str, *, actor: str = "system") -> dict:
    period = await get_period_for_date(db, tenant_id, posting_date, actor=actor)
    if period.get("status") != "open":
        raise GLPeriodError(
            f"{period.get('name') or period.get('id')} dönemi kapalı; bu tarihe muhasebe kaydı yapılamaz"
        )
    return period
