"""Agency performance and receivables report (see core.agency_reports).

Hotel (PMS JWT):   GET /api/marketplace/hotel/reports/agency-performance
Agency (portal):   GET /api/marketplace/v1/reports/hotel-performance
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from core.agency_reports import build_report
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from routers.marketplace_b2b import _require_hotel_admin, get_marketplace_agency

hotel_router = APIRouter(prefix="/api/marketplace/hotel/reports", tags=["Marketplace / Reports (hotel)"])
agency_router = APIRouter(prefix="/api/marketplace/v1/reports", tags=["Marketplace / Reports (agency)"])


def _period(period_start: str | None, period_end: str | None) -> tuple[str, str, date]:
    """Check-in period for performance; default: the current month."""
    today = datetime.now(UTC).date()
    try:
        start = date.fromisoformat(period_start) if period_start else today.replace(day=1)
        end = date.fromisoformat(period_end) if period_end else today
    except ValueError as exc:
        raise HTTPException(422, "Tarih YYYY-AA-GG biçiminde olmalıdır") from exc
    if end < start:
        raise HTTPException(422, "Dönem bitişi başlangıçtan önce olamaz")
    if (end - start).days > 366:
        raise HTTPException(422, "Dönem en fazla bir yıl olabilir")
    return start.isoformat(), end.isoformat(), today


@hotel_router.get("/agency-performance")
async def hotel_agency_performance(period_start: str | None = Query(None), period_end: str | None = Query(None),
                                   current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    start, end, today = _period(period_start, period_end)
    return await build_report(get_system_db(), side="hotel", scope={"tenant_id": tenant_id},
                              period_start=start, period_end=end, today=today)


@agency_router.get("/hotel-performance")
async def agency_hotel_performance(period_start: str | None = Query(None), period_end: str | None = Query(None),
                                   agency: dict = Depends(get_marketplace_agency)):
    start, end, today = _period(period_start, period_end)
    return await build_report(get_system_db(), side="agency", scope={"agency_id": agency["agency_id"]},
                              period_start=start, period_end=end, today=today)
