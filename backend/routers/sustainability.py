"""Sustainability: consumption records and the carbon report, per hotel.

Every endpoint needs a signed-in hotel user; reading needs ``view_reports``,
entering consumption ``manage_sustainability``. Records are stored per hotel
(``sustainability_records``, ``tenant_id``) and every query is scoped to the
caller's hotel.

The report:
* emissions = consumption x a fixed factor (kgCO2e per unit, below);
* a record whose period runs past the report period is prorated by days
  (``allocation``), and the response says how many were — an estimate, not
  a measured split;
* room nights are the hotel's real occupied nights in the period (bookings
  not cancelled / no-show, each night counted once per booking); with none,
  the per-room-night figure is not computed instead of inventing nights.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/sustainability", tags=["Sustainability"])

# kgCO2e per unit. Fixed reference factors, not a certified inventory.
EMISSION_FACTORS = {
    "electricity": {"name": "Purchased Electricity", "scope": 2, "unit": "kWh", "factor": 0.429},
    "natural_gas": {"name": "Natural Gas", "scope": 1, "unit": "m3", "factor": 2.02266},
    "water": {"name": "Water Consumption", "scope": 3, "unit": "m3", "factor": 0.344},
    "waste": {"name": "General Waste", "scope": 3, "unit": "kg", "factor": 0.450},
}
ALLOCATION = "Kayıt dönemi rapor dönemini aşıyorsa tüketim gün oranında bölüştürülür (tahmin)."
NOT_OCCUPYING = ("cancelled", "no_show", "noshow")
MAX_REPORT_DAYS = 366


class FactorOut(BaseModel):
    id: str
    name: str
    scope: int
    unit: str
    factor: float


class RecordIn(BaseModel):
    consumption_type: str = Field(..., description="electricity, natural_gas, water, waste")
    period_start: date
    period_end: date
    amount: float = Field(..., ge=0)
    evidence_url: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        return self


class RecordOut(RecordIn):
    id: str
    scope: int
    emissions_kg_co2e: float


class ReportOut(BaseModel):
    period_start: date
    period_end: date
    total_scope_1: float
    total_scope_2: float
    total_scope_3: float
    total_emissions: float
    total_room_nights: int
    emissions_per_room_night: float | None
    record_count: int
    prorated_record_count: int
    allocation: str
    room_nights_source: str = "bookings"


def _tenant(user: User) -> str:
    if not user.tenant_id:
        raise HTTPException(403, "Bu işlem için bir otel hesabı gerekir")
    return user.tenant_id


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


@router.get("/factors", response_model=list[FactorOut])
async def list_factors(current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_reports"))):
    _tenant(current_user)
    return [{"id": k, **v} for k, v in EMISSION_FACTORS.items()]


@router.post("/records", response_model=RecordOut)
async def create_record(record_in: RecordIn, current_user: User = Depends(get_current_user),
                        _perm=Depends(require_op("manage_sustainability"))):
    tenant_id = _tenant(current_user)
    factor_info = EMISSION_FACTORS.get(record_in.consumption_type)
    if not factor_info:
        raise HTTPException(status_code=400, detail="Invalid consumption type.")
    record = RecordOut(id=str(uuid.uuid4()), scope=factor_info["scope"],
                       emissions_kg_co2e=round(record_in.amount * factor_info["factor"], 2), **record_in.model_dump())
    doc = {**record.model_dump(mode="json"), "tenant_id": tenant_id,
           "created_by": current_user.id, "created_at": datetime.now(UTC).isoformat()}
    await db.sustainability_records.insert_one(doc)
    return record


@router.get("/records", response_model=list[RecordOut])
async def list_records(current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_reports"))):
    tenant_id = _tenant(current_user)
    return await db.sustainability_records.find({"tenant_id": tenant_id}, {"_id": 0}).sort("period_start", -1).to_list(1000)


async def occupied_room_nights(tenant_id: str, start: date, end: date) -> int:
    """Nights in [start, end] covered by the hotel's bookings that occupy a room."""
    nights = 0
    query = {"tenant_id": tenant_id, "status": {"$nin": list(NOT_OCCUPYING)},
             "check_in": {"$lte": end.isoformat() + "T23:59:59.999999"}, "check_out": {"$gt": start.isoformat()}}
    async for booking in db.bookings.find(query, {"_id": 0, "check_in": 1, "check_out": 1}):
        arrive, depart = _day(booking.get("check_in")), _day(booking.get("check_out"))
        if not arrive or not depart:
            continue
        first, last_exclusive = max(arrive, start), min(depart, date.fromordinal(end.toordinal() + 1))
        nights += max(0, (last_exclusive - first).days)
    return nights


@router.get("/report", response_model=ReportOut)
async def generate_report(start_date: date = Query(...), end_date: date = Query(...),
                          current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_reports"))):
    tenant_id = _tenant(current_user)
    if end_date < start_date:
        raise HTTPException(422, "Bitiş tarihi başlangıçtan önce olamaz")
    if (end_date - start_date).days + 1 > MAX_REPORT_DAYS:
        raise HTTPException(422, "Rapor dönemi en fazla bir yıl olabilir")

    scopes = {1: 0.0, 2: 0.0, 3: 0.0}
    count = prorated = 0
    query = {"tenant_id": tenant_id, "period_start": {"$lte": end_date.isoformat()}, "period_end": {"$gte": start_date.isoformat()}}
    async for record in db.sustainability_records.find(query, {"_id": 0}):
        r_start, r_end = _day(record.get("period_start")), _day(record.get("period_end"))
        if not r_start or not r_end:
            continue
        share = 1.0
        overlap = (min(r_end, end_date) - max(r_start, start_date)).days + 1
        length = (r_end - r_start).days + 1
        if overlap < length:
            share = overlap / length
            prorated += 1
        count += 1
        scopes[int(record.get("scope") or 0)] = scopes.get(int(record.get("scope") or 0), 0.0) + float(record.get("emissions_kg_co2e") or 0) * share

    total = scopes[1] + scopes[2] + scopes[3]
    room_nights = await occupied_room_nights(tenant_id, start_date, end_date)
    return ReportOut(
        period_start=start_date, period_end=end_date,
        total_scope_1=round(scopes[1], 2), total_scope_2=round(scopes[2], 2), total_scope_3=round(scopes[3], 2),
        total_emissions=round(total, 2), total_room_nights=room_nights,
        emissions_per_room_night=round(total / room_nights, 4) if room_nights else None,
        record_count=count, prorated_record_count=prorated, allocation=ALLOCATION,
    )
