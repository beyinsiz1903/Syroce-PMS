"""
compliance

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.helpers import (
    require_super_admin_guard,
)
from core.security import (
    _is_super_admin,
    get_current_user,
)
from modules.pms_core.role_permission_service import require_op  # v90 DW

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


# ── GET /security/audit-logs ──
@router.get("/security/audit-logs")
async def get_security_audit_logs(
    days: int = 7,
    action: str | None = None,
    user_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get security audit logs.

    Audit trail entries (kullanıcı aksiyonları, geri alınan mesajlar,
    acil mesaj kayıtları, vb.) sadece tenant yöneticilerine açıktır;
    olağan kullanıcılar 403 alır. Bu kısıt hem `view_system_diagnostics`
    izniyle hem de açık rol kontrolüyle çift kapı olarak doğrulanır.
    """
    if not _is_super_admin(current_user) and current_user.role not in (
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=403,
            detail="Denetim kayıtlarını sadece yöneticiler görüntüleyebilir.",
        )

    start_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    query = {
        'tenant_id': current_user.tenant_id,
        'timestamp': {'$gte': start_date}
    }

    if action:
        query['action'] = action
    if user_id:
        query['user_id'] = user_id

    logs = await db.audit_logs.find(query, {'_id': 0}).sort('timestamp', -1).limit(100).to_list(100)

    return {
        'logs': logs,
        'count': len(logs),
        'date_range': f'Last {days} days'
    }
# ── GET /gdpr/data-requests ──
@router.get("/gdpr/data-requests")
async def get_gdpr_data_requests(
    status: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get GDPR data access/deletion requests - REAL DATA from database"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    requests_data = await db.gdpr_requests.find(query, {'_id': 0}).sort('created_at', -1).to_list(100)

    # Return real data (empty if none)
    return {
        'requests': requests_data,
        'count': len(requests_data),
        'pending': sum(1 for r in requests_data if r.get('status') == 'pending'),
        'completed': sum(1 for r in requests_data if r.get('status') == 'completed')
    }
# ── KVKK/GDPR guest anonymization (F8 § 66, Wave 3) ──
# Right-to-be-forgotten: irreversibly scrub a guest's PII while preserving the
# tenant-scoped record skeleton for financial/audit integrity. Gated behind a
# fail-closed feature flag — anonymization is destructive and must not be
# reachable until an operator explicitly enables it per deployment.
import os as _os

_GUEST_PII_FIELDS = (
    "full_name", "name", "first_name", "last_name", "email", "phone",
    "address", "passport_number", "id_number", "birth_date", "date_of_birth",
    "nationality", "gender", "contact_email", "contact_phone",
)


def guest_anonymization_enabled() -> bool:
    """Fail-closed: only true when ENABLE_GUEST_ANONYMIZATION is explicitly on."""
    return _os.environ.get("ENABLE_GUEST_ANONYMIZATION", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


@router.post("/gdpr/guests/{guest_id}/anonymize")
async def anonymize_guest(
    guest_id: str,
    current_user: User = Depends(get_current_user),
    _guard=Depends(require_super_admin_guard(not_found=False)),
):
    """KVKK/GDPR right-to-be-forgotten — irreversibly scrub guest PII.

    Tenant-scoped + super-admin only. Feature-flag gated (fail-closed): when
    ENABLE_GUEST_ANONYMIZATION is unset the route returns 503 so the
    destructive path stays inert until an operator opts in per deployment.
    """
    if not guest_anonymization_enabled():
        raise HTTPException(
            status_code=503,
            detail=(
                "Guest anonymization disabled "
                "(set ENABLE_GUEST_ANONYMIZATION=1 to enable)"
            ),
        )

    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    scrub = {f: None for f in _GUEST_PII_FIELDS}
    scrub["full_name"] = "ANONYMIZED"
    scrub["anonymized"] = True
    scrub["anonymized_at"] = datetime.now(UTC).isoformat()
    scrub["anonymized_by"] = getattr(current_user, "id", None)

    result = await db.guests.update_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id},
        {"$set": scrub},
    )
    await db.gdpr_requests.insert_one({
        "tenant_id": current_user.tenant_id,
        "guest_id": guest_id,
        "type": "anonymization",
        "status": "completed",
        "created_at": datetime.now(UTC).isoformat(),
        "requested_by": getattr(current_user, "id", None),
    })
    return {
        "ok": True,
        "guest_id": guest_id,
        "anonymized": result.modified_count > 0,
        "fields_scrubbed": len(_GUEST_PII_FIELDS),
    }


# ── GET /compliance/certifications ──
@router.get("/compliance/certifications")
async def get_compliance_certifications(current_user: User = Depends(get_current_user)):
    """Get compliance certifications - REAL DATA from database"""

    # Get from database
    certs = await db.certifications.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(10)

    # If no data, return empty
    return {
        'certifications': certs,
        'count': len(certs),
        'certified_count': sum(1 for c in certs if c.get('status') == 'certified'),
        'compliance_score': (sum(c.get('score', 0) for c in certs) / len(certs)) if certs else 0
    }
