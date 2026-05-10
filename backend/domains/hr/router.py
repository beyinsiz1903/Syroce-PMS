"""
Domain Router: HR Operations

HR complete suite, F&B complete suite for department managers.

Türk İş Kanunu uyumlu defaultlar (2026):
  - Aylık standart saat: 195 (45 sa/hf × 4.33)
  - Saatlik brüt asgari taban: 140 TL (yaklaşık 2026 asgari ücret)
  - Fazla mesai zammı: %50 (overtime_rate = hourly_rate * 1.5)
  - Para birimi: TRY
"""
import base64
import io
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pydantic import BaseModel, Field, field_validator

from core.database import _raw_db, db
from core.security import get_current_user

# GridFS bucket — personel belgeleri için (5MB üstü destek + memory verimi).
# Eski kayıtlar `data_b64` alanı üzerinden okunmaya devam eder (geriye uyum).
_hr_docs_bucket = AsyncIOMotorGridFSBucket(_raw_db, bucket_name='staff_docs')
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v96 DW

router = APIRouter(prefix="/api", tags=["hr-operations"])

# ============= TR Labor Defaults =============
TR_DEFAULT_HOURLY_RATE = 140.0   # 2026 asgari ücret yaklaşık saatlik brüt
TR_DEFAULT_MONTHLY_HOURS = 195   # 45 sa/hafta × 4.33 hafta
TR_DEFAULT_OVERTIME_MULTIPLIER = 1.5  # %50 zam (İş K. m.41)
TR_CURRENCY = "TRY"

# Türkiye saat dilimi (UTC+3, sabit — yaz saati uygulaması yok)
TR_TZ = timezone(timedelta(hours=3))


def _today_local() -> date:
    """Türkiye TZ'ne göre bugünün tarihi — UTC vs local skew'unu engeller."""
    return datetime.now(TR_TZ).date()


# ============= HR COMPLETE SUITE =============

async def _get_staff_map(tenant_id: str):
    staff = await db.staff_members.find({'tenant_id': tenant_id}, {'_id': 0}).to_list(500)
    return {member['id']: member for member in staff}


async def _verify_staff_in_tenant(staff_id: str, tenant_id: str) -> dict | None:
    """
    Bug DAK round-7: Cross-tenant clock-in açığı.
    staff_id'nin gerçekten bu tenant'a ait olduğunu doğrular.
    staff_members'da bulunamazsa users tablosundan (derived staff) kontrol eder.
    """
    if not staff_id:
        return None
    sm = await db.staff_members.find_one(
        {'id': staff_id, 'tenant_id': tenant_id},
        {'_id': 0}
    )
    if sm:
        return sm
    # users tablosundan türetilmiş staff (HRv2 — derived_from=users)
    user = await db.users.find_one(
        {'id': staff_id, 'tenant_id': tenant_id, 'is_active': True},
        {'_id': 0, 'id': 1, 'name': 1, 'role': 1, 'email': 1}
    )
    if user:
        return {
            'id': user['id'],
            'tenant_id': tenant_id,
            'name': user.get('name') or 'Personel',
            'department': user.get('role') or 'staff',
            'derived_from': 'users',
        }
    return None


# ============= Pydantic Models =============

class ClockInRequest(BaseModel):
    staff_id: str = Field(..., min_length=1, max_length=128)


class LeaveRequestPayload(BaseModel):
    staff_id: str = Field(..., min_length=1, max_length=128)
    staff_name: str | None = Field(None, max_length=200)
    leave_type: Literal['annual', 'sick', 'maternity', 'paternity', 'unpaid', 'bereavement', 'excused'] = 'annual'
    start_date: str = Field(..., description="ISO date YYYY-MM-DD")
    end_date: str = Field(..., description="ISO date YYYY-MM-DD")
    reason: str | None = Field(None, max_length=500)
    total_days: int | None = Field(None, ge=0, le=365)

    @field_validator('start_date', 'end_date')
    @classmethod
    def _valid_iso(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v).date()
        except Exception as exc:
            raise ValueError("Geçersiz tarih formatı (YYYY-MM-DD)") from exc
        return v


class LeaveDecision(BaseModel):
    decision: Literal['approve', 'reject']
    note: str | None = Field(None, max_length=500)


class PayrollFinalizePayload(BaseModel):
    month: str = Field(..., pattern=r'^\d{4}-\d{2}$')


class PerformanceReviewPayload(BaseModel):
    staff_id: str = Field(..., min_length=1, max_length=128)
    reviewer_name: str | None = Field(None, max_length=200)
    period: str | None = Field(None, max_length=64)
    overall_score: float = Field(..., ge=0, le=10)
    goals: str | None = Field(None, max_length=2000)
    strengths: str | None = Field(None, max_length=2000)
    improvement_areas: str | None = Field(None, max_length=2000)
    template_id: str | None = Field(None, max_length=128)
    competency_scores: dict[str, float] | None = None  # {"Müşteri ilişkileri": 8.5, ...}


class JobPostingPayload(BaseModel):
    """Personel ihtiyaç talebi / iş ilanı formu.

    Bu model iki amaca hizmet eder:
    - `request_type='internal_request'` (varsayılan): Departman müdürü
      personel ihtiyacı bildirir, HR yöneticisi onaylayınca aday alımına açılır.
    - `request_type='public_posting'`: Direkt kabul edilmiş açık pozisyon
      (legacy davranış; ileride dış kanal entegrasyonu eklenirse kullanılır).
    """
    title: str = Field(..., min_length=1, max_length=200)
    department: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=5000)
    employment_type: Literal['full_time', 'part_time', 'seasonal', 'intern', 'contract'] = 'full_time'
    location: str | None = Field(None, max_length=200)
    salary_range: str | None = Field(None, max_length=100)
    # Personel talebi alanları
    request_type: Literal['internal_request', 'public_posting'] = 'internal_request'
    headcount_needed: int = Field(1, ge=1, le=50)
    urgency: Literal['low', 'normal', 'high', 'critical'] = 'normal'
    justification: str | None = Field(None, max_length=2000)
    needed_by: str | None = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')


class JobDecisionPayload(BaseModel):
    note: str | None = Field(None, max_length=500)


# ============= Attendance =============

@router.post("/hr/clock-in")
async def clock_in(payload: ClockInRequest, current_user: User = Depends(get_current_user)):
    """Personel giriş kaydı — tenant scoped, TR-TZ tarih, validated staff_id."""
    staff = await _verify_staff_in_tenant(payload.staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı veya bu tenant'a ait değil")

    today_iso = _today_local().isoformat()
    # Aynı gün içinde açık clock-in varsa, çift kayıt önle
    existing = await db.attendance_records.find_one({
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'date': today_iso,
        'clock_out': None,
    })
    if existing:
        return {'success': False, 'message': 'Açık giriş kaydı mevcut', 'time': existing.get('clock_in')}

    record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'staff_name': staff.get('name'),
        'date': today_iso,
        'clock_in': datetime.now(UTC).isoformat(),
        'clock_out': None,
        'status': 'present',
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.attendance_records.insert_one(record)
    return {'success': True, 'message': 'Giriş kaydedildi', 'time': record['clock_in']}


@router.post("/hr/clock-out")
async def clock_out(payload: ClockInRequest, current_user: User = Depends(get_current_user)):
    # v109 Bug DAK round-6 (T08 P1): tenant_id scoped on both find and update.
    today_iso = _today_local().isoformat()
    record = await db.attendance_records.find_one({
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'date': today_iso,
        'clock_out': None,
    })
    if record:
        clock_out_time = datetime.now(UTC)
        clock_in_time = datetime.fromisoformat(record['clock_in'].replace('Z', '+00:00'))
        hours = (clock_out_time - clock_in_time).total_seconds() / 3600
        await db.attendance_records.update_one(
            {'id': record['id'], 'tenant_id': current_user.tenant_id},
            {'$set': {'clock_out': clock_out_time.isoformat(), 'total_hours': round(hours, 2)}}
        )
        return {'success': True, 'hours_worked': round(hours, 2)}
    return {'success': False, 'message': 'Açık giriş kaydı bulunamadı'}


def _parse_date_range(start: str | None, end: str | None, days: int = 7):
    today = _today_local()
    start_date = datetime.fromisoformat(start).date() if start else today - timedelta(days=days)
    end_date = datetime.fromisoformat(end).date() if end else today
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


@router.get("/hr/attendance/records")
async def get_attendance_records(
    start_date: str | None = None,
    end_date: str | None = None,
    staff_id: str | None = None,
    limit: int = 500,
    current_user: User = Depends(get_current_user)
):
    start_dt, end_dt = _parse_date_range(start_date, end_date, days=7)
    query: dict[str, Any] = {
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()}
    }
    if staff_id:
        query['staff_id'] = staff_id
    records = await db.attendance_records.find(query, {'_id': 0}).sort('clock_in', -1).limit(limit).to_list(limit)
    staff_map = await _get_staff_map(current_user.tenant_id)
    for record in records:
        staff = staff_map.get(record['staff_id'])
        if staff:
            record['staff_name'] = staff.get('name') or record.get('staff_name')
            record['department'] = staff.get('department')
            record['position'] = staff.get('position')
    return {
        'records': records,
        'total': len(records),
        'range': {'start': start_dt.isoformat(), 'end': end_dt.isoformat()}
    }


@router.get("/hr/attendance/summary")
async def get_attendance_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    start_dt, end_dt = _parse_date_range(start_date, end_date, days=30)
    query = {
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()}
    }
    records = await db.attendance_records.find(query, {'_id': 0}).to_list(2000)
    staff_map = await _get_staff_map(current_user.tenant_id)

    summary: dict[str, Any] = {}
    for record in records:
        staff_id = record['staff_id']
        summary.setdefault(staff_id, {
            'staff_id': staff_id,
            'total_hours': 0,
            'days_present': 0,
            'overtime_hours': 0,
            'late_count': 0
        })
        summary[staff_id]['total_hours'] += record.get('total_hours', 0)
        summary[staff_id]['days_present'] += 1

    for staff_id, data in summary.items():
        staff = staff_map.get(staff_id, {})
        data['staff_name'] = staff.get('name', staff_id)
        data['department'] = staff.get('department', 'unknown')
        data['position'] = staff.get('position', 'Staff')
        overtime_threshold = staff.get('monthly_hours', TR_DEFAULT_MONTHLY_HOURS)
        if data['total_hours'] > overtime_threshold:
            data['overtime_hours'] = round(data['total_hours'] - overtime_threshold, 2)
        data['average_daily_hours'] = round(
            data['total_hours'] / data['days_present'], 2
        ) if data['days_present'] else 0

    summary_list = sorted(summary.values(), key=lambda x: x['staff_name'])
    total_hours = round(sum(item['total_hours'] for item in summary_list), 2)

    # Aktif personel sayısı: hem staff_members'da olanlar hem users
    # tablosundan türeyenler (HRv2 derived staff). `_get_staff_map` yalnızca
    # staff_members'ı döndürdüğü için users tarafını ayrıca sayıyoruz.
    explicit_count = await db.staff_members.count_documents(
        {'tenant_id': current_user.tenant_id, 'active': True}
    )
    derived_roles = ['housekeeping', 'front_desk', 'supervisor',
                     'finance', 'sales', 'admin']
    derived_count = await db.users.count_documents({
        'tenant_id': current_user.tenant_id,
        'is_active': True,
        'role': {'$in': derived_roles},
    })
    total_active_staff = explicit_count + derived_count

    # Devam kayıtlı personel başına ortalamayı koru, bilgi amaçlı
    # genel ortalamayı (gerçek headcount'a göre) ayrı alanla sunalım.
    avg_hours = round(total_hours / len(summary_list), 2) if summary_list else 0
    avg_hours_per_active_staff = (
        round(total_hours / total_active_staff, 2) if total_active_staff else 0
    )

    return {
        'summary': summary_list,
        'range': {'start': start_dt.isoformat(), 'end': end_dt.isoformat()},
        'metrics': {
            'staff_count': len(summary_list),
            'total_active_staff': total_active_staff,
            'total_hours': total_hours,
            'avg_hours_per_staff': avg_hours,
            'avg_hours_per_active_staff': avg_hours_per_active_staff,
        }
    }


