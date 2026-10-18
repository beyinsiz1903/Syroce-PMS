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
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit
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
    {"key": "revenue", "label": "Gelir Raporu", "description": "Dönem geliri, işlem sayısı, ADR ve RevPAR; para birimleri ayrı"},
    {"key": "occupancy", "label": "Doluluk Raporu", "description": "Gerçekleşen dolu ve satılabilir oda-gece, dönem doluluk oranı"},
    {"key": "reservations", "label": "Rezervasyon Raporu", "description": "Giriş dönemine göre rezervasyon durum istatistikleri"},
    {"key": "guest_analytics", "label": "Misafir Analitik", "description": "Dönemde eklenen misafirler ve anlık toplam kayıt sayısı"},
    {"key": "adr_revpar", "label": "ADR / RevPAR", "description": "Ortalama günlük fiyat ve oda başına gelir"},
    {"key": "channel_performance", "label": "Kanal Performansı", "description": "OTA ve satış kanalı bazlı analiz"},
    {"key": "b2b_analytics", "label": "B2B Analitik", "description": "Giriş dönemine göre acente rezervasyon sayıları ve durumları"},
    {"key": "housekeeping", "label": "Housekeeping Raporu", "description": "Aktif odaların anlık temizlik durumları; geçmiş dönem performansı değildir"},
    {"key": "financial", "label": "Finansal Satış Özeti", "description": "İşlenmiş satış/iade geliri; tahsilat veya genel muhasebe mizanı değildir"},
    {"key": "flash_report", "label": "Flash Report", "description": "Anlık operasyon durum raporu"},
]

FREQUENCY_OPTIONS = ["daily", "weekly", "monthly"]
FORMAT_OPTIONS = ["pdf", "csv", "link"]
DATE_RANGE_OPTIONS = ["auto", "business_day", "last_7_days", "month_to_date", "previous_month"]
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
    if "name" in data:
        data["name"] = data["name"].strip()
        if not 1 <= len(data["name"]) <= 200:
            raise HTTPException(status_code=400, detail="Zamanlama adı 1-200 karakter olmalıdır")
    if "report_type" in data and data["report_type"] not in [r["key"] for r in REPORT_TYPES]:
        raise HTTPException(status_code=400, detail=f"Geçersiz rapor tipi: {data['report_type']}")
    if "frequency" in data and data["frequency"] not in FREQUENCY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Geçersiz frekans: {data['frequency']}")
    if "format" in data and data["format"] not in FORMAT_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Geçersiz format: {data['format']}")
    if "date_range" in data and data["date_range"] not in DATE_RANGE_OPTIONS:
        raise HTTPException(status_code=400, detail="Geçersiz rapor dönemi")
    if "send_time" in data and not _TIME_RE.fullmatch(data["send_time"]):
        raise HTTPException(status_code=400, detail="Geçersiz saat formatı, HH:MM olmalıdır")
    if data.get("day_of_week") and data["day_of_week"] not in DAYS_OF_WEEK:
        raise HTTPException(status_code=400, detail=f"Geçersiz gün: {data['day_of_week']}")
    if data.get("day_of_month") is not None:
        if not (1 <= data["day_of_month"] <= 28):
            raise HTTPException(status_code=400, detail="Ayın günü 1-28 arası olmalıdır (kısa ayları kapsamak için)")
    if "recipients" in data:
        recipients = list(dict.fromkeys(email.strip() for email in data["recipients"]))
        if not 1 <= len(recipients) <= 100:
            raise HTTPException(status_code=400, detail="1-100 alıcı belirtilmelidir")
        for email in recipients:
            if not _EMAIL_RE.fullmatch(email):
                raise HTTPException(status_code=400, detail=f"Geçersiz e-posta: {email}")
        data["recipients"] = recipients
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
    return {"report_types": REPORT_TYPES, "frequencies": FREQUENCY_OPTIONS, "formats": FORMAT_OPTIONS, "days_of_week": DAYS_OF_WEEK, "date_ranges": DATE_RANGE_OPTIONS}


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
    schedules = await cursor.to_list(length=None)
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
    merged = {**schedule, **updates}
    _validate_schedule_fields(merged)
    updates = {key: merged[key] for key in updates}

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
    limit: int = Query(50, ge=1, le=200),
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

    cursor = db.report_schedule_history.find(query, {"report_payload": 0, "schedule_snapshot": 0}).sort("sent_at", -1).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"history": history, "total": await db.report_schedule_history.count_documents(query)}


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

    if entry.get("status") not in {"failed", "partial"}:
        raise HTTPException(status_code=400, detail="Sadece başarısız veya kısmi gönderimler tekrar denenebilir")
    if not entry.get("schedule_snapshot"):
        raise HTTPException(status_code=409, detail="Eski kayıtta rapor ve alıcı anlık görüntüsü yok. Teslimatı doğruladıktan sonra zamanlamadan yeni gönderim başlatın.")
    states = entry.get("delivery_states", [])
    if any(item.get("status") == "sending" for item in states):
        raise HTTPException(status_code=409, detail="Önceki gönderimin sonucu belirsiz. Mükerrer e-postayı önlemek için teslimatı doğrulayın; otomatik tekrar yapılmadı.")
    if not states and entry.get("delivery_details", {}).get("sent_count", 0):
        raise HTTPException(status_code=409, detail="Eski kayıtta alıcı bazında teslimat kanıtı yok. Mükerrer gönderimi önlemek için teslimatı doğrulayın.")

    schedule = await _get_schedule_for_tenant(entry["schedule_id"], current_user)

    claim = await db.report_schedule_history.update_one(
        {"_id": history_id, "tenant_id": _get_tenant_id(current_user), "status": entry["status"], "retry_count": entry.get("retry_count", 0)},
        {"$set": {"status": "retrying"}, "$inc": {"retry_count": 1}},
    )
    if not claim.modified_count:
        raise HTTPException(status_code=409, detail="Gönderim başka bir işlem tarafından tekrar deneniyor")

    result = await _execute_schedule(schedule, triggered_by=current_user.email, history_id=history_id)
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return result


