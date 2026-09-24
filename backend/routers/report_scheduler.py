"""
Report Email Scheduler — Otomatik Rapor E-posta Zamanlayici
============================================================
Endpoints:
  POST   /api/report-scheduler/schedules          — Yeni zamanlama olustur
  GET    /api/report-scheduler/schedules          — Tüm zamanlamalari listele
  GET    /api/report-scheduler/schedules/{id}     — Tek zamanlama detayi
  PUT    /api/report-scheduler/schedules/{id}     — Zamanlama guncelle
  DELETE /api/report-scheduler/schedules/{id}     — Zamanlama sil
  POST   /api/report-scheduler/schedules/{id}/toggle — Aktif/pasif toggle
  POST   /api/report-scheduler/schedules/{id}/send-now — Manuel tetikleme
  GET    /api/report-scheduler/history            — Gönderim gecmisi
  GET    /api/report-scheduler/history/{id}       — Tek gönderim detayi
  POST   /api/report-scheduler/history/{id}/retry — Başarısız gönderimleri tekrar dene
  GET    /api/report-scheduler/report-types       — Mevcut rapor tipleri
"""

import asyncio
import logging
import os
import re as _re
import traceback
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from cache_manager import cached
from core.database import db
from core.security import _is_super_admin, get_current_user
from models.enums import UserRole
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v98 DW


def _invalidate_scheduler_cache(tenant_id: str) -> None:
    """Drop scheduler list/history caches for a tenant after writes."""
    for prefix in ("report_scheduler_schedules", "report_scheduler_history"):
        try:
            _cache.safe_invalidate(tenant_id, prefix)
        except Exception as e:  # pragma: no cover — best-effort
            logger.debug("scheduler cache invalidation skipped (%s): %s", prefix, e)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report-scheduler", tags=["Report Scheduler"])

HOTEL_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.ADMIN,
    "super_admin",
    "admin",
    "manager",
    "staff",
}

MANAGER_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.ADMIN,
    "super_admin",
    "admin",
    "manager",
}


def _require_hotel_role(user: User):
    if _is_super_admin(user):
        return
    if user.role in HOTEL_ROLES:
        return
    extra_roles = getattr(user, "roles", None) or []
    if isinstance(extra_roles, list) and any((r in HOTEL_ROLES) for r in extra_roles):
        return
    raise HTTPException(status_code=403, detail="Bu sayfaya erisim yetkiniz yok.")


def _require_manager_role(user: User):
    if _is_super_admin(user):
        return
    if user.role in MANAGER_ROLES:
        return
    extra_roles = getattr(user, "roles", None) or []
    if isinstance(extra_roles, list) and any((r in MANAGER_ROLES) for r in extra_roles):
        return
    raise HTTPException(status_code=403, detail="Bu islemi yapmak icin yonetici yetkisi gereklidir.")


REPORT_TYPES = [
    {"key": "daily_summary", "label": "Günlük Özet Raporu", "description": "Günlük doluluk, gelir ve operasyon özeti"},
    {"key": "revenue", "label": "Gelir Raporu", "description": "Detaylı gelir analizi ve kıyaslama"},
    {"key": "occupancy", "label": "Doluluk Raporu", "description": "Oda doluluk oranları ve trendler"},
    {"key": "reservations", "label": "Rezervasyon Raporu", "description": "Rezervasyon listesi ve istatistikler"},
    {"key": "guest_analytics", "label": "Misafir Analitik", "description": "Misafir profili ve dağılım raporları"},
    {"key": "adr_revpar", "label": "ADR / RevPAR", "description": "Ortalama günlük fiyat ve oda başına gelir"},
    {"key": "channel_performance", "label": "Kanal Performansı", "description": "OTA ve satış kanalı bazlı analiz"},
    {"key": "b2b_analytics", "label": "B2B Analitik", "description": "Acente ve API kullanım analitikleri"},
    {"key": "housekeeping", "label": "Housekeeping Raporu", "description": "Kat hizmetleri performans raporu"},
    {"key": "financial", "label": "Finansal Rapor", "description": "Genel muhasebe ve folio özeti"},
    {"key": "flash_report", "label": "Flash Report", "description": "Anlık operasyon durum raporu"},
]

