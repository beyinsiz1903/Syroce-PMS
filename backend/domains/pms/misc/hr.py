"""Auto-split from misc_router.py — backward-compatible sub-router."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

from ._common import (
    _scrub_encrypted,
)

logger = logging.getLogger(__name__)

sub_router = APIRouter()

@sub_router.post("/hr/staff")
async def add_staff_member(staff_data: dict, current_user: User = Depends(get_current_user),
    # Bug DAK round-7: "view_system_diagnostics" semantik olarak yanlıştı —
    # personel ekleme HR yönetici işidir, sistem tanılaması değil.
    _perm=Depends(require_op("view_executive_reports")),
):
    """Yeni personel ekle"""
    staff = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': staff_data['name'],
        'email': staff_data['email'],
        'phone': staff_data['phone'],
        'department': staff_data['department'],
        'position': staff_data['position'],
        'hire_date': staff_data['hire_date'],
        'employment_type': staff_data.get('employment_type', 'full_time'),
        'performance_score': 0.0,
        'active': True,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.staff_members.insert_one(staff)
    return {'success': True, 'staff_id': staff['id']}



@sub_router.get("/hr/staff")
async def get_staff_list(
    department: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v95.5 KVKK — HR PII koruması (round-7: view_system_diagnostics yerine)
):
    """Personel listesi.

    v95.5 — Önce `staff_members` koleksiyonundan açıkça eklenen kayıtları al.
    Çoğu tenant'ta bu koleksiyon boştur (POST /hr/staff henüz UI'dan çağrılmıyor),
    bu yüzden `users` tablosundan staff role'lerini (housekeeping, front_desk,
    supervisor, finance, sales, admin) türeterek listeyi doldururuz.
    Email bazlı deduplikasyon + KVKK için yetki kısıtı + allow-list projection.
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

    # 1) Açıkça eklenmiş HR kayıtları
    explicit_query: dict = {'tenant_id': tid, 'active': True}
    if department:
        explicit_query['department'] = department
    explicit = await db.staff_members.find(explicit_query, {'_id': 0}).to_list(200)
    seen_emails = {(s.get('email') or '').lower() for s in explicit if s.get('email')}

    # 2) Users tablosundan türeyenler — ALLOW-LIST projection (deny-list yerine
    # güvenli; User modelinde `extra=allow` olduğu için yeni alanlar otomatik
    # sızmasın diye sadece görünür alanları seç).
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
        # Şifreli (aes256gcm:) email/phone UI'a ham gösterilmesin
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



@sub_router.post("/hr/shift")
async def create_shift(shift_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # round-7: HR yetkisi
):
    """Vardiya oluştur"""
    shift = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': shift_data['staff_id'],
        'shift_date': shift_data['shift_date'],
        'shift_type': shift_data['shift_type'],
        'start_time': shift_data['start_time'],
        'end_time': shift_data['end_time'],
        'status': 'scheduled',
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.shift_schedules.insert_one(shift)
    return {'success': True, 'shift_id': shift['id']}



@sub_router.get("/hr/performance/{staff_id}")
async def get_staff_performance(staff_id: str, current_user: User = Depends(get_current_user)):
    """Personel performansı"""
    reviews = await db.performance_reviews.find({
        'staff_id': staff_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('reviewed_at', -1).to_list(10)

    avg_score = sum([r.get('overall_score', 0) for r in reviews]) / len(reviews) if reviews else 0

    return {
        'staff_id': staff_id,
        'recent_reviews': reviews,
        'avg_performance_score': round(avg_score, 2),
        'total_reviews': len(reviews)
    }