def _report_period(schedule: dict, business_day: date) -> tuple[date, date]:
    """All periods end on the PMS business calendar, never the wall clock."""
    choice = schedule.get("date_range") or "auto"
    if choice == "auto":
        choice = {"weekly": "last_7_days", "monthly": "previous_month"}.get(schedule.get("frequency"), "business_day")
    if choice == "last_7_days":
        return business_day - timedelta(days=6), business_day
    if choice == "month_to_date":
        return business_day.replace(day=1), business_day
    if choice == "previous_month":
        last = business_day.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    if choice == "business_day":
        return business_day, business_day
    raise ValueError("Geçersiz rapor dönemi")


def _payload_range_label(payload: dict) -> str:
    first = payload.get("start_date") or payload.get("range") or ""
    last = payload.get("end_date") or first
    def display(value):
        try:
            return date.fromisoformat(str(value)).strftime("%d.%m.%Y")
        except ValueError:
            return str(value)
    return display(first) if first == last else f"{display(first)} – {display(last)}"


async def _build_report_payload(schedule: dict, now: datetime) -> dict:
    """Use shared ledger and room-night contracts for the explicit period."""
    from core.business_date_service import ensure_business_date_initialized
    from core.database import _raw_db as raw_db
    from modules.pms_core.report_money import add_amount, amounts_text
    from modules.pms_core.reporting_dates import date_period_match
    from modules.pms_core.stay_night_metrics import load_stay_night_metrics

    tenant_id = schedule.get("tenant_id") or "default"
    rtype = schedule.get("report_type", "")
    state = await ensure_business_date_initialized(raw_db, tenant_id)
    business_day = date.fromisoformat(str(state["business_date"])[:10])
    first, last = _report_period(schedule, business_day)
    booking_period = {"tenant_id": tenant_id, **date_period_match("check_in", first, last)}
    period = first.isoformat() if first == last else f"{first.isoformat()} – {last.isoformat()}"
    rows = []
    notes = None

    if rtype in ("daily_summary", "occupancy", "flash_report"):
        arrivals = await raw_db.bookings.count_documents({
            **booking_period, "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house", "checked_out", "arriving"]},
        })
        departures = await raw_db.bookings.count_documents({
            "tenant_id": tenant_id, **date_period_match("check_out", first, last),
            "status": {"$in": ["checked_in", "in_house", "checked_out", "departing"]},
        })
        metrics = await load_stay_night_metrics(raw_db, tenant_id, first, last, actual_only=True)
        occupied = sum(day["occupied_rooms"] for day in metrics)
        capacity = sum(day["total_rooms"] for day in metrics)
        rows = [
            {"label": "Rapor dönemi", "value": period},
            {"label": "Dönemde gelen (arrivals)", "value": arrivals},
            {"label": "Dönemde çıkan (departures)", "value": departures},
            {"label": "Dolu oda-gece", "value": occupied},
            {"label": "Satılabilir oda-gece", "value": capacity},
            {"label": "Doluluk %", "value": round(occupied / capacity * 100, 2) if capacity else 0},
        ]
        notes = "Gerçekleşen konaklamalar; çıkış günü oda-geceye dahil edilmez."
    elif rtype in ("revenue", "adr_revpar", "financial"):
        from modules.pms_core.reporting_ledger import charge_amount, charge_category, posted_revenue_rows

        charges = await posted_revenue_rows(tenant_id, first, last, database=raw_db)
        totals, room_totals = {}, {}
        for item in charges:
            add_amount(totals, item.get("currency"), charge_amount(item))
            if charge_category(item) == "room":
                add_amount(room_totals, item.get("currency"), charge_amount(item))
        metrics = await load_stay_night_metrics(raw_db, tenant_id, first, last, actual_only=True)
        sold_nights = sum(day.get("sold_rooms", day["occupied_rooms"]) for day in metrics)
        capacity = sum(day["total_rooms"] for day in metrics)
        effective_room_totals = room_totals
        notes = "İşlenmiş satış/iade geliri; tahsilat veya genel muhasebe mizanı değildir. Para birimleri ayrı gösterilir; kur dönüşümü yapılmaz. ADR, dönem toplam oda geliri / satılmış oda-gece; RevPAR, dönem toplam oda geliri / satılabilir oda-gecedir."
        if not room_totals:
            effective_room_totals = {}
            for day in metrics:
                for code, amount in day.get("revenue_by_currency", {}).items():
                    add_amount(effective_room_totals, code, amount)
            notes += " Oda geliri henüz işlenmediğinden ADR/RevPAR konaklama tahakkukuna dayanır."
        adr = {code: float(amount) / sold_nights if sold_nights else 0 for code, amount in effective_room_totals.items()}
        revpar = {code: float(amount) / capacity if capacity else 0 for code, amount in effective_room_totals.items()}
        rows = [
            {"label": "Rapor dönemi", "value": period},
            {"label": "Toplam gelir (para birimine göre)", "value": amounts_text(totals)},
            {"label": "Gelir işlem sayısı", "value": len(charges)},
            {"label": "ADR (Ortalama Günlük Fiyat)", "value": amounts_text(adr)},
            {"label": "RevPAR (Oda Başı Gelir)", "value": amounts_text(revpar)},
        ]
    elif rtype == "guest_analytics":
        new_guests = await raw_db.guests.count_documents({"tenant_id": tenant_id, **date_period_match("created_at", first, last)})
        total_guests = await raw_db.guests.count_documents({"tenant_id": tenant_id})
        rows = [
            {"label": "Dönemde eklenen misafir", "value": new_guests},
            {"label": "Toplam kayıtlı misafir (anlık)", "value": total_guests},
        ]
        notes = "Yeni misafir sayısı rapor dönemine; toplam kayıtlı misafir sayısı üretim anına aittir."
    elif rtype == "channel_performance":
        grouped = await raw_db.bookings.aggregate([
            {"$match": booking_period},
            {"$group": {"_id": "$channel", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
        ]).to_list(None)
        rows = [{"label": row["_id"] or "Direkt", "value": row["count"]} for row in grouped]
        notes = "Giriş tarihine göre tüm rezervasyonlar; iptaller dahil. Kanallar kırpılmaz."
    elif rtype in ("b2b_analytics", "reservations"):
        query = dict(booking_period)
        if rtype == "b2b_analytics":
            query["agency_id"] = {"$exists": True, "$nin": [None, ""]}
        grouped = await raw_db.bookings.aggregate([
            {"$match": query}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}},
        ]).to_list(None)
        rows = [{"label": "Giriş dönemindeki rezervasyon sayısı", "value": sum(row["count"] for row in grouped)}]
        rows += [{"label": f"Rezervasyon durumu — {row['_id'] or 'belirtilmemiş'}", "value": row["count"]} for row in grouped]
        notes = "Rezervasyon giriş tarihine göre durum istatistikleri; iptaller dahil."
    elif rtype == "housekeeping":
        for status in ("clean", "dirty", "inspected", "out_of_order"):
            count = await raw_db.rooms.count_documents({"tenant_id": tenant_id, "is_active": {"$ne": False}, "housekeeping_status": status})
            rows.append({"label": f"Oda durumu — {status}", "value": count})
        notes = "Anlık oda durumu; geçmiş dönem performansı değildir."
    else:
        raise ValueError(f"'{rtype}' için zamanlanmış rapor hazırlayıcı tanımlı değil")

    if rtype in ("daily_summary", "flash_report"):
        from modules.pms_core.reporting_ledger import charge_amount, posted_revenue_rows

        totals = {}
        for item in await posted_revenue_rows(tenant_id, first, last, database=raw_db):
            add_amount(totals, item.get("currency"), charge_amount(item))
        rows.append({"label": "Toplam gelir (para birimine göre)", "value": amounts_text(totals)})
        notes += " Gelir, işlenmiş satış ve iade kayıtlarından hesaplanır; tahsilat değildir. Para birimleri ayrı tutulur."

    return {
        "rows": rows, "generated_at": now.isoformat(), "range": period,
        "start_date": first.isoformat(), "end_date": last.isoformat(),
        "business_date": business_day.isoformat(), "notes": notes,
    }


