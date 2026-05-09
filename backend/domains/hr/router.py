"""
Domain Router: HR Operations

HR complete suite, F&B complete suite for department managers.

Türk İş Kanunu uyumlu defaultlar (2026):
  - Aylık standart saat: 195 (45 sa/hf × 4.33)
  - Saatlik brüt asgari taban: 140 TL (yaklaşık 2026 asgari ücret)
  - Fazla mesai zammı: %50 (overtime_rate = hourly_rate * 1.5)
  - Para birimi: TRY
"""
import io
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from core.database import db
from core.security import get_current_user
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


class JobPostingPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    department: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=5000)
    employment_type: Literal['full_time', 'part_time', 'seasonal', 'intern', 'contract'] = 'full_time'
    location: str | None = Field(None, max_length=200)
    salary_range: str | None = Field(None, max_length=100)


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
    return {'success': True, 'status': new_status}


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
    _perm=Depends(require_op("view_executive_reports")),  # HR yönetici yetkisi (manage_sales semantik olarak yanlıştı)
):
    job = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': payload.title,
        'department': payload.department,
        'description': payload.description,
        'employment_type': payload.employment_type,
        'location': payload.location,
        'salary_range': payload.salary_range,
        'status': 'active',
        'applicants_count': 0,
        'created_by': getattr(current_user, 'id', None),
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.job_postings.insert_one(job)
    return {'success': True, 'job_id': job['id']}


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


# ============= Staff CRUD (PUT/DELETE/profile) =============
# NOT: POST /hr/staff `domains/pms/misc/hr.py` içinde mevcut.

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
    existing = await db.staff_members.find_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id}
    )
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Personel bulunamadı (yalnızca HR-managed personel düzenlenebilir)"
        )
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
    return {'success': True, 'updated_fields': len(update) - 1}


@router.delete("/hr/staff/{staff_id}")
async def delete_staff_member(
    staff_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Soft delete (active=False)."""
    res = await db.staff_members.update_one(
        {'tenant_id': current_user.tenant_id, 'id': staff_id},
        {'$set': {
            'active': False,
            'deactivated_at': datetime.now(UTC).isoformat(),
        }}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Personel bulunamadı")
    return {'success': True}


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
):
    job = await db.job_postings.find_one(
        {'tenant_id': current_user.tenant_id, 'id': job_id}
    )
    if not job:
        raise HTTPException(status_code=404, detail="İş ilanı bulunamadı")
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