FREQUENCY_OPTIONS = ["daily", "weekly", "monthly"]
FORMAT_OPTIONS = ["pdf", "csv", "link"]
DAYS_OF_WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_type: str
    frequency: str
    # Pydantic v2: list constraints use min_length/max_length, not min_items.
    recipients: list[str] = Field(..., min_length=1)
    format: str = "pdf"
    send_time: str = "08:00"
    day_of_week: str | None = None
    day_of_month: int | None = None
    include_charts: bool = True
    notes: str | None = None
    date_range: str = "auto"


class ScheduleUpdate(BaseModel):
    name: str | None = None
    report_type: str | None = None
    frequency: str | None = None
    recipients: list[str] | None = None
    format: str | None = None
    send_time: str | None = None
    day_of_week: str | None = None
    day_of_month: int | None = None
    include_charts: bool | None = None
    notes: str | None = None
    is_active: bool | None = None
    date_range: str | None = None


_TIME_RE = _re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _get_tenant_id(user: User) -> str:
    return getattr(user, "tenant_id", "default")


async def _get_schedule_for_tenant(schedule_id: str, user: User) -> dict:
    schedule = await db.report_schedules.find_one(
        {
            "_id": schedule_id,
            "tenant_id": _get_tenant_id(user),
        }
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Zamanlama bulunamadi")
    return schedule


async def _get_history_for_tenant(history_id: str, user: User) -> dict:
    entry = await db.report_schedule_history.find_one(
        {
            "_id": history_id,
            "tenant_id": _get_tenant_id(user),
        }
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Gönderim kaydi bulunamadi")
    return entry


def _validate_schedule_fields(data: dict):
    if data.get("report_type") and data["report_type"] not in [r["key"] for r in REPORT_TYPES]:
        raise HTTPException(status_code=400, detail=f"Geçersiz rapor tipi: {data['report_type']}")
    if data.get("frequency") and data["frequency"] not in FREQUENCY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Geçersiz frekans: {data['frequency']}")
    if data.get("format") and data["format"] not in FORMAT_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Geçersiz format: {data['format']}")
    if data.get("send_time") and not _TIME_RE.match(data["send_time"]):
        raise HTTPException(status_code=400, detail="Geçersiz saat formatı, HH:MM olmalıdır")
    if data.get("day_of_week") and data["day_of_week"] not in DAYS_OF_WEEK:
        raise HTTPException(status_code=400, detail=f"Geçersiz gün: {data['day_of_week']}")
    if data.get("day_of_month") is not None:
        if not (1 <= data["day_of_month"] <= 28):
            raise HTTPException(status_code=400, detail="Ayın günü 1-28 arası olmalıdır (kısa ayları kapsamak için)")
    if data.get("recipients"):
        for email in data["recipients"]:
            if not _EMAIL_RE.match(email):
                raise HTTPException(status_code=400, detail=f"Geçersiz e-posta: {email}")
    # Frekans-bağımlı zorunlu alanlar
    freq = data.get("frequency")
    if freq == "weekly" and "frequency" in data and not data.get("day_of_week"):
        raise HTTPException(status_code=400, detail="Haftalık frekans için 'gönderim günü' zorunludur")
    if freq == "monthly" and "frequency" in data and data.get("day_of_month") is None:
        raise HTTPException(status_code=400, detail="Aylık frekans için 'ayın günü' zorunludur")


async def _get_tenant_timezone(tenant_id: str) -> str:
    settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "timezone": 1}) or {}
    timezone_name = settings.get("timezone") or "Europe/Istanbul"
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
        timezone_name = "Europe/Istanbul"
    return timezone_name