def _payload_to_csv(report_label: str, payload: dict) -> bytes:
    import csv
    import io

    from core.csv_safe import safe_writerow

    buf = io.StringIO()
    w = csv.writer(buf)
    safe_writerow(w, [report_label])
    safe_writerow(w, ["Üretim:", payload.get("generated_at", "")])
    safe_writerow(w, ["Rapor dönemi:", _payload_range_label(payload)])
    safe_writerow(w, ["Başlangıç:", payload.get("start_date", ""), "Bitiş:", payload.get("end_date", "")])
    w.writerow([])
    w.writerow(["Metrik", "Değer"])
    for r in payload.get("rows", []):
        safe_writerow(w, [r.get("label", ""), r.get("value", "")])
    if payload.get("notes"):
        w.writerow([])
        safe_writerow(w, ["Not:", payload["notes"]])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _payload_to_pdf(report_label: str, payload: dict, html: str) -> bytes | None:
    try:
        from weasyprint import HTML  # type: ignore

        return HTML(string=html).write_pdf()
    except Exception as exc:
        logger.warning("[report-scheduler] PDF render failed: %s", exc)
        return None


def _resolve_app_url(history_id: str) -> str:
    base = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")
    try:
        parsed = urlsplit(base)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    return f"{base}/report-scheduler?history_id={history_id}"