# ============= Leave =============

@router.post("/hr/leave-request")
async def create_leave_request(
    payload: LeaveRequestPayload,
    current_user: User = Depends(get_current_user),
):
    """
    İzin talebi oluştur. Bug DAK round-7: Önceden permission gate yoktu ve
    Pydantic doğrulaması yapılmıyordu — kullanıcı başkası adına talep yaratabiliyordu.
    Şimdi: staff_id mutlaka aynı tenant'ta olmalı; HR yönetici yetkisi yoksa
    kullanıcı SADECE kendi user.id'sine eşleşen staff_id ile talep oluşturabilir.
    """
    staff = await _verify_staff_in_tenant(payload.staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı veya bu tenant'a ait değil")

    # Self-leave kontrolü: HR yönetici izni olmayan kullanıcı sadece kendi adına talep edebilir
    is_self = (payload.staff_id == getattr(current_user, 'id', None))
    if not is_self:
        # HR yönetici yetkisi gereken roller: admin/supervisor/finance
        manager_roles = {'admin', 'supervisor', 'finance'}
        if (getattr(current_user, 'role', None) or '').lower() not in manager_roles:
            raise HTTPException(
                status_code=403,
                detail="Başka personel adına izin talebi oluşturma yetkiniz yok"
            )

    start = datetime.fromisoformat(payload.start_date).date()
    end = datetime.fromisoformat(payload.end_date).date()
    if end < start:
        raise HTTPException(status_code=400, detail="Bitiş tarihi başlangıçtan önce olamaz")
    total_days = payload.total_days if payload.total_days is not None else (end - start).days + 1

    leave = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'staff_name': payload.staff_name or staff.get('name') or 'Personel',
        'leave_type': payload.leave_type,
        'start_date': payload.start_date,
        'end_date': payload.end_date,
        'total_days': total_days,
        'reason': payload.reason,
        'status': 'pending',
        'requested_by': getattr(current_user, 'id', None),
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.leave_requests.insert_one(leave)

    # HR yöneticilerine bildirim — onay bekleyen talep
    await _notify_hr_managers(
        current_user.tenant_id,
        kind='leave_request',
        title='Yeni izin talebi',
        body=(
            f"{leave['staff_name']} • {payload.leave_type} • "
            f"{payload.start_date} → {payload.end_date} ({total_days} gün)"
        ),
        link=f'/hr?tab=leave&id={leave["id"]}',
        ref_id=leave['id'],
    )

    return {'success': True, 'leave_id': leave['id'], 'total_days': total_days, 'status': 'pending'}


@router.get("/hr/leave-requests")
async def list_leave_requests(
    status: str | None = None,
    staff_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query: dict[str, Any] = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    if staff_id:
        query['staff_id'] = staff_id
    items = await db.leave_requests.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    counts = {'pending': 0, 'approved': 0, 'rejected': 0}
    for item in items:
        counts[item.get('status', 'pending')] = counts.get(item.get('status', 'pending'), 0) + 1
    return {'items': items, 'total': len(items), 'counts': counts}


@router.post("/hr/leave-request/{leave_id}/decision")
async def decide_leave_request(
    leave_id: str,
    payload: LeaveDecision,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # HR yönetici yetkisi
):
    leave = await db.leave_requests.find_one({
        'tenant_id': current_user.tenant_id, 'id': leave_id
    })
    if not leave:
        raise HTTPException(status_code=404, detail="İzin talebi bulunamadı")
    new_status = 'approved' if payload.decision == 'approve' else 'rejected'
    await db.leave_requests.update_one(
        {'tenant_id': current_user.tenant_id, 'id': leave_id},
        {'$set': {
            'status': new_status,
            'decision_note': payload.note,
            'decided_by': getattr(current_user, 'id', None),
            'decided_at': datetime.now(UTC).isoformat(),
        }}
    )
    # Talep sahibine bildirim — kararı duyur
    requester_id = leave.get('requested_by') or leave.get('staff_id')
    if requester_id:
        await _notify_user(
            current_user.tenant_id,
            user_id=requester_id,
            kind=f'leave_{new_status}',
            title=('İzin talebiniz onaylandı' if new_status == 'approved'
                   else 'İzin talebiniz reddedildi'),
            body=(
                f"{leave.get('start_date')} → {leave.get('end_date')} • "
                f"{leave.get('total_days', 0)} gün"
                + (f" • Not: {payload.note}" if payload.note else '')
            ),
            link=f'/hr?tab=leave&id={leave_id}',
            ref_id=leave_id,
        )
    return {'success': True, 'status': new_status}


# ============= Notification helpers (HR akışı için) =============

def _build_notification_doc(
    tenant_id: str, *, user_id: str | None, kind: str, title: str, body: str,
    link: str | None, ref_id: str | None,
) -> dict:
    """notifications koleksiyon şemasıyla uyumlu doc üretir.

    notification_router.list_notifications {type, title, message, action_url}
    alanlarını okur — bu helper bu adlandırmayı kullanır; ek olarak
    'kind' ve 'ref_id' metadata içine konur (debugging / future filtering için).
    """
    now_iso = datetime.now(UTC).isoformat()
    return {
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        'user_id': user_id,
        'type': kind,                # list endpoint 'type' okuyor
        'title': title,
        'message': body,             # list endpoint 'message' okuyor
        'body': body,                # backward-compat (bazı yerler 'body' kullanıyor)
        'priority': 'normal',
        'action_url': link,          # list endpoint 'action_url' okuyor
        'metadata': {'kind': kind, 'ref_id': ref_id} if ref_id else {'kind': kind},
        'read': False,
        'created_at': now_iso,
        'sent_at': now_iso,
    }


async def _notify_hr_managers(
    tenant_id: str, *, kind: str, title: str, body: str,
    link: str | None = None, ref_id: str | None = None,
):
    """HR yönetici rollerindeki tüm aktif kullanıcılara in-app bildirim gönder."""
    cursor = db.users.find({
        'tenant_id': tenant_id,
        'is_active': True,
        'role': {'$in': ['admin', 'supervisor', 'finance']},
    }, {'_id': 0, 'id': 1})
    user_ids = [u['id'] async for u in cursor if u.get('id')]
    if not user_ids:
        return
    docs = [
        _build_notification_doc(
            tenant_id, user_id=uid, kind=kind, title=title, body=body,
            link=link, ref_id=ref_id,
        )
        for uid in user_ids
    ]
    try:
        await db.notifications.insert_many(docs)
    except Exception as exc:  # pragma: no cover
        logger.warning("HR bildirimi yazılamadı: %s", exc)


async def _notify_user(
    tenant_id: str, *, user_id: str, kind: str, title: str, body: str,
    link: str | None = None, ref_id: str | None = None,
):
    """Tek kullanıcıya in-app bildirim gönder."""
    try:
        await db.notifications.insert_one(_build_notification_doc(
            tenant_id, user_id=user_id, kind=kind, title=title, body=body,
            link=link, ref_id=ref_id,
        ))
    except Exception as exc:  # pragma: no cover
        logger.warning("HR bildirimi yazılamadı: %s", exc)


# ============= Payroll =============

# NOTE: The dynamic `GET /hr/payroll/{month}` is intentionally declared
# AFTER the static export/finalize routes so FastAPI matches static first.

def _compute_payroll_for_month(
    records: list[dict],
    staff_map: dict[str, dict],
    month: str,
) -> list[dict]:
    payroll_rows: dict[str, float] = {}
    for record in records:
        staff_id = record['staff_id']
        payroll_rows.setdefault(staff_id, 0.0)
        payroll_rows[staff_id] += record.get('total_hours', 0)

    payroll: list[dict] = []
    for staff_id, total_hours in payroll_rows.items():
        staff = staff_map.get(staff_id, {})
        hourly_rate = float(staff.get('hourly_rate') or TR_DEFAULT_HOURLY_RATE)
        monthly_hours = float(staff.get('monthly_hours') or TR_DEFAULT_MONTHLY_HOURS)
        overtime_rate = float(staff.get('overtime_rate') or hourly_rate * TR_DEFAULT_OVERTIME_MULTIPLIER)
        overtime_hours = max(0.0, total_hours - monthly_hours)
        base_hours = total_hours - overtime_hours
        gross_pay = (base_hours * hourly_rate) + (overtime_hours * overtime_rate)

        # Basitleştirilmiş TR kesinti modeli (yaklaşık):
        # SGK işçi payı %14, işsizlik %1, gelir vergisi %15 (matrah - SGK), damga %0.759
        sgk_employee = round(gross_pay * 0.14, 2)
        unemployment = round(gross_pay * 0.01, 2)
        income_tax_base = max(0.0, gross_pay - sgk_employee - unemployment)
        income_tax = round(income_tax_base * 0.15, 2)
        stamp_tax = round(gross_pay * 0.00759, 2)
        total_deductions = round(sgk_employee + unemployment + income_tax + stamp_tax, 2)
        net_pay = round(gross_pay - total_deductions, 2)

        payroll.append({
            'staff_id': staff_id,
            'staff_name': staff.get('name', staff_id),
            'department': staff.get('department', 'unknown'),
            'period_month': month,
            'total_hours': round(total_hours, 2),
            'overtime_hours': round(overtime_hours, 2),
            'hourly_rate': round(hourly_rate, 2),
            'overtime_rate': round(overtime_rate, 2),
            'gross_pay': round(gross_pay, 2),
            'sgk_employee': sgk_employee,
            'unemployment': unemployment,
            'income_tax': income_tax,
            'stamp_tax': stamp_tax,
            'total_deductions': total_deductions,
            'net_salary': net_pay,
            'currency': TR_CURRENCY,
        })
    return payroll


async def _build_payroll(month: str | None, tenant_id: str):
    today = _today_local()
    if month:
        start_dt = datetime.fromisoformat(f"{month}-01").date()
    else:
        start_dt = date(today.year, today.month, 1)
    next_month = start_dt.replace(day=28) + timedelta(days=4)
    end_dt = next_month - timedelta(days=next_month.day)

    query = {
        'tenant_id': tenant_id,
        'date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()}
    }
    records = await db.attendance_records.find(query, {'_id': 0}).to_list(5000)
    staff_map = await _get_staff_map(tenant_id)
    period_month = start_dt.strftime('%Y-%m')
    payroll = _compute_payroll_for_month(records, staff_map, period_month)
    return period_month, payroll


@router.get("/hr/payroll/export")
async def export_payroll(
    month: str | None = None,
    format: str = 'json',
    current_user: User = Depends(get_current_user),
    # Bug DAK round-7: Maaş PII'sı için yetki gate'i (KVKK + iş hukuku).
    _perm=Depends(require_op("view_executive_reports")),
):
    period_month, payroll = await _build_payroll(month, current_user.tenant_id)

    response: dict[str, Any] = {
        'month': period_month,
        'payroll': payroll,
        'staff_count': len(payroll),
        'total_gross_pay': round(sum(row['gross_pay'] for row in payroll), 2),
        'total_net_pay': round(sum(row['net_salary'] for row in payroll), 2),
        'currency': TR_CURRENCY,
    }

    # NOT: format=csv için inline base64 desteği kaldırıldı. UI artık
    # /hr/payroll/export/csv (StreamingResponse) endpoint'ini kullanıyor —
    # data: URL'in 2MB tarayıcı limitini aşan büyük tenant'larda doğru çözüm.
    return response


@router.get("/hr/payroll/export/csv")
async def export_payroll_csv_stream(
    month: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Streaming CSV download — büyük dosyalar için data: URL limiti yok."""
    period_month, payroll = await _build_payroll(month, current_user.tenant_id)

    import csv

    from core.csv_safe import safe_dict_writerow
    buf = io.StringIO()
    fields = [
        'staff_id', 'staff_name', 'department', 'period_month',
        'total_hours', 'overtime_hours', 'hourly_rate', 'overtime_rate',
        'gross_pay', 'sgk_employee', 'unemployment', 'income_tax',
        'stamp_tax', 'total_deductions', 'net_salary', 'currency'
    ]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in payroll:
        safe_dict_writerow(writer, row)
    csv_text = buf.getvalue()

    return StreamingResponse(
        iter([csv_text]),
        media_type='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="payroll_{period_month}.csv"'
        }
    )


@router.post("/hr/payroll/finalize")
async def finalize_payroll(
    payload: PayrollFinalizePayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """
    Bordroyu hesapla ve payroll_records koleksiyonuna kalıcı olarak yaz.
    Önceden bu koleksiyona insert YOKTU — GET /hr/payroll/{month} her zaman
    boş dönüyordu (3-katmanlı dead code).
    """
    period_month, payroll = await _build_payroll(payload.month, current_user.tenant_id)
    if not payroll:
        return {'success': False, 'message': 'Bu ay için attendance kaydı yok', 'count': 0}

    # Önce eski kayıtları sil (idempotent finalize), sonra yeni satırları ekle
    await db.payroll_records.delete_many({
        'tenant_id': current_user.tenant_id,
        'period_month': period_month,
    })
    for row in payroll:
        row['id'] = str(uuid.uuid4())
        row['tenant_id'] = current_user.tenant_id
        row['finalized_by'] = getattr(current_user, 'id', None)
        row['finalized_at'] = datetime.now(UTC).isoformat()
    await db.payroll_records.insert_many(payroll)
    return {
        'success': True,
        'period_month': period_month,
        'count': len(payroll),
        'total_gross': round(sum(r['gross_pay'] for r in payroll), 2),
        'total_net': round(sum(r['net_salary'] for r in payroll), 2),
        'currency': TR_CURRENCY,
    }


@router.get("/hr/payroll/{month}")
async def get_payroll(
    month: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Per-month payroll lookup — finalize edilmiş kayıtları okur."""
    payroll = await db.payroll_records.find(
        {'tenant_id': current_user.tenant_id, 'period_month': month},
        {'_id': 0}
    ).to_list(500)
    total_gross = round(sum(p.get('gross_pay', 0) for p in payroll), 2)
    total_net = round(sum(p.get('net_salary', 0) for p in payroll), 2)
    return {
        'payroll': payroll,
        'period_month': month,
        'count': len(payroll),
        'total_gross': total_gross,
        'total_net': total_net,
        'currency': TR_CURRENCY,
    }


# ============= Performance =============

@router.post("/hr/performance")
async def create_performance_review(
    payload: PerformanceReviewPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    staff = await _verify_staff_in_tenant(payload.staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    review = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'staff_name': staff.get('name'),
        'reviewer_id': getattr(current_user, 'id', None),
        'reviewer_name': payload.reviewer_name,
        'period': payload.period,
        'overall_score': payload.overall_score,
        'goals': payload.goals,
        'strengths': payload.strengths,
        'improvement_areas': payload.improvement_areas,
        'template_id': payload.template_id,
        'competency_scores': payload.competency_scores or {},
        'reviewed_at': datetime.now(UTC).isoformat(),
    }
    await db.performance_reviews.insert_one(review)
    return {'success': True, 'review_id': review['id']}


@router.get("/hr/performance")
async def list_performance_reviews(
    staff_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query: dict[str, Any] = {'tenant_id': current_user.tenant_id}
    if staff_id:
        query['staff_id'] = staff_id
    items = await db.performance_reviews.find(query, {'_id': 0}).sort('reviewed_at', -1).to_list(500)
    avg = round(sum(i.get('overall_score', 0) for i in items) / len(items), 2) if items else 0
    return {'items': items, 'total': len(items), 'avg_score': avg}


# ============= Recruitment =============

@router.post("/hr/job-posting")
async def create_job_posting(
    payload: JobPostingPayload,
    current_user: User = Depends(get_current_user),
):
    """Personel ihtiyaç talebi oluştur (her departman müdürü açabilir).

    - internal_request → status=pending_approval, HR yöneticisine bildirim gider.
    - public_posting → yalnızca HR yetkisi ile, doğrudan status=active.
    """
    # public_posting için ek yetki gerekir; internal_request herkese açık
    if payload.request_type == 'public_posting':
        role = (getattr(current_user, 'role', None) or '').lower()
        if role not in {'admin', 'supervisor', 'finance'}:
            raise HTTPException(
                status_code=403,
                detail="Doğrudan ilan yayınlamak için HR yöneticisi yetkisi gerekir"
            )
        initial_status = 'active'
    else:
        initial_status = 'pending_approval'

    job = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': payload.title,
        'department': payload.department,
        'description': payload.description,
        'employment_type': payload.employment_type,
        'location': payload.location,
        'salary_range': payload.salary_range,
        'request_type': payload.request_type,
        'headcount_needed': payload.headcount_needed,
        'urgency': payload.urgency,
        'justification': payload.justification,
        'needed_by': payload.needed_by,
        'status': initial_status,
        'applicants_count': 0,
        'created_by': getattr(current_user, 'id', None),
        'created_by_name': getattr(current_user, 'name', None) or getattr(current_user, 'email', None),
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.job_postings.insert_one(job)

    # Yöneticiye bildirim — onay gerektiren talepler için
    if initial_status == 'pending_approval':
        await _notify_hr_managers(
            current_user.tenant_id,
            kind='hr_request',
            title='Yeni personel talebi',
            body=(
                f"{job.get('created_by_name') or 'Bir müdür'} • "
                f"{payload.department} • {payload.title} ({payload.headcount_needed} kişi)"
                + (f" • aciliyet: {payload.urgency}" if payload.urgency != 'normal' else '')
            ),
            link=f'/hr?tab=recruitment&job={job["id"]}',
            ref_id=job['id'],
        )

    return {'success': True, 'job_id': job['id'], 'status': initial_status}


@router.post("/hr/job-posting/{job_id}/approve")
async def approve_job_posting(
    job_id: str,
    payload: JobDecisionPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    job = await db.job_postings.find_one({'tenant_id': current_user.tenant_id, 'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    if job.get('status') not in ('pending_approval', None):
        raise HTTPException(status_code=400, detail="Bu talep zaten karara bağlanmış")
    await db.job_postings.update_one(
        {'tenant_id': current_user.tenant_id, 'id': job_id},
        {'$set': {
            'status': 'active',
            'approved_by': getattr(current_user, 'id', None),
            'approved_by_name': getattr(current_user, 'name', None),
            'approved_at': datetime.now(UTC).isoformat(),
            'decision_note': payload.note,
        }}
    )
    # Talep sahibine bildirim
    if job.get('created_by'):
        await _notify_user(
            current_user.tenant_id,
            user_id=job['created_by'],
            kind='hr_request_approved',
            title='Personel talebiniz onaylandı',
            body=f"{job.get('title')} • aday eklemeye açıldı",
            link=f'/hr?tab=recruitment&job={job_id}',
            ref_id=job_id,
        )
    return {'success': True, 'status': 'active'}


@router.post("/hr/job-posting/{job_id}/reject")
async def reject_job_posting(
    job_id: str,
    payload: JobDecisionPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    job = await db.job_postings.find_one({'tenant_id': current_user.tenant_id, 'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    await db.job_postings.update_one(
        {'tenant_id': current_user.tenant_id, 'id': job_id},
        {'$set': {
            'status': 'rejected',
            'rejected_by': getattr(current_user, 'id', None),
            'rejected_at': datetime.now(UTC).isoformat(),
            'decision_note': payload.note,
        }}
    )
    if job.get('created_by'):
        await _notify_user(
            current_user.tenant_id,
            user_id=job['created_by'],
            kind='hr_request_rejected',
            title='Personel talebiniz reddedildi',
            body=(payload.note or job.get('title') or '—'),
            link=f'/hr?tab=recruitment&job={job_id}',
            ref_id=job_id,
        )
    return {'success': True, 'status': 'rejected'}


@router.get("/hr/job-postings")
async def list_job_postings(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query: dict[str, Any] = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    items = await db.job_postings.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    return {'items': items, 'total': len(items)}


@router.post("/hr/job-posting/{job_id}/close")
async def close_job_posting(
    job_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.job_postings.update_one(
        {'tenant_id': current_user.tenant_id, 'id': job_id},
        {'$set': {'status': 'closed', 'closed_at': datetime.now(UTC).isoformat()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="İş ilanı bulunamadı")
    return {'success': True}


# ============= F&B COMPLETE SUITE =============

async def _get_ingredient_map(tenant_id: str):
    ingredients = await db.ingredients.find({'tenant_id': tenant_id}, {'_id': 0}).to_list(1000)
    return {ing['id']: ing for ing in ingredients}, ingredients


def _enrich_recipe_cost(recipe: dict, ingredient_map: dict[str, dict]):
    enriched_lines = []
    total_cost = 0
    for line in recipe.get('ingredients', []):
        ingredient = ingredient_map.get(line.get('ingredient_id'))
        unit_cost = line.get('unit_cost') or (ingredient.get('unit_cost') if ingredient else 0)
        quantity = line.get('quantity', 1)
        waste_pct = line.get('waste_pct', 0)
        line_cost = unit_cost * quantity * (1 + waste_pct / 100)
        total_cost += line_cost

        enriched_lines.append({
            'ingredient_id': line.get('ingredient_id'),
            'ingredient_name': line.get('ingredient_name') or (ingredient.get('name') if ingredient else 'Unknown'),
            'unit': line.get('unit') or (ingredient.get('unit') if ingredient else ''),
            'quantity': quantity,
            'unit_cost': round(unit_cost, 2),
            'waste_pct': waste_pct,
            'line_cost': round(line_cost, 2),
            'supplier': ingredient.get('supplier') if ingredient else None
        })

    recipe['cost_breakdown'] = enriched_lines
    recipe['total_cost'] = round(total_cost, 2)
    selling_price = recipe.get('selling_price', 0)
    recipe['gp_percentage'] = round(((selling_price - total_cost) / selling_price * 100), 1) if selling_price else 0
    recipe['ingredient_count'] = len(enriched_lines)
    return recipe


@router.post("/fnb/recipes")
async def create_recipe(recipe_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)

    recipe = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'dish_name': recipe_data.get('recipe_name') or recipe_data.get('dish_name', 'Unnamed Recipe'),
        'category': recipe_data.get('category', 'general'),
        'portion_size': recipe_data.get('portion_size', '1 portion'),
        'preparation_time': recipe_data.get('preparation_time', 15),
        'ingredients': recipe_data.get('ingredients', []),
        'selling_price': recipe_data.get('selling_price', 0),
        'active': True,
        'created_at': datetime.now(UTC).isoformat()
    }

    recipe = _enrich_recipe_cost(recipe, ingredient_map)
    await db.recipes.insert_one(recipe)

    return {
        'success': True,
        'recipe_id': recipe['id'],
        'gp_percentage': recipe['gp_percentage'],
        'total_cost': recipe['total_cost']
    }


@router.get("/fnb/recipes")
async def get_recipes(current_user: User = Depends(get_current_user)):
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)
    recipes = await db.recipes.find(
        {'tenant_id': current_user.tenant_id, 'active': True},
        {'_id': 0}
    ).sort('dish_name', 1).to_list(200)

    enriched = [_enrich_recipe_cost(dict(recipe), ingredient_map) for recipe in recipes]
    avg_gp = sum([r.get('gp_percentage', 0) for r in enriched]) / len(enriched) if enriched else 0
    avg_food_cost = sum([r.get('total_cost', 0) for r in enriched]) / len(enriched) if enriched else 0

    return {
        'recipes': enriched,
        'total': len(enriched),
        'avg_gp': round(avg_gp, 1),
        'avg_food_cost': round(avg_food_cost, 2)
    }


@router.get("/fnb/recipes/{recipe_id}")
async def get_recipe(recipe_id: str, current_user: User = Depends(get_current_user)):
    recipe = await db.recipes.find_one({'tenant_id': current_user.tenant_id, 'id': recipe_id}, {'_id': 0})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)
    recipe = _enrich_recipe_cost(recipe, ingredient_map)
    return {'recipe': recipe}


@router.put("/fnb/recipes/{recipe_id}")
async def update_recipe(recipe_id: str, recipe_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    recipe = await db.recipes.find_one({'tenant_id': current_user.tenant_id, 'id': recipe_id})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    updated = {**recipe, **recipe_data}
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)
    updated = _enrich_recipe_cost(updated, ingredient_map)

    await db.recipes.update_one(
        {'tenant_id': current_user.tenant_id, 'id': recipe_id},
        {'$set': updated}
    )
    updated.pop('_id', None)
    return {'success': True, 'recipe': updated}

@router.post("/fnb/beo")
async def create_beo(beo_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    beo = {
        'id': str(uuid.uuid4()), 'tenant_id': current_user.tenant_id,
        **beo_data, 'status': 'confirmed',
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.banquet_event_orders.insert_one(beo)
    return {'success': True, 'beo_id': beo['id'], 'message': 'BEO olusturuldu'}

# NOTE: Kitchen Display System endpoints moved to pos_fnb_router.py


@router.get("/fnb/ingredients")
async def list_ingredients(current_user: User = Depends(get_current_user)):
    ingredients = await db.ingredients.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('name', 1).to_list(500)

    low_stock = [ing for ing in ingredients if ing.get('current_stock', 0) <= ing.get('reorder_point', 0)]
    total_value = sum((ing.get('current_stock', 0) * ing.get('unit_cost', 0)) for ing in ingredients)

    categories = {}
    for ing in ingredients:
        cat = ing.get('category', 'other')
        categories.setdefault(cat, 0)
        categories[cat] += 1

    return {
        'ingredients': ingredients,
        'summary': {
            'total_items': len(ingredients),
            'low_stock': len(low_stock),
            'inventory_value': round(total_value, 2),
            'categories': categories
        }
    }


@router.post("/fnb/ingredients")
async def add_ingredient(ing_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    ingredient = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': ing_data['name'],
        'category': ing_data.get('category', 'general'),
        'unit': ing_data.get('unit', 'kg'),
        'current_stock': ing_data.get('current_stock', 0),
        'par_level': ing_data.get('par_level', 0),
        'reorder_point': ing_data.get('reorder_point', 0),
        'unit_cost': ing_data.get('unit_cost', 0),
        'supplier': ing_data.get('supplier'),
        'last_order_date': ing_data.get('last_order_date'),
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.ingredients.insert_one(ingredient)
    ingredient.pop('_id', None)
    return {'success': True, 'ingredient': ingredient}


@router.put("/fnb/ingredients/{ingredient_id}")
async def update_ingredient(ingredient_id: str, ing_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    ingredient = await db.ingredients.find_one({'tenant_id': current_user.tenant_id, 'id': ingredient_id})
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    updated = {**ingredient, **ing_data}
    await db.ingredients.update_one(
        {'tenant_id': current_user.tenant_id, 'id': ingredient_id},
        {'$set': updated}
    )
    updated.pop('_id', None)
    return {'success': True, 'ingredient': updated}


# ============= Departments / Positions (HR settings) =============

class DepartmentPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    code: str | None = Field(None, max_length=40)
    description: str | None = Field(None, max_length=300)


class PositionPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    department: str | None = Field(None, max_length=80)
    default_hourly_rate: float | None = Field(None, ge=0, le=100000)


@router.get("/hr/departments")
async def list_departments(current_user: User = Depends(get_current_user)):
    items = await db.hr_departments.find(
        {'tenant_id': current_user.tenant_id}, {'_id': 0}
    ).sort('name', 1).to_list(200)
    return {'items': items, 'total': len(items)}


@router.post("/hr/departments")
async def create_department(
    payload: DepartmentPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    code = (payload.code or payload.name.lower().replace(' ', '_'))[:40]
    if await db.hr_departments.find_one(
        {'tenant_id': current_user.tenant_id, 'code': code}
    ):
        raise HTTPException(status_code=409, detail="Bu departman kodu zaten var")
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': payload.name,
        'code': code,
        'description': payload.description,
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.hr_departments.insert_one(item)
    item.pop('_id', None)
    return {'success': True, 'department': item}


@router.delete("/hr/departments/{dept_id}")
async def delete_department(
    dept_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.hr_departments.delete_one(
        {'tenant_id': current_user.tenant_id, 'id': dept_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Departman bulunamadı")
    return {'success': True}


@router.get("/hr/positions")
async def list_positions(current_user: User = Depends(get_current_user)):
    items = await db.hr_positions.find(
        {'tenant_id': current_user.tenant_id}, {'_id': 0}
    ).sort('title', 1).to_list(300)
    return {'items': items, 'total': len(items)}


@router.post("/hr/positions")
async def create_position(
    payload: PositionPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': payload.title,
        'department': payload.department,
        'default_hourly_rate': payload.default_hourly_rate,
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.hr_positions.insert_one(item)
    item.pop('_id', None)
    return {'success': True, 'position': item}


@router.delete("/hr/positions/{pos_id}")
async def delete_position(
    pos_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.hr_positions.delete_one(
        {'tenant_id': current_user.tenant_id, 'id': pos_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pozisyon bulunamadı")
    return {'success': True}


# ============= Staff CRUD (POST/GET/PUT/DELETE/profile) =============

def _scrub_encrypted(value):
    if isinstance(value, str) and value.startswith('aes256gcm:'):
        return ''
    return value or ''


@router.post("/hr/staff")
async def add_staff_member(
    staff_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Yeni personel ekle.

    Zorunlu: name. Diğer alanlar opsiyonel; UI form akışı eksik bilgiyle
    de minimum personel kaydı oluşturabilsin diye gevşetildi.
    Ek finansal alanlar (hourly_rate, monthly_hours, annual_leave_entitlement)
    payroll ve izin bakiyesi hesaplarında kullanılır.
    """
    if not staff_data.get('name'):
        raise HTTPException(status_code=400, detail="Personel adı zorunludur")
    staff = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': staff_data['name'],
        'email': staff_data.get('email'),
        'phone': staff_data.get('phone'),
        'department': staff_data.get('department'),
        'position': staff_data.get('position'),
        'hire_date': staff_data.get('hire_date'),
        'employment_type': staff_data.get('employment_type', 'full_time'),
        'hourly_rate': staff_data.get('hourly_rate'),
        'monthly_hours': staff_data.get('monthly_hours'),
        'annual_leave_entitlement': staff_data.get('annual_leave_entitlement', 14),
        'performance_score': 0.0,
        'active': True,
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.staff_members.insert_one(staff)
    return {'success': True, 'staff_id': staff['id']}


@router.get("/hr/staff")
async def get_staff_list(
    department: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Personel listesi.

    Önce `staff_members` koleksiyonundan açıkça eklenen kayıtları al; sonra
    `users` tablosundan staff role'lerini (housekeeping, front_desk,
    supervisor, finance, sales, admin) türeterek listeyi tamamla.
    Email bazlı dedup + KVKK için yetki kısıtı + allow-list projection.
    """
    tid = current_user.tenant_id
    role_to_dept = {
        'housekeeping': 'housekeeping',
        'front_desk': 'front_desk',
        'supervisor': 'management',
        'finance': 'finance',
        'sales': 'sales',
        'admin': 'management',
    }

    explicit_query: dict = {'tenant_id': tid, 'active': True}
    if department:
        explicit_query['department'] = department
    explicit = await db.staff_members.find(explicit_query, {'_id': 0}).to_list(200)
    seen_emails = {(s.get('email') or '').lower() for s in explicit if s.get('email')}

    user_query: dict = {
        'tenant_id': tid,
        'is_active': True,
        'role': {'$in': list(role_to_dept.keys())},
    }
    if department:
        roles_in_dept = [r for r, d in role_to_dept.items() if d == department or r == department]
        user_query['role'] = {'$in': roles_in_dept or ['__none__']}

    user_projection = {
        '_id': 0,
        'id': 1, 'name': 1, 'email': 1, 'phone': 1,
        'role': 1, 'created_at': 1,
    }

    derived: list = []
    cursor = db.users.find(user_query, user_projection).limit(500)
    async for u in cursor:
        email_raw = (u.get('email') or '')
        em = email_raw.lower()
        if em and em in seen_emails:
            continue
        role = u.get('role')
        email_clean = _scrub_encrypted(email_raw)
        phone_clean = _scrub_encrypted(u.get('phone'))
        derived.append({
            'id': u.get('id'),
            'tenant_id': tid,
            'name': u.get('name') or email_clean or 'Personel',
            'email': email_clean,
            'phone': phone_clean,
            'department': role_to_dept.get(role, role or 'other'),
            'position': role or 'staff',
            'hire_date': (u.get('created_at') or '')[:10],
            'employment_type': 'full_time',
            'performance_score': 0.0,
            'active': True,
            'derived_from': 'users',
        })
        if em:
            seen_emails.add(em)

    combined = explicit + derived
    return {'staff': combined, 'total': len(combined)}


@router.get("/hr/performance/{staff_id}")
async def get_staff_performance_summary(
    staff_id: str,
    current_user: User = Depends(get_current_user),
):
    """Personel performans özeti (son 10 review + ortalama puan)."""
    reviews = await db.performance_reviews.find({
        'staff_id': staff_id,
        'tenant_id': current_user.tenant_id,
    }, {'_id': 0}).sort('reviewed_at', -1).to_list(10)

    avg_score = sum([r.get('overall_score', 0) for r in reviews]) / len(reviews) if reviews else 0

    return {
        'staff_id': staff_id,
        'recent_reviews': reviews,
        'avg_performance_score': round(avg_score, 2),
        'total_reviews': len(reviews),
    }


class StaffUpdatePayload(BaseModel):
    name: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=40)
    department: str | None = Field(None, max_length=80)
    position: str | None = Field(None, max_length=120)
    hire_date: str | None = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    employment_type: Literal[
        'full_time', 'part_time', 'seasonal', 'contract', 'intern'
    ] | None = None
    hourly_rate: float | None = Field(None, ge=0, le=100000)
    monthly_hours: float | None = Field(None, ge=0, le=400)
    annual_leave_entitlement: int | None = Field(None, ge=0, le=365)


@router.put("/hr/staff/{staff_id}")
async def update_staff_member(
    staff_id: str,
    payload: StaffUpdatePayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Personel güncelle.

    HR-managed (`staff_members`): tüm alanlar güncellenebilir.
    Users-derived (kullanıcı kaydından türetilmiş): sadece **iletişim**
    alanları (email/phone/name) güncellenebilir; rol/departman/maaş gibi
    alanlar Kullanıcı Yönetimi üzerinden değiştirilir.
    """
    existing = await db.staff_members.find_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id}
    )
    if existing:
        update = {
            k: v for k, v in payload.model_dump(exclude_unset=True).items()
            if v is not None
        }
        if not update:
            return {'success': True, 'updated_fields': 0}
        update['updated_at'] = datetime.now(UTC).isoformat()
        await db.staff_members.update_one(
            {'tenant_id': current_user.tenant_id, 'id': staff_id},
            {'$set': update}
        )
        return {'success': True, 'updated_fields': len(update) - 1, 'source': 'staff'}

    # Users-derived path — sadece iletişim alanları
    user = await db.users.find_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id, 'is_active': True},
        {'_id': 0, 'id': 1}
    )
    if not user:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")

    raw = payload.model_dump(exclude_unset=True)
    allowed = {k: v for k, v in raw.items() if k in {'name', 'email', 'phone'} and v is not None}
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail="Türetilmiş personel için yalnızca isim, e-posta ve telefon güncellenebilir."
        )
    allowed['updated_at'] = datetime.now(UTC).isoformat()
    await db.users.update_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id},
        {'$set': allowed}
    )
    return {'success': True, 'updated_fields': len(allowed) - 1, 'source': 'users'}


@router.delete("/hr/staff/{staff_id}")
async def delete_staff_member(
    staff_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """İşten ayrılış (soft deactivate). Personel ASLA hard-delete edilmez —
    bordro / devam / izin geçmişi korunur, listeden çıkar.

    HR-managed: `staff_members.active=False`.
    Users-derived: `users.is_active=False`.
    """
    now_iso = datetime.now(UTC).isoformat()
    res = await db.staff_members.update_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id},
        {'$set': {
            'active': False,
            'deactivated_at': now_iso,
        }}
    )
    if res.matched_count > 0:
        return {'success': True, 'source': 'staff', 'deactivated_at': now_iso}

    # Users-derived ayrılış
    res2 = await db.users.update_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id, 'is_active': True},
        {'$set': {
            'is_active': False,
            'deactivated_at': now_iso,
        }}
    )
    if res2.matched_count == 0:
        raise HTTPException(status_code=404, detail="Personel bulunamadı veya zaten ayrılmış")
    return {'success': True, 'source': 'users', 'deactivated_at': now_iso}


@router.get("/hr/staff/{staff_id}/profile")
async def get_staff_profile(
    staff_id: str,
    current_user: User = Depends(get_current_user),
):
    """Aggregate profil: kişi + son 30g devam + izinler + performans + bordro + vardiya."""
    staff = await _verify_staff_in_tenant(staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    today = _today_local()
    start_30 = today - timedelta(days=30)

    attendance = await db.attendance_records.find({
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'date': {'$gte': start_30.isoformat(), '$lte': today.isoformat()},
    }, {'_id': 0}).sort('date', -1).to_list(100)

    leaves = await db.leave_requests.find({
        'tenant_id': current_user.tenant_id, 'staff_id': staff_id,
    }, {'_id': 0}).sort('created_at', -1).to_list(100)

    reviews = await db.performance_reviews.find({
        'tenant_id': current_user.tenant_id, 'staff_id': staff_id,
    }, {'_id': 0}).sort('reviewed_at', -1).to_list(50)

    payroll = await db.payroll_records.find({
        'tenant_id': current_user.tenant_id, 'staff_id': staff_id,
    }, {'_id': 0}).sort('period_month', -1).to_list(12)

    shifts = await db.shift_schedules.find({
        'tenant_id': current_user.tenant_id, 'staff_id': staff_id,
        'shift_date': {'$gte': today.isoformat()},
    }, {'_id': 0}).sort('shift_date', 1).to_list(20)

    total_hours = round(sum(r.get('total_hours', 0) for r in attendance), 2)
    days_present = len({r['date'] for r in attendance if r.get('clock_out')})
    avg_score = (
        round(sum(r.get('overall_score', 0) for r in reviews) / len(reviews), 2)
        if reviews else 0
    )

    balance = await db.leave_balances.find_one({
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'year': today.year,
    }, {'_id': 0})

    return {
        'staff': staff,
        'attendance': {
            'records': attendance,
            'total_hours_30d': total_hours,
            'days_present_30d': days_present,
        },
        'leaves': {
            'items': leaves,
            'total': len(leaves),
            'pending': sum(1 for leave in leaves if leave.get('status') == 'pending'),
        },
        'leave_balance': balance,
        'performance': {
            'items': reviews,
            'avg_score': avg_score,
            'total': len(reviews),
        },
        'payroll': {
            'recent': payroll,
            'count': len(payroll),
        },
        'upcoming_shifts': shifts,
    }


# ============= Leave Balance (yıllık izin bakiyesi) =============

class LeaveBalancePayload(BaseModel):
    staff_id: str = Field(..., min_length=1)
    year: int = Field(..., ge=2020, le=2100)
    annual_entitlement: int = Field(..., ge=0, le=365)
    carry_over: int | None = Field(0, ge=0, le=365)
    sick_entitlement: int | None = Field(None, ge=0, le=365)


@router.get("/hr/leave-balance/{staff_id}")
async def get_leave_balance(
    staff_id: str,
    year: int | None = None,
    current_user: User = Depends(get_current_user),
):
    yr = year or _today_local().year
    staff = await _verify_staff_in_tenant(staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    balance = await db.leave_balances.find_one({
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'year': yr,
    }, {'_id': 0})
    # İş Kanunu m.53 default: 14 gün yıllık ücretli izin
    annual_ent = balance.get('annual_entitlement', 14) if balance else 14
    carry = balance.get('carry_over', 0) if balance else 0
    sick_ent = balance.get('sick_entitlement', 5) if balance else 5

    approved = await db.leave_requests.find({
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'status': 'approved',
        'start_date': {'$gte': f'{yr}-01-01', '$lte': f'{yr}-12-31'},
    }, {'_id': 0}).to_list(500)
    used_annual = sum(
        leave.get('total_days', 0) for leave in approved
        if leave.get('leave_type') == 'annual'
    )
    used_sick = sum(
        leave.get('total_days', 0) for leave in approved
        if leave.get('leave_type') == 'sick'
    )
    total_annual = annual_ent + carry
    return {
        'staff_id': staff_id,
        'staff_name': staff.get('name'),
        'year': yr,
        'configured': bool(balance),
        'annual': {
            'entitlement': annual_ent,
            'carry_over': carry,
            'total': total_annual,
            'used': used_annual,
            'remaining': max(0, total_annual - used_annual),
        },
        'sick': {
            'entitlement': sick_ent,
            'used': used_sick,
            'remaining': max(0, sick_ent - used_sick),
        },
    }


@router.post("/hr/leave-balance")
async def set_leave_balance(
    payload: LeaveBalancePayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    staff = await _verify_staff_in_tenant(payload.staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    doc = {
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'year': payload.year,
        'annual_entitlement': payload.annual_entitlement,
        'carry_over': payload.carry_over or 0,
        'sick_entitlement': (
            payload.sick_entitlement if payload.sick_entitlement is not None else 5
        ),
        'updated_at': datetime.now(UTC).isoformat(),
    }
    await db.leave_balances.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'staff_id': payload.staff_id,
            'year': payload.year,
        },
        {'$set': doc},
        upsert=True,
    )
    return {'success': True}


# ============= Shifts (vardiya planlaması) =============

class ShiftPayload(BaseModel):
    staff_id: str = Field(..., min_length=1)
    shift_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    shift_type: Literal['morning', 'afternoon', 'evening', 'night', 'split'] = 'morning'
    start_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')
    end_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')
    notes: str | None = Field(None, max_length=300)


@router.post("/hr/shifts")
async def create_shift_v2(
    payload: ShiftPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    staff = await _verify_staff_in_tenant(payload.staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'staff_name': staff.get('name'),
        'shift_date': payload.shift_date,
        'shift_type': payload.shift_type,
        'start_time': payload.start_time,
        'end_time': payload.end_time,
        'notes': payload.notes,
        'status': 'scheduled',
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.shift_schedules.insert_one(item)
    item.pop('_id', None)
    return {'success': True, 'shift': item}


@router.get("/hr/shifts")
async def list_shifts(
    start: str | None = None,
    end: str | None = None,
    staff_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    today = _today_local()
    start_dt = (
        datetime.fromisoformat(start).date() if start
        else today - timedelta(days=7)
    )
    end_dt = (
        datetime.fromisoformat(end).date() if end
        else today + timedelta(days=14)
    )
    query: dict[str, Any] = {
        'tenant_id': current_user.tenant_id,
        'shift_date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()},
    }
    if staff_id:
        query['staff_id'] = staff_id
    items = await db.shift_schedules.find(
        query, {'_id': 0}
    ).sort('shift_date', 1).to_list(2000)

    # Personel adıyla zenginleştir (hem staff_members hem türeyen users)
    staff_map = await _get_staff_map(current_user.tenant_id)
    user_cursor = db.users.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True,
        'role': {'$in': [
            'housekeeping', 'front_desk', 'supervisor',
            'finance', 'sales', 'admin'
        ]},
    }, {'_id': 0, 'id': 1, 'name': 1})
    async for u in user_cursor:
        if u['id'] not in staff_map:
            staff_map[u['id']] = {'id': u['id'], 'name': u.get('name') or 'Personel'}
    for item in items:
        if not item.get('staff_name'):
            sm = staff_map.get(item.get('staff_id'), {})
            item['staff_name'] = sm.get('name', item.get('staff_id'))
    return {
        'items': items,
        'total': len(items),
        'range': {'start': start_dt.isoformat(), 'end': end_dt.isoformat()},
    }


@router.delete("/hr/shifts/{shift_id}")
async def delete_shift(
    shift_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.shift_schedules.delete_one(
        {'tenant_id': current_user.tenant_id, 'id': shift_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Vardiya bulunamadı")
    return {'success': True}


# ============= Recruitment Applicants =============

class ApplicantPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=2000)
    cv_url: str | None = Field(None, max_length=500)


class ApplicantStatusPayload(BaseModel):
    status: Literal['new', 'screening', 'interview', 'offer', 'hired', 'rejected']
    note: str | None = Field(None, max_length=500)


@router.post("/hr/job-postings/{job_id}/applicants")
async def add_applicant(
    job_id: str,
    payload: ApplicantPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    job = await db.job_postings.find_one(
        {'tenant_id': current_user.tenant_id, 'id': job_id}
    )
    if not job:
        raise HTTPException(status_code=404, detail="İş ilanı bulunamadı")
    if job.get('status') != 'active':
        raise HTTPException(
            status_code=400,
            detail="Sadece aktif (yayında) ilanlara aday eklenebilir",
        )
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'job_id': job_id,
        'job_title': job.get('title'),
        'name': payload.name,
        'email': payload.email,
        'phone': payload.phone,
        'notes': payload.notes,
        'cv_url': payload.cv_url,
        'status': 'new',
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.job_applicants.insert_one(item)
    await db.job_postings.update_one(
        {'tenant_id': current_user.tenant_id, 'id': job_id},
        {'$inc': {'applicants_count': 1}},
    )
    item.pop('_id', None)
    return {'success': True, 'applicant': item}


@router.get("/hr/job-postings/{job_id}/applicants")
async def list_applicants(
    job_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    items = await db.job_applicants.find({
        'tenant_id': current_user.tenant_id,
        'job_id': job_id,
    }, {'_id': 0}).sort('created_at', -1).to_list(500)
    counts: dict[str, int] = {}
    for it in items:
        s = it.get('status', 'new')
        counts[s] = counts.get(s, 0) + 1
    return {'items': items, 'total': len(items), 'counts': counts}


@router.post("/hr/applicants/{applicant_id}/status")
async def update_applicant_status(
    applicant_id: str,
    payload: ApplicantStatusPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.job_applicants.update_one(
        {'tenant_id': current_user.tenant_id, 'id': applicant_id},
        {'$set': {
            'status': payload.status,
            'status_note': payload.note,
            'status_updated_by': getattr(current_user, 'id', None),
            'status_updated_at': datetime.now(UTC).isoformat(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Aday bulunamadı")
    return {'success': True, 'status': payload.status}


# ============= Performance Templates =============

class CompetencyItem(BaseModel):
    name: str = Field(..., max_length=100)
    weight: float = Field(1.0, ge=0, le=10)


class PerformanceTemplatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=1000)
    competencies: list[CompetencyItem] = Field(default_factory=list)


@router.get("/hr/performance-templates")
async def list_performance_templates(
    current_user: User = Depends(get_current_user),
):
    items = await db.performance_templates.find({
        'tenant_id': current_user.tenant_id,
    }, {'_id': 0}).sort('name', 1).to_list(100)
    return {'items': items, 'total': len(items)}


@router.post("/hr/performance-templates")
async def create_performance_template(
    payload: PerformanceTemplatePayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': payload.name,
        'description': payload.description,
        'competencies': [c.model_dump() for c in payload.competencies],
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.performance_templates.insert_one(item)
    item.pop('_id', None)
    return {'success': True, 'template': item}


@router.delete("/hr/performance-templates/{tpl_id}")
async def delete_performance_template(
    tpl_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.performance_templates.delete_one({
        'tenant_id': current_user.tenant_id,
        'id': tpl_id,
    })
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    return {'success': True}


# ============================================================================
# HR FAZ 2 — Eklentiler (Mayıs 2026)
#   1. Mesai (overtime) talep + onay/red + 270h/yıl üst sınırı
#   2. Vardiya değişim talebi + onay (atomic swap)
#   3. Maaş geçmişi / zam kaydı
#   4. İşten ayrılma süreci (Türk İş K. m.14 kıdem tazminatı hesabı)
#   5. Eğitim/sertifika takibi (expiry alarmı)
#   6. Personel belgeleri (multipart upload, MongoDB inline base64, max 5MB)
#   7. Performans hedef-ilerleme check-in
# ============================================================================

# TR İş Kanunu m.41/3: yıllık fazla mesai üst sınırı 270 saat.
TR_ANNUAL_OVERTIME_CAP_HOURS = 270
# m.14 / m.17: kıdem tazminatı = 30 günlük brüt × tam yıl. Yasal tavan
# (kıdem tazminatı tavanı) günlük üst sınır olarak uygulanır — 2026 yarıyıl
# için yaklaşık 53.919,68 TL/aylık (1.797,32 TL/gün). Tenant override için
# settings.severance_daily_cap kullanılabilir.
SEVERANCE_DAYS_PER_YEAR = 30
TR_SEVERANCE_DAILY_CAP_DEFAULT = 1797.32  # 2026 H1 — günlük brüt tavanı
HR_ELEVATED_ROLES = {'admin', 'owner', 'supervisor', 'manager', 'hr', 'finance'}
# Belge boyut sınırı (MongoDB document ~16MB üst sınırı; güvenli marj).
DOC_MAX_BYTES = 5 * 1024 * 1024


# ============= 1. Mesai Talebi =============

class OvertimeRequestPayload(BaseModel):
    staff_id: str = Field(..., min_length=1, max_length=128)
    work_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    hours: float = Field(..., gt=0, le=12)
    reason: str = Field(..., min_length=3, max_length=1000)


class OvertimeDecisionPayload(BaseModel):
    action: Literal['approve', 'reject']
    note: str | None = Field(None, max_length=500)


async def _yearly_overtime_hours(tenant_id: str, staff_id: str, year: int) -> float:
    """Onaylanmış (status=approved) yıllık fazla mesai toplamı."""
    cursor = db.overtime_requests.find({
        'tenant_id': tenant_id,
        'staff_id': staff_id,
        'status': 'approved',
        'work_date': {'$gte': f'{year}-01-01', '$lte': f'{year}-12-31'},
    }, {'_id': 0, 'hours': 1})
    total = 0.0
    async for d in cursor:
        total += float(d.get('hours') or 0)
    return total


@router.post("/hr/overtime-request")
async def create_overtime_request(
    payload: OvertimeRequestPayload,
    current_user: User = Depends(get_current_user),
):
    staff = await _verify_staff_in_tenant(payload.staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    # Self-service guard: yetkisi olmayan kullanıcı sadece kendi adına talep açabilir.
    if getattr(current_user, 'role', None) not in HR_ELEVATED_ROLES:
        user_email = (getattr(current_user, 'email', None) or '').lower()
        staff_email = (staff.get('email') or '').lower()
        if not user_email or user_email != staff_email:
            raise HTTPException(status_code=403, detail="Sadece kendi adınıza talep açabilirsiniz")
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': payload.staff_id,
        'staff_name': staff.get('name'),
        'work_date': payload.work_date,
        'hours': payload.hours,
        'reason': payload.reason,
        'status': 'pending',
        'requested_by': getattr(current_user, 'id', None),
        'requested_at': datetime.now(UTC).isoformat(),
    }
    await db.overtime_requests.insert_one(item)
    item.pop('_id', None)
    await _notify_hr_managers(
        current_user.tenant_id,
        kind='overtime_request',
        title=f"Mesai talebi: {staff.get('name')}",
        body=f"{payload.work_date} — {payload.hours:g} saat. Sebep: {payload.reason[:120]}",
        link=f"/hr-complete?tab=overtime",
        ref_id=item['id'],
    )
    return {'success': True, 'overtime_request': item}


@router.get("/hr/overtime-requests")
async def list_overtime_requests(
    staff_id: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query: dict[str, Any] = {'tenant_id': current_user.tenant_id}
    if staff_id:
        query['staff_id'] = staff_id
    if status:
        query['status'] = status
    items = await db.overtime_requests.find(query, {'_id': 0}).sort('requested_at', -1).to_list(500)
    counts = {'pending': 0, 'approved': 0, 'rejected': 0}
    for it in items:
        counts[it.get('status', 'pending')] = counts.get(it.get('status', 'pending'), 0) + 1
    return {'items': items, 'total': len(items), 'counts': counts}


@router.post("/hr/overtime-request/{req_id}/decision")
async def decide_overtime_request(
    req_id: str,
    payload: OvertimeDecisionPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    req = await db.overtime_requests.find_one({
        'tenant_id': current_user.tenant_id, 'id': req_id,
    })
    if not req:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    if req.get('status') != 'pending':
        raise HTTPException(status_code=400, detail="Bu talep zaten karara bağlanmış")

    if payload.action == 'approve':
        # 270h/yıl kontrolü (İş K. m.41/3)
        year = int(req['work_date'][:4])
        already = await _yearly_overtime_hours(
            current_user.tenant_id, req['staff_id'], year,
        )
        proposed = float(req.get('hours') or 0)
        if already + proposed > TR_ANNUAL_OVERTIME_CAP_HOURS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Yıllık 270 saat fazla mesai üst sınırı aşılır "
                    f"(mevcut: {already:g}h, talep: {proposed:g}h, sınır: 270h)"
                ),
            )
        new_status = 'approved'
        notify_kind = 'overtime_approved'
        notify_title = "Mesai talebiniz onaylandı"
    else:
        new_status = 'rejected'
        notify_kind = 'overtime_rejected'
        notify_title = "Mesai talebiniz reddedildi"

    await db.overtime_requests.update_one(
        {'tenant_id': current_user.tenant_id, 'id': req_id},
        {'$set': {
            'status': new_status,
            'decision_note': payload.note,
            'decided_by': getattr(current_user, 'id', None),
            'decided_at': datetime.now(UTC).isoformat(),
        }},
    )
    requester = req.get('requested_by')
    if requester:
        await _notify_user(
            current_user.tenant_id, user_id=requester,
            kind=notify_kind, title=notify_title,
            body=f"{req['work_date']} — {req['hours']:g}h. " + (payload.note or ''),
            ref_id=req_id,
        )
    return {'success': True, 'status': new_status}


# ============= 2. Vardiya Değişim Talebi =============

class ShiftSwapRequestPayload(BaseModel):
    shift_id: str = Field(..., min_length=1)
    target_staff_id: str = Field(..., min_length=1)
    reason: str | None = Field(None, max_length=500)


class ShiftSwapDecisionPayload(BaseModel):
    action: Literal['approve', 'reject']
    note: str | None = Field(None, max_length=500)


@router.post("/hr/shift-swap-request")
async def create_shift_swap(
    payload: ShiftSwapRequestPayload,
    current_user: User = Depends(get_current_user),
):
    shift = await db.shift_schedules.find_one({
        'tenant_id': current_user.tenant_id, 'id': payload.shift_id,
    })
    if not shift:
        raise HTTPException(status_code=404, detail="Vardiya bulunamadı")
    target = await _verify_staff_in_tenant(payload.target_staff_id, current_user.tenant_id)
    if not target:
        raise HTTPException(status_code=404, detail="Hedef personel bulunamadı")
    if shift['staff_id'] == payload.target_staff_id:
        raise HTTPException(status_code=400, detail="Hedef personel mevcut sahibinin aynısı olamaz")
    # Self-service guard: yetkisiz kullanıcı sadece kendi vardiyasını değişime sunabilir.
    if getattr(current_user, 'role', None) not in HR_ELEVATED_ROLES:
        user_email = (getattr(current_user, 'email', None) or '').lower()
        owner = await db.staff.find_one(
            {'tenant_id': current_user.tenant_id, 'id': shift['staff_id']},
            {'_id': 0, 'email': 1},
        )
        owner_email = ((owner or {}).get('email') or '').lower()
        if not user_email or user_email != owner_email:
            raise HTTPException(status_code=403, detail="Sadece kendi vardiyanızı değişime sunabilirsiniz")
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'shift_id': payload.shift_id,
        'shift_date': shift.get('shift_date'),
        'shift_type': shift.get('shift_type'),
        'from_staff_id': shift['staff_id'],
        'from_staff_name': shift.get('staff_name'),
        'target_staff_id': payload.target_staff_id,
        'target_staff_name': target.get('name'),
        'reason': payload.reason,
        'status': 'pending',
        # Çift onay akışı: önce hedef personelin rızası, sonra İK kararı.
        'target_consent_status': 'pending',
        'target_consent_at': None,
        'target_consent_note': None,
        'requested_by': getattr(current_user, 'id', None),
        'requested_at': datetime.now(UTC).isoformat(),
    }
    await db.shift_swap_requests.insert_one(item)
    item.pop('_id', None)
    # Hedef personele bildirim — rıza bekleniyor.
    target_user = await db.users.find_one(
        {'tenant_id': current_user.tenant_id, 'email': (target.get('email') or '').lower()},
        {'_id': 0, 'id': 1},
    ) if target.get('email') else None
    if target_user and target_user.get('id'):
        await _notify_user(
            current_user.tenant_id, user_id=target_user['id'],
            kind='shift_swap_consent_request',
            title="Vardiya devralma talebi",
            body=f"{shift.get('staff_name')} {shift.get('shift_date')} {shift.get('shift_type')} vardiyasını size devretmek istiyor",
            link="/hr/shifts",
            ref_id=item['id'],
        )
    await _notify_hr_managers(
        current_user.tenant_id,
        kind='shift_swap_request',
        title="Vardiya değişim talebi (hedef onayı bekliyor)",
        body=f"{shift.get('staff_name')} → {target.get('name')} ({shift.get('shift_date')} {shift.get('shift_type')})",
        link="/hr/shifts",
        ref_id=item['id'],
    )
    return {'success': True, 'request': item}


class ShiftSwapConsentPayload(BaseModel):
    action: Literal['approve', 'reject']
    note: str | None = Field(None, max_length=500)


@router.post("/hr/shift-swap-request/{req_id}/consent")
async def consent_shift_swap(
    req_id: str,
    payload: ShiftSwapConsentPayload,
    current_user: User = Depends(get_current_user),
):
    """Hedef personelin vardiyayı devralmaya rıza/red bildirmesi."""
    req = await db.shift_swap_requests.find_one({
        'tenant_id': current_user.tenant_id, 'id': req_id,
    })
    if not req:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    if req.get('status') != 'pending':
        raise HTTPException(status_code=400, detail="Talep zaten karara bağlanmış")
    if req.get('target_consent_status') != 'pending':
        raise HTTPException(status_code=400, detail="Bu talebe daha önce yanıt verilmiş")

    # Sadece hedef personel rıza verebilir (yöneticiler dahil değil — etik gereği bizzat hedef).
    target = await db.staff.find_one(
        {'tenant_id': current_user.tenant_id, 'id': req['target_staff_id']},
        {'_id': 0, 'email': 1},
    )
    user_email = (getattr(current_user, 'email', None) or '').lower()
    target_email = ((target or {}).get('email') or '').lower()
    if not user_email or user_email != target_email:
        raise HTTPException(status_code=403, detail="Bu talep size ait değil — sadece hedef personel yanıtlayabilir")

    new_consent = 'approved' if payload.action == 'approve' else 'rejected'
    new_status = req.get('status') if new_consent == 'approved' else 'rejected'
    # Atomik update: target_consent_status hâlâ 'pending' iken yaz; aksi halde başka bir
    # eşzamanlı çağrı yanıt vermiş demektir (race koruması).
    res = await db.shift_swap_requests.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'id': req_id,
            'target_consent_status': 'pending',
        },
        {'$set': {
            'target_consent_status': new_consent,
            'target_consent_at': datetime.now(UTC).isoformat(),
            'target_consent_note': payload.note,
            'status': new_status,
        }},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=409, detail="Bu talebe bu sırada başka bir yanıt verildi")
    # Talep sahibine bildir.
    if req.get('requested_by'):
        await _notify_user(
            current_user.tenant_id, user_id=req['requested_by'],
            kind=f'shift_swap_consent_{new_consent}',
            title=f"Hedef personel vardiyayı {('kabul etti' if new_consent == 'approved' else 'reddetti')}",
            body=f"{req.get('shift_date')} {req.get('shift_type')} — " + (payload.note or ''),
            ref_id=req_id,
        )
    return {'success': True, 'target_consent_status': new_consent, 'status': new_status}


@router.get("/hr/shift-swap-requests")
async def list_shift_swap_requests(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query: dict[str, Any] = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    items = await db.shift_swap_requests.find(query, {'_id': 0}).sort('requested_at', -1).to_list(500)
    return {'items': items, 'total': len(items)}


@router.post("/hr/shift-swap-request/{req_id}/decision")
async def decide_shift_swap(
    req_id: str,
    payload: ShiftSwapDecisionPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    req = await db.shift_swap_requests.find_one({
        'tenant_id': current_user.tenant_id, 'id': req_id,
    })
    if not req:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    if req.get('status') != 'pending':
        raise HTTPException(status_code=400, detail="Bu talep zaten karara bağlanmış")

    if payload.action == 'approve':
        # Çift onay gate: hedef personelin rızası alınmadan İK onaylayamaz.
        if req.get('target_consent_status') != 'approved':
            raise HTTPException(
                status_code=409,
                detail="Hedef personel henüz rıza vermedi — önce rıza beklenmeli",
            )
        # Atomik swap: shift'i target_staff_id'ye devret
        target = await _verify_staff_in_tenant(req['target_staff_id'], current_user.tenant_id)
        if not target:
            raise HTTPException(status_code=400, detail="Hedef personel artık aktif değil")
        # Atomik filtre: vardiyanın hâlâ orijinal sahibinde olduğunu doğrula.
        # Aksi halde başka bir swap zaten uygulanmış demektir (race koruması).
        upd = await db.shift_schedules.update_one(
            {
                'tenant_id': current_user.tenant_id,
                'id': req['shift_id'],
                'staff_id': req['from_staff_id'],
            },
            {'$set': {
                'staff_id': req['target_staff_id'],
                'staff_name': target.get('name'),
                'swapped_from': req['from_staff_id'],
                'swapped_at': datetime.now(UTC).isoformat(),
            }},
        )
        if upd.matched_count == 0:
            raise HTTPException(
                status_code=409,
                detail="Vardiya bu sürede değişti veya silindi — talebi yeniden değerlendirin",
            )
        new_status = 'approved'
    else:
        new_status = 'rejected'

    await db.shift_swap_requests.update_one(
        {'tenant_id': current_user.tenant_id, 'id': req_id},
        {'$set': {
            'status': new_status,
            'decision_note': payload.note,
            'decided_by': getattr(current_user, 'id', None),
            'decided_at': datetime.now(UTC).isoformat(),
        }},
    )
    if req.get('requested_by'):
        await _notify_user(
            current_user.tenant_id, user_id=req['requested_by'],
            kind=f'shift_swap_{new_status}',
            title=f"Vardiya değişimi {('onaylandı' if new_status == 'approved' else 'reddedildi')}",
            body=f"{req.get('shift_date')} {req.get('shift_type')} — " + (payload.note or ''),
            ref_id=req_id,
        )
    return {'success': True, 'status': new_status}


# ============= 3. Maaş Geçmişi / Zam Kaydı =============

class SalaryChangePayload(BaseModel):
    new_hourly_rate: float = Field(..., gt=0, le=100000)
    effective_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    change_type: Literal['raise', 'promotion', 'correction', 'demotion'] = 'raise'
    reason: str | None = Field(None, max_length=500)


@router.post("/hr/staff/{staff_id}/salary-change")
async def create_salary_change(
    staff_id: str,
    payload: SalaryChangePayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    staff = await _verify_staff_in_tenant(staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    old_rate = float(staff.get('hourly_rate') or TR_DEFAULT_HOURLY_RATE)
    delta_pct = round(((payload.new_hourly_rate - old_rate) / old_rate) * 100, 2) if old_rate else 0
    record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'staff_name': staff.get('name'),
        'old_hourly_rate': old_rate,
        'new_hourly_rate': payload.new_hourly_rate,
        'delta_pct': delta_pct,
        'effective_date': payload.effective_date,
        'change_type': payload.change_type,
        'reason': payload.reason,
        'created_by': getattr(current_user, 'id', None),
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.salary_history.insert_one(record)
    # Aktüel ücreti güncelle (basit yaklaşım: effective_date geçmişse hemen uygula)
    if payload.effective_date <= _today_local().isoformat():
        await db.staff_members.update_one(
            {'tenant_id': current_user.tenant_id, 'id': staff_id},
            {'$set': {
                'hourly_rate': payload.new_hourly_rate,
                'updated_at': datetime.now(UTC).isoformat(),
            }},
        )
    record.pop('_id', None)
    return {'success': True, 'record': record, 'applied_now': payload.effective_date <= _today_local().isoformat()}


@router.get("/hr/staff/{staff_id}/salary-history")
async def list_salary_history(
    staff_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    items = await db.salary_history.find({
        'tenant_id': current_user.tenant_id, 'staff_id': staff_id,
    }, {'_id': 0}).sort('effective_date', -1).to_list(500)
    return {'items': items, 'total': len(items)}


# ============= 4. İşten Ayrılma Süreci =============

class TerminationPayload(BaseModel):
    reason: Literal['resign', 'dismiss', 'mutual', 'retire', 'end_of_contract', 'death']
    last_day: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    notice_period_days: int = Field(0, ge=0, le=180)
    exit_interview_notes: str | None = Field(None, max_length=4000)
    severance_override: float | None = Field(None, ge=0, le=10_000_000)
    eligible_for_rehire: bool = True


def _calc_severance_tr(
    hire_date_str: str | None,
    last_day_str: str,
    monthly_gross: float,
    daily_cap: float | None = None,
) -> dict:
    """Türk İş K. m.14: kıdem tazminatı = 30 günlük brüt × tam yıl + orantılı.

    `daily_cap` parametresi yasal tavanı (2026 H1 için ~1.797,32 TL/gün)
    uygular. Çalışanın günlük brüt ücreti tavanı aşıyorsa hesap tavandan
    yapılır. Bu sayede yüksek maaşlı pozisyonlarda şişirilmiş tazminat
    çıkmaz. İhbar tazminatı + birikmiş izin alacağı ayrı hesaplanır.
    """
    if not hire_date_str:
        return {'years_of_service': 0, 'severance_amount': 0, 'note': 'İşe başlama tarihi yok'}
    try:
        hire = date.fromisoformat(hire_date_str)
        last = date.fromisoformat(last_day_str)
    except ValueError:
        return {'years_of_service': 0, 'severance_amount': 0, 'note': 'Geçersiz tarih'}
    days = (last - hire).days
    if days < 365:
        return {
            'years_of_service': round(days / 365, 2),
            'severance_amount': 0,
            'note': '1 yıldan az kıdem — kıdem tazminatına hak kazanılmaz',
        }
    years = days / 365.0
    raw_daily = monthly_gross / 30.0
    cap = daily_cap if (daily_cap is not None and daily_cap > 0) else TR_SEVERANCE_DAILY_CAP_DEFAULT
    capped = raw_daily > cap
    daily_gross = min(raw_daily, cap)
    severance = round(years * SEVERANCE_DAYS_PER_YEAR * daily_gross, 2)
    note = f'{years:.2f} yıl × 30 gün × {daily_gross:.2f} TL/gün'
    if capped:
        note += f' (yasal tavan uygulandı; ham günlük: {raw_daily:.2f} TL)'
    return {
        'years_of_service': round(years, 2),
        'daily_gross': round(daily_gross, 2),
        'raw_daily_gross': round(raw_daily, 2),
        'daily_cap_applied': capped,
        'daily_cap': round(cap, 2),
        'severance_amount': severance,
        'note': note,
    }


@router.post("/hr/staff/{staff_id}/terminate")
async def terminate_staff(
    staff_id: str,
    payload: TerminationPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    staff = await _verify_staff_in_tenant(staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    if staff.get('terminated_at'):
        raise HTTPException(status_code=400, detail="Personel zaten ayrılmış")

    monthly_hours = float(staff.get('monthly_hours') or TR_DEFAULT_MONTHLY_HOURS)
    hourly_rate = float(staff.get('hourly_rate') or TR_DEFAULT_HOURLY_RATE)
    monthly_gross = monthly_hours * hourly_rate

    # Tenant'a özel kıdem tavan override'ı (settings.severance_daily_cap) — yoksa default.
    tenant_settings = await db.tenant_settings.find_one(
        {'tenant_id': current_user.tenant_id}, {'_id': 0, 'severance_daily_cap': 1},
    ) or {}
    severance_calc = _calc_severance_tr(
        staff.get('hire_date'), payload.last_day, monthly_gross,
        daily_cap=tenant_settings.get('severance_daily_cap'),
    )
    final_severance = (
        payload.severance_override
        if payload.severance_override is not None
        else severance_calc['severance_amount']
    )

    record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'staff_name': staff.get('name'),
        'reason': payload.reason,
        'last_day': payload.last_day,
        'notice_period_days': payload.notice_period_days,
        'exit_interview_notes': payload.exit_interview_notes,
        'monthly_gross_at_exit': round(monthly_gross, 2),
        'severance_calc': severance_calc,
        'severance_paid': final_severance,
        'eligible_for_rehire': payload.eligible_for_rehire,
        'processed_by': getattr(current_user, 'id', None),
        'processed_at': datetime.now(UTC).isoformat(),
    }
    await db.staff_terminations.insert_one(record)

    await db.staff_members.update_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id},
        {'$set': {
            'active': False,
            'terminated_at': datetime.now(UTC).isoformat(),
            'termination_reason': payload.reason,
            'last_day': payload.last_day,
        }},
    )
    record.pop('_id', None)
    return {'success': True, 'termination': record}


@router.get("/hr/staff/{staff_id}/termination")
async def get_termination_record(
    staff_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    rec = await db.staff_terminations.find_one(
        {'tenant_id': current_user.tenant_id, 'staff_id': staff_id},
        {'_id': 0},
        sort=[('processed_at', -1)],
    )
    return {'record': rec}


# ============= 5. Eğitim/Sertifika Takibi =============

class CertificationPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    issuer: str | None = Field(None, max_length=200)
    issue_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    expiry_date: str | None = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    certificate_no: str | None = Field(None, max_length=100)
    file_url: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=1000)


@router.post("/hr/staff/{staff_id}/certifications")
async def add_certification(
    staff_id: str,
    payload: CertificationPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    staff = await _verify_staff_in_tenant(staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'staff_name': staff.get('name'),
        'name': payload.name,
        'issuer': payload.issuer,
        'issue_date': payload.issue_date,
        'expiry_date': payload.expiry_date,
        'certificate_no': payload.certificate_no,
        'file_url': payload.file_url,
        'notes': payload.notes,
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.staff_certifications.insert_one(item)
    item.pop('_id', None)
    return {'success': True, 'certification': item}


@router.get("/hr/staff/{staff_id}/certifications")
async def list_staff_certifications(
    staff_id: str,
    current_user: User = Depends(get_current_user),
):
    items = await db.staff_certifications.find({
        'tenant_id': current_user.tenant_id, 'staff_id': staff_id,
    }, {'_id': 0}).sort('issue_date', -1).to_list(500)
    today = _today_local().isoformat()
    expiring = sum(1 for it in items if it.get('expiry_date') and it['expiry_date'] >= today)
    expired = sum(1 for it in items if it.get('expiry_date') and it['expiry_date'] < today)
    return {'items': items, 'total': len(items), 'active': expiring, 'expired': expired}


@router.delete("/hr/certifications/{cert_id}")
async def delete_certification(
    cert_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.staff_certifications.delete_one({
        'tenant_id': current_user.tenant_id, 'id': cert_id,
    })
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sertifika bulunamadı")
    return {'success': True}


@router.get("/hr/certifications/expiring")
async def list_expiring_certifications(
    days_ahead: int = Query(90, ge=1, le=365),
    current_user: User = Depends(get_current_user),
):
    """Önümüzdeki N gün içinde süresi dolan sertifikalar (compliance dashboard)."""
    today = _today_local()
    end = (today + timedelta(days=days_ahead)).isoformat()
    items = await db.staff_certifications.find({
        'tenant_id': current_user.tenant_id,
        'expiry_date': {'$gte': today.isoformat(), '$lte': end},
    }, {'_id': 0}).sort('expiry_date', 1).to_list(500)
    return {'items': items, 'total': len(items), 'window_days': days_ahead}


# ============= 6. Personel Belgeleri (PDF/sözleşme yükleme) =============

ALLOWED_DOC_TYPES = {'contract', 'id', 'diploma', 'health', 'insurance', 'tax', 'other'}
ALLOWED_DOC_MIME = {
    'application/pdf', 'image/png', 'image/jpeg', 'image/webp',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}


@router.post("/hr/staff/{staff_id}/documents")
async def upload_staff_document(
    staff_id: str,
    file: UploadFile = File(...),
    doc_type: str = Query('other', max_length=20),
    label: str = Query('', max_length=200),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    staff = await _verify_staff_in_tenant(staff_id, current_user.tenant_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Geçersiz belge türü. İzinli: {sorted(ALLOWED_DOC_TYPES)}")
    if file.content_type not in ALLOWED_DOC_MIME:
        raise HTTPException(status_code=400, detail=f"Geçersiz dosya türü: {file.content_type}")

    content = await file.read()
    if len(content) > DOC_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Dosya çok büyük (>5MB)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Boş dosya")

    # GridFS'e yaz — büyük dosyalar memory'de tutulmaz, koleksiyon liste sorguları hızlı kalır.
    gridfs_id = await _hr_docs_bucket.upload_from_stream(
        file.filename or 'document',
        content,
        metadata={
            'tenant_id': current_user.tenant_id,
            'staff_id': staff_id,
            'doc_type': doc_type,
            'content_type': file.content_type,
        },
    )
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_id,
        'staff_name': staff.get('name'),
        'doc_type': doc_type,
        'label': label or file.filename or 'Belge',
        'filename': file.filename,
        'content_type': file.content_type,
        'size_bytes': len(content),
        'gridfs_id': str(gridfs_id),
        'storage': 'gridfs',
        'uploaded_by': getattr(current_user, 'id', None),
        'uploaded_at': datetime.now(UTC).isoformat(),
    }
    await db.staff_documents.insert_one(item)
    response = {k: v for k, v in item.items() if k != '_id'}
    return {'success': True, 'document': response}


@router.get("/hr/staff/{staff_id}/documents")
async def list_staff_documents(
    staff_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    items = await db.staff_documents.find(
        {'tenant_id': current_user.tenant_id, 'staff_id': staff_id},
        {'_id': 0, 'data_b64': 0},  # Legacy binary alanı liste yanıtında olmasın
    ).sort('uploaded_at', -1).to_list(500)
    return {'items': items, 'total': len(items)}


@router.get("/hr/documents/{doc_id}/download")
async def download_staff_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    doc = await db.staff_documents.find_one({
        'tenant_id': current_user.tenant_id, 'id': doc_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Belge bulunamadı")

    # GridFS'ten oku; eski (data_b64) kayıtlar için geriye dönük destek.
    if doc.get('gridfs_id'):
        try:
            gridfs_oid = ObjectId(doc['gridfs_id'])
        except Exception:
            raise HTTPException(status_code=404, detail="Belge depolamada bulunamadı")
        # Defense-in-depth: GridFS bucket tenant-aware proxy bypass'lı (_raw_db) olduğundan
        # metadata.tenant_id'yi tekrar doğrula. Meta kaydı zaten scoped ama belge bütünlüğü
        # için cross-check yapıyoruz.
        gf_meta = await _hr_docs_bucket.find({
            '_id': gridfs_oid,
            'metadata.tenant_id': current_user.tenant_id,
        }).to_list(1)
        if not gf_meta:
            raise HTTPException(status_code=404, detail="Belge depolamada bulunamadı")
        try:
            stream = await _hr_docs_bucket.open_download_stream(gridfs_oid)
            raw = await stream.read()
        except Exception:
            raise HTTPException(status_code=404, detail="Belge depolamada bulunamadı")
    elif doc.get('data_b64'):
        raw = base64.b64decode(doc['data_b64'])
    else:
        raise HTTPException(status_code=410, detail="Belge içeriği yok")

    headers = {
        'Content-Disposition': f'attachment; filename="{doc.get("filename", doc_id)}"',
        'Content-Length': str(len(raw)),
    }
    return StreamingResponse(
        iter([raw]),
        media_type=doc.get('content_type', 'application/octet-stream'),
        headers=headers,
    )


@router.delete("/hr/documents/{doc_id}")
async def delete_staff_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    doc = await db.staff_documents.find_one({
        'tenant_id': current_user.tenant_id, 'id': doc_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Belge bulunamadı")
    # Önce GridFS chunk'larını temizle (varsa); sonra meta kaydını sil.
    if doc.get('gridfs_id'):
        try:
            await _hr_docs_bucket.delete(ObjectId(doc['gridfs_id']))
        except Exception:
            pass  # Çoktan silinmiş olabilir — meta silmeyi engellemesin.
    await db.staff_documents.delete_one({
        'tenant_id': current_user.tenant_id, 'id': doc_id,
    })
    return {'success': True}


# ============= 6b. Kıdem Tazminatı Tavanı Ayarı =============

class SeveranceCapPayload(BaseModel):
    daily_cap: float = Field(..., gt=0, le=100000, description="Günlük brüt tavanı TL")


@router.get("/hr/settings/severance-cap")
async def get_severance_cap(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    s = await db.tenant_settings.find_one(
        {'tenant_id': current_user.tenant_id}, {'_id': 0, 'severance_daily_cap': 1, 'severance_cap_updated_at': 1},
    ) or {}
    return {
        'daily_cap': s.get('severance_daily_cap') or TR_SEVERANCE_DAILY_CAP_DEFAULT,
        'is_default': not s.get('severance_daily_cap'),
        'updated_at': s.get('severance_cap_updated_at'),
        'monthly_cap_estimate': round((s.get('severance_daily_cap') or TR_SEVERANCE_DAILY_CAP_DEFAULT) * 30, 2),
        'note': "Hazine yarıyıl açıklamasıyla (Ocak/Temmuz) güncellenmeli. Boş bırakılırsa default tavan uygulanır.",
    }


@router.put("/hr/settings/severance-cap")
async def set_severance_cap(
    payload: SeveranceCapPayload,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    await db.tenant_settings.update_one(
        {'tenant_id': current_user.tenant_id},
        {'$set': {
            'severance_daily_cap': payload.daily_cap,
            'severance_cap_updated_at': datetime.now(UTC).isoformat(),
            'severance_cap_updated_by': getattr(current_user, 'id', None),
        }},
        upsert=True,
    )
    return {'success': True, 'daily_cap': payload.daily_cap}


# ============= 7. Performans Hedef Check-in =============

class GoalCheckinPayload(BaseModel):
    goal_text: str = Field(..., min_length=1, max_length=1000)
    progress_pct: int = Field(..., ge=0, le=100)
    status: Literal['on_track', 'at_risk', 'blocked', 'done'] = 'on_track'
    note: str | None = Field(None, max_length=2000)
    checkin_date: str | None = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')


@router.post("/hr/performance/{review_id}/checkin")
async def add_goal_checkin(
    review_id: str,
    payload: GoalCheckinPayload,
    current_user: User = Depends(get_current_user),
):
    review = await db.performance_reviews.find_one({
        'tenant_id': current_user.tenant_id, 'id': review_id,
    })
    if not review:
        raise HTTPException(status_code=404, detail="Performans değerlendirmesi bulunamadı")
    item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'review_id': review_id,
        'staff_id': review.get('staff_id'),
        'goal_text': payload.goal_text,
        'progress_pct': payload.progress_pct,
        'status': payload.status,
        'note': payload.note,
        'checkin_date': payload.checkin_date or _today_local().isoformat(),
        'created_by': getattr(current_user, 'id', None),
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.performance_checkins.insert_one(item)
    item.pop('_id', None)
    return {'success': True, 'checkin': item}


@router.get("/hr/performance/{review_id}/checkins")
async def list_goal_checkins(
    review_id: str,
    current_user: User = Depends(get_current_user),
):
    items = await db.performance_checkins.find({
        'tenant_id': current_user.tenant_id, 'review_id': review_id,
    }, {'_id': 0}).sort('checkin_date', -1).to_list(500)
    return {'items': items, 'total': len(items)}


@router.delete("/hr/performance/checkins/{checkin_id}")
async def delete_goal_checkin(
    checkin_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    res = await db.performance_checkins.delete_one({
        'tenant_id': current_user.tenant_id, 'id': checkin_id,
    })
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Check-in bulunamadı")
    return {'success': True}