def _compute_next_run(
    frequency: str,
    send_time: str,
    day_of_week: str | None,
    day_of_month: int | None,
    timezone_name: str = "Europe/Istanbul",
    *,
    now_utc: datetime | None = None,
) -> str:
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
        timezone = ZoneInfo("Europe/Istanbul")
    reference = now_utc or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    now = reference.astimezone(timezone)
    hour, minute = (int(x) for x in send_time.split(":"))

    if frequency == "daily":
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
    elif frequency == "weekly":
        target_day = DAYS_OF_WEEK.index(day_of_week or "monday")
        days_ahead = target_day - now.weekday()
        candidate = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            days_ahead += 7
        next_run = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif frequency == "monthly":
        dom = day_of_month or 1
        next_run = now.replace(day=dom, hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            month = now.month + 1
            year = now.year
            if month > 12:
                month = 1
                year += 1
            next_run = next_run.replace(year=year, month=month)
    else:
        next_run = now + timedelta(days=1)

    return next_run.astimezone(UTC).isoformat()


@router.get("/report-types")
@cached(ttl=3600, key_prefix="report_scheduler_types")  # static lookup, 1h
async def get_report_types(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    _require_manager_role(current_user)
    return {"report_types": REPORT_TYPES, "frequencies": FREQUENCY_OPTIONS, "formats": FORMAT_OPTIONS, "days_of_week": DAYS_OF_WEEK}


@router.post("/schedules")
async def create_schedule(
    body: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    data = body.model_dump()
    _validate_schedule_fields(data)
    tenant_id = _get_tenant_id(current_user)
    timezone_name = await _get_tenant_timezone(tenant_id)

    schedule = {
        "_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timezone": timezone_name,
        "created_by": current_user.email,
        "created_by_name": getattr(current_user, "name", current_user.email),
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "is_active": True,
        "next_run": _compute_next_run(
            data["frequency"],
            data["send_time"],
            data.get("day_of_week"),
            data.get("day_of_month"),
            timezone_name,
        ),
        "total_sent": 0,
        "total_failed": 0,
        "last_sent_at": None,
        "last_status": None,
        **data,
    }

    await db.report_schedules.insert_one(schedule)
    logger.info(f"Schedule created: {schedule['_id']} by {current_user.email}")
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return {"message": "Zamanlama olusturuldu", "schedule": schedule}


@router.get("/schedules")
@cached(ttl=60, key_prefix="report_scheduler_schedules")
async def list_schedules(
    current_user: User = Depends(get_current_user),
    _nocache: bool = Query(False, alias="nocache"),
    _perm=Depends(require_op("view_reports")),
):
    # Alıcı e-postaları + zamanlama notları kişisel veri içerebilir → manager+.
    _require_manager_role(current_user)

    cursor = db.report_schedules.find({"tenant_id": _get_tenant_id(current_user)}).sort("created_at", -1)
    schedules = await cursor.to_list(length=200)
    return {"schedules": schedules, "total": len(schedules)}


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    _require_manager_role(current_user)

    schedule = await _get_schedule_for_tenant(schedule_id, current_user)
    return {"schedule": schedule}


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    schedule = await _get_schedule_for_tenant(schedule_id, current_user)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    _validate_schedule_fields(updates)

    if any(k in updates for k in ("frequency", "send_time", "day_of_week", "day_of_month")):
        freq = updates.get("frequency", schedule["frequency"])
        st = updates.get("send_time", schedule["send_time"])
        dow = updates.get("day_of_week", schedule.get("day_of_week"))
        dom = updates.get("day_of_month", schedule.get("day_of_month"))
        timezone_name = schedule.get("timezone") or await _get_tenant_timezone(_get_tenant_id(current_user))
        updates["timezone"] = timezone_name
        updates["next_run"] = _compute_next_run(freq, st, dow, dom, timezone_name)

    updates["updated_at"] = datetime.now(UTC).isoformat()
    tenant_filter = {"_id": schedule_id, "tenant_id": _get_tenant_id(current_user)}
    await db.report_schedules.update_one(tenant_filter, {"$set": updates})

    updated = await db.report_schedules.find_one(tenant_filter)
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return {"message": "Zamanlama guncellendi", "schedule": updated}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    await _get_schedule_for_tenant(schedule_id, current_user)
    tenant_filter = {"_id": schedule_id, "tenant_id": _get_tenant_id(current_user)}
    await db.report_schedules.delete_one(tenant_filter)

    await db.report_schedule_history.delete_many({"schedule_id": schedule_id, "tenant_id": _get_tenant_id(current_user)})
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return {"message": "Zamanlama silindi"}


@router.post("/schedules/{schedule_id}/toggle")
async def toggle_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    schedule = await _get_schedule_for_tenant(schedule_id, current_user)

    new_status = not schedule.get("is_active", True)
    updates = {"is_active": new_status, "updated_at": datetime.now(UTC).isoformat()}
    if new_status:
        updates["next_run"] = _compute_next_run(
            schedule["frequency"],
            schedule["send_time"],
            schedule.get("day_of_week"),
            schedule.get("day_of_month"),
            schedule.get("timezone") or await _get_tenant_timezone(_get_tenant_id(current_user)),
        )

    await db.report_schedules.update_one(
        {"_id": schedule_id, "tenant_id": _get_tenant_id(current_user)},
        {"$set": updates},
    )
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return {"message": f"Zamanlama {'aktif' if new_status else 'pasif'} edildi", "is_active": new_status}


@router.post("/schedules/{schedule_id}/send-now")
async def send_now(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    schedule = await _get_schedule_for_tenant(schedule_id, current_user)

    result = await _execute_schedule(schedule, triggered_by=current_user.email)
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return result


@router.get("/history")
@cached(ttl=60, key_prefix="report_scheduler_history")
async def get_history(
    schedule_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    _nocache: bool = Query(False, alias="nocache"),
    _perm=Depends(require_op("view_reports")),
):
    _require_manager_role(current_user)

    query = {"tenant_id": _get_tenant_id(current_user)}
    if schedule_id:
        query["schedule_id"] = schedule_id
    if status:
        query["status"] = status

    cursor = db.report_schedule_history.find(query).sort("sent_at", -1).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"history": history, "total": len(history)}


@router.get("/history/{history_id}")
async def get_history_detail(
    history_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    _require_manager_role(current_user)

    entry = await _get_history_for_tenant(history_id, current_user)
    return {"entry": entry}


@router.post("/history/{history_id}/retry")
async def retry_send(
    history_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    entry = await _get_history_for_tenant(history_id, current_user)

    if entry.get("status") != "failed":
        raise HTTPException(status_code=400, detail="Sadece başarısız gönderimler tekrar denenebilir")

    schedule = await _get_schedule_for_tenant(entry["schedule_id"], current_user)

    await db.report_schedule_history.update_one(
        {"_id": history_id, "tenant_id": _get_tenant_id(current_user)},
        {"$set": {"status": "retrying", "retry_count": entry.get("retry_count", 0) + 1}},
    )

    result = await _execute_schedule(schedule, triggered_by=current_user.email, history_id=history_id)
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return result


async def _build_report_payload(schedule: dict, now: datetime) -> dict:
    """Rapor tipi başına gerçek veri toplar.

    Döner: {rows: [{label, value}], generated_at, range, notes}
    Veri toplama hataları çağırana aktarılır; hatalı/boş rapor başarıyla
    gönderilmiş gibi kaydedilmez.
    """
    from core.business_date_service import accounting_day_match, ensure_business_date_initialized
    from core.database import _raw_db as raw_db
    from core.tenant_currency import get_tenant_currency
    from modules.pms_core.stay_night_metrics import load_stay_night_metrics

    tenant_id = schedule.get("tenant_id") or "default"
    rtype = schedule.get("report_type", "")
    business_state = await ensure_business_date_initialized(raw_db, tenant_id)
    today_iso = str(business_state["business_date"])[:10]
    day_start = datetime.fromisoformat(today_iso).replace(tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    currency_code, _ = await get_tenant_currency(tenant_id)
    rows: list[dict] = []
    notes: str | None = None

    try:
        if rtype in ("daily_summary", "occupancy", "reservations", "flash_report"):
            arrivals = await raw_db.bookings.count_documents(
                {
                    "tenant_id": tenant_id,
                    "$or": [
                        {"check_in": today_iso},
                        {"check_in": {"$gte": day_start, "$lt": day_end}},
                        {"check_in": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}},
                    ],
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house", "arriving"]},
                }
            )
            departures = await raw_db.bookings.count_documents(
                {
                    "tenant_id": tenant_id,
                    "$or": [
                        {"check_out": today_iso},
                        {"check_out": {"$gte": day_start, "$lt": day_end}},
                        {"check_out": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}},
                    ],
                    "status": {"$in": ["checked_in", "in_house", "checked_out", "departing"]},
                }
            )
            metrics = (await load_stay_night_metrics(raw_db, tenant_id, day_start.date(), day_start.date(), actual_only=True))[0]
            in_house = metrics["occupied_rooms"]
            total_rooms = metrics["total_rooms"]
            occ = metrics["occupancy_rate"]
            rows = [
                {"label": "PMS iş tarihi", "value": day_start.strftime("%d.%m.%Y")},
                {"label": "Bugün gelen (arrivals)", "value": arrivals},
                {"label": "Bugün çıkan (departures)", "value": departures},
                {"label": "Evde olan (in-house)", "value": in_house},
                {"label": "Toplam oda", "value": total_rooms},
                {"label": "Doluluk %", "value": occ},
            ]
        elif rtype in ("revenue", "adr_revpar", "financial"):
            charges = await raw_db.folio_charges.find(
                {
                    "tenant_id": tenant_id,
                    "voided": {"$ne": True},
                    **accounting_day_match(
                        today_iso,
                        {"date": today_iso},
                        {"date": {"$gte": day_start, "$lt": day_end}},
                        {"created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}},
                    ),
                },
                {"_id": 0, "total": 1, "amount": 1, "charge_category": 1, "charge_type": 1},
            ).to_list(50000)
            total = round(sum(float(item.get("total") or item.get("amount") or 0) for item in charges), 2)
            room_revenue = round(
                sum(
                    float(item.get("total") or item.get("amount") or 0)
                    for item in charges
                    if str(item.get("charge_category") or item.get("charge_type") or "").lower()
                    in {"room", "room_charge", "accommodation", "lodging", "konaklama"}
                ),
                2,
            )
            metrics = (await load_stay_night_metrics(raw_db, tenant_id, day_start.date(), day_start.date(), actual_only=True))[0]
            occupied_rooms = metrics["occupied_rooms"]
            total_rooms = metrics["total_rooms"]
            effective_room_revenue = room_revenue if room_revenue else metrics["revenue"]
            adr = round(effective_room_revenue / occupied_rooms, 2) if occupied_rooms else 0
            revpar = round(effective_room_revenue / total_rooms, 2) if total_rooms else 0
            rows = [
                {"label": "PMS iş tarihi", "value": day_start.strftime("%d.%m.%Y")},
                {"label": f"Toplam gelir ({currency_code})", "value": f"{total:,.2f}".replace(",", ".")},
                {"label": "Folyo kayıt sayısı", "value": len(charges)},
                {"label": "ADR (Ortalama Günlük Fiyat)", "value": adr},
                {"label": "RevPAR (Oda Başı Gelir)", "value": revpar},
            ]
        elif rtype == "guest_analytics":
            new_guests = await raw_db.guests.count_documents(
                {
                    "tenant_id": tenant_id,
                    "$or": [
                        {"created_at": {"$regex": f"^{today_iso}"}},
                        {"created_at": {"$gte": day_start, "$lt": day_end}},
                    ],
                }
            )
            total_guests = await raw_db.guests.count_documents({"tenant_id": tenant_id})
            rows = [
                {"label": "Bugün eklenen misafir", "value": new_guests},
                {"label": "Toplam misafir", "value": total_guests},
            ]
        elif rtype == "channel_performance":
            pipeline = [
                {"$match": {"tenant_id": tenant_id}},
                {"$group": {"_id": "$channel", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ]
            agg = await raw_db.bookings.aggregate(pipeline).to_list(length=10)
            rows = [{"label": (a["_id"] or "Direkt"), "value": a["count"]} for a in agg]
            if not rows:
                notes = "Bu tenant için kanal verisi bulunamadı."
        elif rtype == "housekeeping":
            for st in ("clean", "dirty", "inspected", "out_of_order"):
                cnt = await raw_db.rooms.count_documents(
                    {
                        "tenant_id": tenant_id,
                        "housekeeping_status": st,
                    }
                )
                rows.append({"label": f"Oda durumu — {st}", "value": cnt})
        elif rtype == "b2b_analytics":
            cnt = await raw_db.bookings.count_documents(
                {
                    "tenant_id": tenant_id,
                    "agency_id": {"$exists": True, "$ne": None},
                }
            )
            rows = [{"label": "Acente kanalı rezervasyon (toplam)", "value": cnt}]
        else:
            raise ValueError(f"'{rtype}' için zamanlanmış rapor hazırlayıcı tanımlı değil")
    except Exception:
        logger.exception("[report-scheduler] payload build failed (%s)", rtype)
        raise

    return {
        "rows": rows,
        "generated_at": now.isoformat(),
        "range": today_iso,
        "notes": notes,
    }


def _payload_to_csv(report_label: str, payload: dict) -> bytes:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([report_label])
    w.writerow(["Üretim:", payload.get("generated_at", "")])
    w.writerow([])
    w.writerow(["Metrik", "Değer"])
    for r in payload.get("rows", []):
        w.writerow([r.get("label", ""), r.get("value", "")])
    if payload.get("notes"):
        w.writerow([])
        w.writerow(["Not:", payload["notes"]])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _payload_to_pdf(report_label: str, payload: dict, html: str) -> bytes | None:
    try:
        from weasyprint import HTML  # type: ignore

        return HTML(string=html).write_pdf()
    except Exception as exc:
        logger.warning("[report-scheduler] PDF render failed: %s", exc)
        return None


def _resolve_app_url(schedule_id: str) -> str:
    base = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")
    if not base:
        return ""
    return f"{base}/app/raporlar?schedule_id={schedule_id}"


async def _execute_schedule(schedule: dict, triggered_by: str = "system", history_id: str | None = None):
    now = datetime.now(UTC)
    report_type_info = next((r for r in REPORT_TYPES if r["key"] == schedule["report_type"]), None)
    report_label = report_type_info["label"] if report_type_info else schedule["report_type"]
    fmt = (schedule.get("format") or "pdf").lower()

    hid = history_id or str(uuid.uuid4())

    history_entry = {
        "_id": hid,
        "schedule_id": schedule["_id"],
        "schedule_name": schedule["name"],
        "tenant_id": schedule.get("tenant_id", "default"),
        "report_type": schedule["report_type"],
        "report_label": report_label,
        "format": fmt,
        "recipients": schedule["recipients"],
        "triggered_by": triggered_by,
        "sent_at": now.isoformat(),
        "status": "processing",
        "error_message": None,
        "retry_count": 0,
        "delivery_details": {},
    }

    if not history_id:
        await db.report_schedule_history.insert_one(history_entry)

    try:
        from modules.messaging.email_service import email_service

        # 1) Rapor verisini topla
        payload = await _build_report_payload(schedule, now)
        report_date = str(payload.get("range") or now.date().isoformat())[:10]
        try:
            report_date_label = datetime.fromisoformat(report_date).strftime("%d.%m.%Y")
        except ValueError:
            report_date_label = report_date

        # 2) E-posta içeriği
        subject = f"Syroce Rapor: {report_label} — {report_date_label}"
        app_url = _resolve_app_url(schedule["_id"])
        html_content = _build_report_email_html(schedule, report_label, now, payload, app_url)
        text_lines = [
            report_label,
            f"Tarih: {now.strftime('%d.%m.%Y %H:%M')}",
            f"Format: {fmt.upper()}",
            "",
            "Özet:",
        ]
        for r in payload.get("rows", []):
            text_lines.append(f"  • {r.get('label')}: {r.get('value')}")
        if payload.get("notes"):
            text_lines += ["", f"Not: {payload['notes']}"]
        text_content = "\n".join(text_lines)

        # 3) Ek (CSV/PDF) üret
        attachments: list = []
        date_tag = report_date.replace("-", "")
        if fmt == "csv":
            attachments.append(
                (
                    f"{schedule['report_type']}_{date_tag}.csv",
                    "text/csv",
                    _payload_to_csv(report_label, payload),
                )
            )
        elif fmt == "pdf":
            pdf_bytes = _payload_to_pdf(report_label, payload, html_content)
            if pdf_bytes:
                attachments.append(
                    (
                        f"{schedule['report_type']}_{date_tag}.pdf",
                        "application/pdf",
                        pdf_bytes,
                    )
                )
            else:
                # PDF üretilemediyse en azından CSV ile fallback gönder.
                attachments.append(
                    (
                        f"{schedule['report_type']}_{date_tag}.csv",
                        "text/csv",
                        _payload_to_csv(report_label, payload),
                    )
                )

        # 4) Gönderim
        sent_count = 0
        failed_recipients = []
        mock_recipients = []
        smtp_ready = email_service.mode == "production" and email_service.smtp_username and email_service.smtp_password
        for recipient in schedule["recipients"]:
            try:
                if smtp_ready:
                    # SMTP senkron — event loop'u bloklamasın.
                    success = await asyncio.to_thread(
                        email_service._send_email_smtp,
                        recipient,
                        subject,
                        html_content,
                        text_content,
                        attachments,
                    )
                    if success:
                        sent_count += 1
                    else:
                        failed_recipients.append(recipient)
                else:
                    # SMTP yapılandırılmamış: gerçek gönderim YOK.
                    # Eskiden success=True dönüyordu → KPI yalan söylüyordu (bug brief P1).
                    # Şimdi ayrı `mock` durumu olarak işaretliyoruz.
                    logger.info(f"[MOCK] Report email -> {recipient}: {subject} (SMTP not configured)")
                    mock_recipients.append(recipient)
            except Exception as e:
                logger.error(f"Email send failed to {recipient}: {e}")
                failed_recipients.append(recipient)

        # 5) Status hesapla
        total = len(schedule["recipients"])
        if mock_recipients and not failed_recipients and sent_count == 0:
            status = "mock"
            error_msg = "SMTP yapılandırılmadığı için gerçek e-posta gönderilmedi (mock mode)."
        elif failed_recipients and sent_count == 0:
            status = "failed"
            error_msg = f"Tüm alıcılara gönderim başarısız: {', '.join(failed_recipients)}"
        elif failed_recipients:
            status = "partial"
            error_msg = f"Bazı alıcılara gönderilemedi: {', '.join(failed_recipients)}"
        else:
            status = "sent"
            error_msg = None

        await db.report_schedule_history.update_one(
            {"_id": hid, "tenant_id": schedule.get("tenant_id", "default")},
            {
                "$set": {
                    "status": status,
                    "error_message": error_msg,
                    "delivery_details": {
                        "sent_count": sent_count,
                        "failed_count": len(failed_recipients),
                        "failed_recipients": failed_recipients,
                        "mock_count": len(mock_recipients),
                        "total_recipients": total,
                        "attachment_count": len(attachments),
                        "report_summary": payload.get("rows", [])[:8],
                    },
                }
            },
        )

        # KPI'yı sadece gerçekten gönderilen sayısı kadar artır.
        await db.report_schedules.update_one(
            {"_id": schedule["_id"], "tenant_id": schedule.get("tenant_id", "default")},
            {
                "$set": {
                    "last_sent_at": now.isoformat(),
                    "last_status": status,
                    "updated_at": now.isoformat(),
                },
                "$inc": {
                    "total_sent": sent_count,
                    "total_failed": len(failed_recipients),
                },
            },
        )

        return {
            "message": f"Rapor gönderimi tamamlandı ({status})",
            "status": status,
            "sent_count": sent_count,
            "failed_count": len(failed_recipients),
            "mock_count": len(mock_recipients),
            "history_id": hid,
        }

    except Exception as e:
        error_msg = f"Rapor gönderim hatası: {str(e)}"
        logger.error(f"Schedule execution failed: {e}\n{traceback.format_exc()}")

        await db.report_schedule_history.update_one(
            {"_id": hid, "tenant_id": schedule.get("tenant_id", "default")},
            {"$set": {"status": "failed", "error_message": error_msg}},
        )
        await db.report_schedules.update_one(
            {"_id": schedule["_id"], "tenant_id": schedule.get("tenant_id", "default")},
            {"$set": {"last_status": "failed", "updated_at": now.isoformat()}, "$inc": {"total_failed": 1}},
        )

        return {"message": error_msg, "status": "failed", "history_id": hid}


def _build_report_email_html(
    schedule: dict,
    report_label: str,
    now: datetime,
    payload: dict | None = None,
    app_url: str = "",
) -> str:
    # Bug AQ (April 2026): schedule.name ve schedule.notes kullanıcı tarafından
    # girilir; XSS önlemek için tüm dinamik alanlar HTML-escape edilir.
    # Sprint A DS (May 2026): mor gradient kaldırıldı → indigo (#4f46e5) düz renk.
    import html as _html_mod

    def _e(v):
        return _html_mod.escape("" if v is None else str(v), quote=True)

    fmt = _e(schedule.get("format", "pdf").upper())
    freq_labels = {"daily": "Günlük", "weekly": "Haftalık", "monthly": "Aylık"}
    freq_label = _e(freq_labels.get(schedule.get("frequency", ""), schedule.get("frequency", "")))
    sched_name = _e(schedule.get("name", "-"))
    sched_notes = _e(schedule.get("notes")) if schedule.get("notes") else None
    report_label = _e(report_label)
    safe_app_url = _e(app_url) if app_url else ""

    # Rapor özet tablosu (gerçek veri)
    summary_rows_html = ""
    notes_html = ""
    if payload:
        rows = payload.get("rows") or []
        if rows:
            summary_rows_html = "".join(f"<tr><td>{_e(r.get('label', ''))}</td><td>{_e(r.get('value', ''))}</td></tr>" for r in rows)
        if payload.get("notes"):
            notes_html = f'<p style="color:#92400e;background:#fef3c7;border:1px solid #fcd34d;padding:10px;border-radius:6px">{_e(payload["notes"])}</p>'

    summary_block = (
        f'<h3 style="margin-top:24px;color:#1e293b">Özet</h3><table class="meta-table">{summary_rows_html}</table>'
        if summary_rows_html
        else '<p style="color:#64748b"><em>Bu rapor için detay özet henüz hazır değil; lütfen ekteki dosyayı inceleyiniz.</em></p>'
    )

    cta_block = (
        f'<p style="text-align:center;"><a href="{safe_app_url}" class="button">Raporu Görüntüle</a></p>'
        if safe_app_url
        else '<p style="text-align:center;color:#64748b;font-size:12px"><em>Tam rapora ulaşmak için sisteminize giriş yapın.</em></p>'
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; background: #f8fafc; margin: 0; }}
            .container {{ max-width: 640px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #4f46e5; color: white; padding: 28px; text-align: center;
                      border-radius: 10px 10px 0 0; }}
            .header h1 {{ margin: 0 0 6px; font-size: 22px; }}
            .header p {{ margin: 0; opacity: 0.9; font-size: 14px; }}
            .content {{ background: #ffffff; padding: 28px; border-radius: 0 0 10px 10px;
                       border: 1px solid #e2e8f0; border-top: 0; }}
            .meta-table {{ width: 100%; border-collapse: collapse; margin: 14px 0; }}
            .meta-table td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
            .meta-table td:first-child {{ font-weight: 600; color: #475569; width: 50%; }}
            .button {{ background: #1e293b; color: white; padding: 12px 22px;
                      text-decoration: none; border-radius: 6px; display: inline-block; margin: 15px 0;
                      font-weight: 600; }}
            .footer {{ text-align: center; margin-top: 18px; color: #94a3b8; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{report_label}</h1>
                <p>{freq_label} otomatik rapor</p>
            </div>
            <div class="content">
                <p>Merhaba,</p>
                <p>Zamanlanmış raporunuz hazır. Kısa özet aşağıdadır; detay için ekteki <strong>{fmt}</strong> dosyasını inceleyebilirsiniz.</p>
                <table class="meta-table">
                    <tr><td>Rapor</td><td>{report_label}</td></tr>
                    <tr><td>Frekans</td><td>{freq_label}</td></tr>
                    <tr><td>Format</td><td>{fmt}</td></tr>
                    <tr><td>Oluşturulma</td><td>{now.strftime("%d.%m.%Y %H:%M")}</td></tr>
                    <tr><td>Zamanlama</td><td>{sched_name}</td></tr>
                </table>
                {summary_block}
                {notes_html}
                {cta_block}
                {f'<p style="color:#475569"><em>Not: {sched_notes}</em></p>' if sched_notes else ""}
            </div>
            <div class="footer">
                <p>Syroce Otel Yönetim Sistemi</p>
                <p>Bu otomatik bir e-postadır. Zamanlamayı değiştirmek için sisteme giriş yapınız.</p>
            </div>
        </div>
    </body>
    </html>
    """
