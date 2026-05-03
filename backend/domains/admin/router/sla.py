"""
sla

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.helpers import (
    get_tenant_modules,
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
from domains.admin.property_profiles import get_all_property_types, get_hidden_nav_config, get_modules_for_property_type, get_property_profile, get_property_special_settings
from domains.admin.subscription_models import PLAN_MODULE_DEFAULTS, SUBSCRIPTION_PLANS, SubscriptionTier, get_all_module_keys, get_feature_comparison, get_plan_default_modules
from models.enums import ROLE_PERMISSIONS, Permission, UserRole
from models.schemas import Tenant, TenantRegister, UpdateUserRoleRequest, User


def _has_permission(role: UserRole | str, perm: Permission) -> bool:
    """Lightweight helper: ROLE_PERMISSIONS lookup."""
    role_key = role if isinstance(role, UserRole) else UserRole(role) if role in {r.value for r in UserRole} else None
    if role_key is None:
        return False
    perms = ROLE_PERMISSIONS.get(role_key, [])
    perm_value = perm.value if isinstance(perm, Permission) else perm
    return any((p.value if isinstance(p, Permission) else p) == perm_value for p in perms)
from security.encrypted_lookup import (
    build_user_email_query,
    decrypt_user_doc,
    encrypt_user_doc,
)

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
from core.security import hash_password
from domains.admin.schemas import (  # noqa: E402
    AdminCreateTeamMemberRequest,
    AdminUpdateTenantInfoRequest,
    ChangePlanRequest,
    CreateTeamMemberRequest,
    DemoRequest,
    PermissionCheckRequest,
    PmsLiteLeadAdminUpdateRequest,
    PmsLiteLeadStatus,
    SLAConfig,
    SubscriptionUpdateRequest,
    TenantModulesUpdate,
    UpdateGrantedPermissionsRequest,
    UpdateHotelInfoRequest,
    UpdateTeamMemberRoleRequest,
)




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

from demo_data_generator import DemoDataGenerator
















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

import time

import psutil

# api_metrics is now provided by apm_store from apm_middleware.py
# Backward compat: alias api_metrics to apm_store.requests
try:
    from apm_middleware import apm_store as _apm_store_ref
    from apm_middleware import get_rate_limit_stats as _get_rl_stats
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


# ── POST /settings/sla ──
@router.post("/settings/sla")
async def create_sla_config(
    config: SLAConfig,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v95 DW
):
    """
    Create or update SLA configuration for property
    """
    try:
        sla_id = str(uuid.uuid4())

        # Check if SLA exists for this category
        existing = await db.sla_configs.find_one({
            'tenant_id': current_user.tenant_id,
            'category': config.category,
            'priority': config.priority
        }, {'_id': 0})

        if existing:
            # Update existing
            await db.sla_configs.update_one(
                {
                    'tenant_id': current_user.tenant_id,
                    'category': config.category,
                    'priority': config.priority
                },
                {
                    '$set': {
                        'response_time_minutes': config.response_time_minutes,
                        'resolution_time_minutes': config.resolution_time_minutes,
                        'updated_at': datetime.now(UTC).isoformat(),
                        'updated_by': current_user.name
                    }
                }
            )
            sla_id = existing['id']
        else:
            # Create new
            await db.sla_configs.insert_one({
                'id': sla_id,
                'tenant_id': current_user.tenant_id,
                'category': config.category,
                'priority': config.priority,
                'response_time_minutes': config.response_time_minutes,
                'resolution_time_minutes': config.resolution_time_minutes,
                'created_at': datetime.now(UTC).isoformat(),
                'created_by': current_user.name
            })

        return {
            'message': 'SLA configuration saved',
            'sla_id': sla_id,
            'category': config.category,
            'priority': config.priority,
            'response_time': f'{config.response_time_minutes} min',
            'resolution_time': f'{config.resolution_time_minutes} min'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save SLA config: {str(e)}")
# ── GET /settings/sla ──
@router.get("/settings/sla")
async def get_sla_configs(
    current_user: User = Depends(get_current_user)
):
    """
    Get all SLA configurations
    """
    try:
        configs = await db.sla_configs.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(100)

        # If no configs, return defaults
        if not configs:
            configs = [
                {
                    'category': 'maintenance',
                    'priority': 'urgent',
                    'response_time_minutes': 30,
                    'resolution_time_minutes': 120
                },
                {
                    'category': 'housekeeping',
                    'priority': 'normal',
                    'response_time_minutes': 60,
                    'resolution_time_minutes': 180
                },
                {
                    'category': 'guest_request',
                    'priority': 'normal',
                    'response_time_minutes': 15,
                    'resolution_time_minutes': 60
                }
            ]

        return {
            'configs': configs,
            'count': len(configs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get SLA configs: {str(e)}")