async def _execute_schedule(schedule: dict, triggered_by: str = "system", history_id: str | None = None):
    now = datetime.now(UTC)
    hid = history_id or str(uuid.uuid4())
    tenant_id = schedule.get("tenant_id", "default")
    history_filter = {"_id": hid, "tenant_id": tenant_id}
    entry = await db.report_schedule_history.find_one(history_filter) if history_id else None
    # A retry must not adopt changed recipients, format, notes or reporting dates.
    schedule = dict((entry or {}).get("schedule_snapshot") or schedule)
    report_label = next((r["label"] for r in REPORT_TYPES if r["key"] == schedule["report_type"]), schedule["report_type"])
    fmt = schedule.get("format") or "pdf"
    states = (entry or {}).get("delivery_states") or [
        {"recipient": recipient, "status": "pending"}
        for recipient in dict.fromkeys(schedule.get("recipients") or [])
    ]
    if not history_id:
        await db.report_schedule_history.insert_one({
            "_id": hid, "tenant_id": tenant_id, "schedule_id": schedule["_id"],
            "schedule_name": schedule["name"], "report_type": schedule["report_type"],
            "report_label": report_label, "format": fmt, "recipients": schedule.get("recipients", []),
            "schedule_snapshot": schedule, "delivery_states": states,
            "triggered_by": triggered_by, "sent_at": now.isoformat(), "status": "processing",
            "error_message": None, "retry_count": 0, "delivery_details": {},
        })

    try:
        from modules.messaging.email_service import email_service

        _validate_schedule_fields(schedule)
        if not states:
            raise ValueError("Rapor gönderimi için en az bir alıcı gereklidir")
        if any(item["status"] == "sending" for item in states):
            raise ValueError("Önceki teslimat sonucu belirsiz; otomatik tekrar yapılmadı")
        payload = (entry or {}).get("report_payload")
        if payload is None:
            payload = await _build_report_payload(schedule, now)
        generated_at = datetime.fromisoformat(payload.get("generated_at") or now.isoformat())
        report_date = payload.get("start_date") or str(payload.get("range") or now.date().isoformat())[:10]
        app_url = _resolve_app_url(hid)
        if fmt == "link" and not app_url:
            raise ValueError("Bağlantılı rapor için PUBLIC_APP_URL geçerli bir HTTPS adresi olmalıdır")
        await db.report_schedule_history.update_one(history_filter, {"$set": {
            "report_payload": payload, "schedule_snapshot": schedule, "delivery_states": states,
            "report_range": _payload_range_label(payload), "last_attempt_at": now.isoformat(),
        }})

        subject = f"Syroce Rapor: {report_label} — {_payload_range_label(payload)}"
        html_content = _build_report_email_html(schedule, report_label, generated_at, payload, app_url)
        text_lines = [report_label, f"Rapor dönemi: {_payload_range_label(payload)}",
                      f"Üretim: {payload.get('generated_at') or now.isoformat()}", f"Format: {fmt.upper()}", "", "Özet:"]
        text_lines += [f"  • {row.get('label')}: {row.get('value')}" for row in payload.get("rows", [])]
        if payload.get("notes"):
            text_lines += ["", f"Not: {payload['notes']}"]
        if fmt == "link":
            text_lines += ["", f"Raporu görüntüle: {app_url}"]
        text_content = "\n".join(text_lines)
        date_tag = report_date.replace("-", "")
        attachments = []
        if fmt == "csv":
            attachments.append((f"{schedule['report_type']}_{date_tag}.csv", "text/csv", _payload_to_csv(report_label, payload)))
        elif fmt == "pdf":
            pdf_bytes = _payload_to_pdf(report_label, payload, html_content)
            if not pdf_bytes:
                raise ValueError("PDF üretilemedi; farklı formatta dosya gönderilmedi. Tekrar deneyin veya CSV seçin.")
            attachments.append((f"{schedule['report_type']}_{date_tag}.pdf", "application/pdf", pdf_bytes))

        sent_this_attempt = failed_this_attempt = 0
        smtp_ready = email_service.mode == "production" and email_service.smtp_username and email_service.smtp_password
        for item in states:
            if item["status"] in {"sent", "mock"}:
                continue
            # Persist intent before the external side effect. A process crash here
            # leaves an explicit uncertain delivery, never a blind duplicate retry.
            item["status"] = "sending"
            await db.report_schedule_history.update_one(history_filter, {"$set": {"delivery_states": states}})
            if smtp_ready:
                try:
                    success = await asyncio.to_thread(email_service._send_email_smtp, item["recipient"], subject, html_content, text_content, attachments)
                except Exception:
                    logger.exception("Report delivery failed")
                    success = False
                item["status"] = "sent" if success else "failed"
                sent_this_attempt += int(bool(success))
                failed_this_attempt += int(not success)
            else:
                item["status"] = "mock"
            await db.report_schedule_history.update_one(history_filter, {"$set": {"delivery_states": states}})

        sent_count = sum(item["status"] == "sent" for item in states)
        failed = [item["recipient"] for item in states if item["status"] == "failed"]
        mock_count = sum(item["status"] == "mock" for item in states)
        status = "partial" if failed and sent_count else "failed" if failed else "mock" if mock_count else "sent"
        error_msg = f"Gönderilemeyen alıcılar: {', '.join(failed)}" if failed else (
            "SMTP yapılandırılmadığı için gerçek e-posta gönderilmedi (mock mode)." if mock_count else None)
        details = {
            "sent_count": sent_count, "failed_count": len(failed), "failed_recipients": failed,
            "mock_count": mock_count, "total_recipients": len(states), "attachment_count": len(attachments),
            "report_summary": payload.get("rows", []),
        }
        await db.report_schedule_history.update_one(history_filter, {"$set": {
            "status": status, "error_message": error_msg, "delivery_details": details, "delivery_states": states,
        }})
        schedule_updates = {"last_status": status, "updated_at": now.isoformat()}
        if sent_this_attempt:
            schedule_updates["last_sent_at"] = now.isoformat()
        await db.report_schedules.update_one(
            {"_id": schedule["_id"], "tenant_id": tenant_id},
            {"$set": schedule_updates, "$inc": {"total_sent": sent_this_attempt, "total_failed": failed_this_attempt}},
        )
        _invalidate_scheduler_cache(tenant_id)
        return {
            "message": f"Rapor gönderimi tamamlandı ({status})", "status": status,
            "sent_count": sent_count, "failed_count": len(failed), "mock_count": mock_count, "history_id": hid,
        }
    except Exception as exc:
        error_msg = f"Rapor gönderim hatası: {exc}"
        logger.error("Schedule execution failed: %s\n%s", exc, traceback.format_exc())
        await db.report_schedule_history.update_one(history_filter, {"$set": {"status": "failed", "error_message": error_msg}})
        await db.report_schedules.update_one(
            {"_id": schedule["_id"], "tenant_id": tenant_id},
            {"$set": {"last_status": "failed", "updated_at": now.isoformat()}, "$inc": {"total_failed": 1}},
        )
        _invalidate_scheduler_cache(tenant_id)
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
    period_label = _e(_payload_range_label(payload or {}))
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
                <p>Zamanlanmış raporunuz hazır. {"Aşağıdaki bağlantıdan yetkili hesabınızla raporu görüntüleyebilirsiniz." if schedule.get("format") == "link" else f'Özet aşağıdadır; ekteki <strong>{fmt}</strong> dosyasını inceleyebilirsiniz.'}</p>
                <table class="meta-table">
                    <tr><td>Rapor</td><td>{report_label}</td></tr>
                    <tr><td>Frekans</td><td>{freq_label}</td></tr>
                    <tr><td>Format</td><td>{fmt}</td></tr>
                    <tr><td>Rapor dönemi</td><td>{period_label}</td></tr>
                    <tr><td>Oluşturulma (UTC)</td><td>{now.strftime("%d.%m.%Y %H:%M")}</td></tr>
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
