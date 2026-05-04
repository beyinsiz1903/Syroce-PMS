"""
ops

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.helpers import (
    require_super_admin_guard,
)
from core.security import (
    _is_super_admin,
)

try:
    from cache_manager import cache as _cache_mgr
    from cache_manager import cached as _cm_cached
except ImportError:
    _cache_mgr = None  # type: ignore
    def _cm_cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator


def _invalidate_admin_tenants_cache(tenant_id: str | None) -> None:
    """v95.3 — admin/tenants list cache'i temizle. Super-admin tenant_id ile
    set edilir; bu fonksiyon güvenli (hata fırlatmaz)."""
    if not _cache_mgr or not tenant_id:
        return
    try:
        _cache_mgr.invalidate_tenant_cache(tenant_id, "admin_tenants_list")
    except Exception:
        pass

require_super_admin = require_super_admin_guard()
from models.enums import ROLE_PERMISSIONS, Permission, UserRole
from models.schemas import User


def _has_permission(role: UserRole | str, perm: Permission) -> bool:
    """Lightweight helper: ROLE_PERMISSIONS lookup."""
    role_key = role if isinstance(role, UserRole) else UserRole(role) if role in {r.value for r in UserRole} else None
    if role_key is None:
        return False
    perms = ROLE_PERMISSIONS.get(role_key, [])
    perm_value = perm.value if isinstance(perm, Permission) else perm
    return any((p.value if isinstance(p, Permission) else p) == perm_value for p in perms)

logger = logging.getLogger(__name__)


def _svc_enc():
    try:
        from security.field_encryption import get_field_encryption_service
        return get_field_encryption_service()
    except Exception:
        return None

ROLES_BY_TIER = {
    "mini": ["admin", "front_desk", "housekeeping"],
    "basic": ["admin", "front_desk", "housekeeping"],
    "professional": ["admin", "front_desk", "housekeeping", "manager", "revenue", "night_audit", "finance", "procurement"],
    "enterprise": ["admin", "front_desk", "housekeeping", "manager", "revenue", "night_audit", "gm", "super_admin", "finance", "procurement", "supervisor", "sales"],
}


def is_role_allowed_for_tier(role: str, tier: str) -> bool:
    allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
    return role in allowed


from core.audit import log_audit_event  # Task #28

# ============= CHANNEL MANAGER & RMS =============









# ============= MOBILE APP ENDPOINTS (STAFF & GUEST) =============
























# ── Task #28: Kullanıcı bazlı operasyon izinleri ──────────────────────
#
# Rol-bazlı RBAC dışında bazı operasyonlar (şu an yalnız acil mesaj
# gönderme) tek tek kullanıcılara verilip alınabilsin diye User modelinde
# `granted_permissions: list[str]` alanı tutuluyor. Endpoint'ler ADMIN ve
# SUPER_ADMIN'e açık. ADMIN sadece kendi tenant'ı içindeki kullanıcılara
# yazabilir; SUPER_ADMIN her tenant'a yazabilir.

# Whitelist: kötü niyetli/yanlış izin atamalarını önlemek için kabul
# edilen izinler dar tutulur.
GRANTABLE_PERMISSIONS: set[str] = {"send_urgent_message"}


def _require_admin_for_target_user(
    current_user: User, target_tenant_id: str | None,
):
    """ADMIN ve SUPER_ADMIN'e izin ver; ADMIN'in başka tenant'a yazmasını
    engelle. Diğer roller 403 alır."""
    if _is_super_admin(current_user):
        return
    role_value = getattr(current_user.role, "value", str(current_user.role))
    if role_value != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Yalnızca yöneticiler kullanıcı izinlerini düzenleyebilir.",
        )
    # ADMIN'in tenant_id'si target ile eşleşmeli.
    if not current_user.tenant_id or current_user.tenant_id != target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )








# ── Task #32: Web push gönderim metrikleri ────────────────────────────

















# ============= ADMIN TENANT INFO & TEAM MANAGEMENT =============
























# ============= BILLING HISTORY & PLAN MANAGEMENT =============
















# ============= HOTEL TEAM MANAGEMENT ENDPOINTS =============

















# ============= DEMO ENVIRONMENT ENDPOINTS =============

















# 6. GET /api/sales/follow-ups - Follow-up reminders








# ============================================================================
# COMPREHENSIVE FINANCE MODULE - CASH FLOW & RISK MANAGEMENT
# ============================================================================

# ============================================================================
# DELAYED TASKS MONITORING & PUSH NOTIFICATIONS
# ============================================================================

# MOVED: /tasks/delayed endpoint moved earlier to avoid path conflict with /tasks/{task_id}


# ============================================================================
# SYSTEM MONITORING & PERFORMANCE - APM INTEGRATED
# ============================================================================



# api_metrics is now provided by apm_store from apm_middleware.py
# Backward compat: alias api_metrics to apm_store.requests
try:
    from apm_middleware import apm_store as _apm_store_ref
    api_metrics = _apm_store_ref.requests
except ImportError:
    from collections import deque
    api_metrics = deque(maxlen=1000)

# Legacy APIMetricsMiddleware replaced by APMMiddleware in apm_middleware.py

# 1. SYSTEM PERFORMANCE MONITORING




# 1b. APM DETAILED ENDPOINT STATS




# 1c. RATE LIMIT STATUS




# 1d. DATABASE OPTIMIZATION STATUS




# 1e. RECENT ERRORS




# 2. LOG VIEWER




# 3. NETWORK PING TEST




# 4. ENDPOINT HEALTH CHECK




# ============================================================================
# OPERA CLOUD PARITY FEATURES - CRITICAL ENTERPRISE FUNCTIONALITY
# ============================================================================

# Import night audit models

# ============= 1. NIGHT AUDIT MODULE (ENTERPRISE GRADE) =============

# ============= 2. CASHIERING & CITY LEDGER MODULE =============

# ============= 3. QUEUE ROOMS MODULE (EARLY ARRIVAL MANAGEMENT) =============

# ============= AUDIT TRAIL LOGGING (AUTO-TRACKING) =============













# ──────────────────────────────────────────────────────────────────────────────
# v95.4 — Maintenance: Oda statüsü ↔ rezervasyon defteri sync
# UctanUcaTest 2026-05-02: dashboard "OCCUPANCY-DRIFT" uyarısı için kalıcı
# çözüm. KPI zaten booking ledger'ı kaynak alıyor, bu endpoint rooms.status
# tarafındaki tortu veriyi (eski non-atomic flow'lardan kalan) düzeltir.
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["Admin / Operations"])


# ── POST /admin/maintenance/sync-room-status ──
@router.post("/admin/maintenance/sync-room-status")
async def sync_room_status(
    dry_run: bool = True,
    current_user: User = Depends(require_super_admin),
):
    """Bookings ledger'ına göre rooms.status alanını yeniden hizala.

    Kural: bugünü kapsayan aktif booking (checked_in / confirmed&today) varsa
    ilgili oda 'occupied'; yoksa 'occupied' tortusu temizlenir.

    Parametre:
      dry_run=True (varsayılan) → sadece tespit, yazma yok.
      dry_run=False             → fiili güncelleme.

    Sadece SUPER_ADMIN. Tek tenant kapsamında çalışır.
    """
    tenant_id = current_user.tenant_id
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Aktif overlap booking'leri (date-only karşılaştırma — dashboard ile aynı)
    bookings = await db.bookings.find(
        {
            'tenant_id': tenant_id,
            'status': {'$in': ['checked_in', 'confirmed', 'guaranteed']},
        },
        {'_id': 0, 'room_id': 1, 'check_in': 1, 'check_out': 1, 'status': 1},
    ).to_list(10000)

    occupied_room_ids: set[str] = set()
    for b in bookings:
        rid = b.get('room_id')
        if not rid:
            continue
        ci = str(b.get('check_in', ''))[:10]
        co = str(b.get('check_out', ''))[:10]
        if ci <= today and co > today:
            occupied_room_ids.add(rid)

    rooms = await db.rooms.find(
        {'tenant_id': tenant_id},
        {'_id': 0, 'id': 1, 'room_number': 1, 'status': 1},
    ).to_list(5000)

    # Hedef statüler:
    #   - mark_occupied → 'occupied' (aktif booking var ama oda farklı statüde)
    #   - clear_occupied → 'dirty' (aktif booking yok ama oda 'occupied' tortusu)
    # 'dirty' tercih edildi çünkü atomic_checkin_checkout.checkout flow'u da
    # check-out sonrası odayı 'dirty' yapar; housekeeping zorunlu kontrolü
    # böylece atlanmaz. Doğrudan 'available' yapmak güvenli değil (önceki
    # konuğun durumunu temizleme garantisi yok).
    to_mark_occupied: list[dict[str, Any]] = []
    to_clear_occupied: list[dict[str, Any]] = []

    for r in rooms:
        rid = r.get('id')
        cur_status = r.get('status')
        if rid in occupied_room_ids:
            if cur_status != 'occupied':
                to_mark_occupied.append({
                    'id': rid,
                    'room_number': r.get('room_number'),
                    'old_status': cur_status,
                })
        else:
            if cur_status == 'occupied':
                to_clear_occupied.append({
                    'id': rid,
                    'room_number': r.get('room_number'),
                    'old_status': cur_status,
                })

    applied_occupied = 0
    applied_cleared = 0
    if not dry_run:
        for r in to_mark_occupied:
            res = await db.rooms.update_one(
                {'id': r['id'], 'tenant_id': tenant_id},
                {'$set': {'status': 'occupied', 'updated_at': datetime.now(UTC).isoformat()}},
            )
            if res.modified_count:
                applied_occupied += 1
        for r in to_clear_occupied:
            res = await db.rooms.update_one(
                {'id': r['id'], 'tenant_id': tenant_id},
                {'$set': {'status': 'dirty', 'current_booking_id': None,
                          'updated_at': datetime.now(UTC).isoformat()}},
            )
            if res.modified_count:
                applied_cleared += 1

        await log_audit_event(
            tenant_id=tenant_id,
            user_id=current_user.id,
            action='sync_room_status',
            entity_type='maintenance',
            entity_id='rooms',
            details=f"Oda statüsü senkronu: +{applied_occupied} occupied, -{applied_cleared} cleared",
            db=db,
        )

    return {
        'tenant_id': tenant_id,
        'dry_run': dry_run,
        'total_rooms': len(rooms),
        'active_bookings_today': len(occupied_room_ids),
        'drift_detected': {
            'should_be_occupied': len(to_mark_occupied),
            'should_be_freed': len(to_clear_occupied),
        },
        'preview': {
            'mark_occupied': to_mark_occupied[:20],
            'clear_occupied': to_clear_occupied[:20],
        },
        'applied': {
            'marked_occupied': applied_occupied,
            'cleared_occupied': applied_cleared,
        } if not dry_run else None,
        'message': (
            'Drift tespit edildi, dry_run=true. Uygulamak için ?dry_run=false gönderin.'
            if dry_run and (to_mark_occupied or to_clear_occupied)
            else 'Drift yok, oda statüsü hizalı.' if dry_run
            else f'Senkron tamamlandı: {applied_occupied} occupied + {applied_cleared} freed.'
        ),
    }
