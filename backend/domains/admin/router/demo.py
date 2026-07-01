"""
demo

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime

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


from domains.admin.schemas import (  # noqa: E402
    DemoRequest,
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
    current_user: User,
    target_tenant_id: str | None,
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


from demo_data_generator import DemoDataGenerator

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


# ── POST /demo/populate ──
@router.post("/demo/populate")
async def populate_demo_data(
    hotel_type: str = "boutique",  # boutique, resort, city
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Populate account with realistic demo data"""

    # Check if already has data
    existing_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    if existing_rooms > 10:
        raise HTTPException(status_code=400, detail="Account already has data. Cannot populate demo data.")

    # Generate demo data
    demo_data = DemoDataGenerator.generate_demo_hotel(current_user.tenant_id, hotel_type)

    # Insert demo data
    stats = {"rooms": 0, "guests": 0, "bookings": 0, "staff": 0, "inventory": 0}

    # Insert rooms
    if demo_data["rooms"]:
        await db.rooms.insert_many(demo_data["rooms"])
        stats["rooms"] = len(demo_data["rooms"])

    # Insert guests
    if demo_data["guests"]:
        await db.guests.insert_many(demo_data["guests"])
        stats["guests"] = len(demo_data["guests"])

    # Insert bookings
    if demo_data["bookings"]:
        await db.bookings.insert_many(demo_data["bookings"])
        stats["bookings"] = len(demo_data["bookings"])

    # Insert staff
    if demo_data["staff"]:
        # Note: Staff might need to be in users collection with passwords
        # For demo, we'll just store as reference data
        for staff in demo_data["staff"]:
            await db.staff_profiles.insert_one(staff)
        stats["staff"] = len(demo_data["staff"])

    # Insert inventory
    if demo_data["inventory"]:
        await db.inventory.insert_many(demo_data["inventory"])
        stats["inventory"] = len(demo_data["inventory"])

    return {"success": True, "message": "Demo data populated successfully", "hotel_name": demo_data["hotel_name"], "stats": stats}


# ── GET /demo/status ──
@router.get("/demo/status")
async def get_demo_status(current_user: User = Depends(get_current_user)):
    """Check if account is using demo data"""

    rooms_count = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    guests_count = await db.guests.count_documents({"tenant_id": current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id})

    is_demo = rooms_count > 0 and guests_count > 0

    return {"is_demo": is_demo, "has_data": rooms_count > 0, "stats": {"rooms": rooms_count, "guests": guests_count, "bookings": bookings_count}}


# ── POST /demo-requests ──
@router.post("/demo-requests")
async def create_demo_request(request: DemoRequest):
    """
    Create demo request from landing page
    Public endpoint - no authentication required
    """
    try:
        demo_data = {
            "id": str(uuid.uuid4()),
            "name": request.name,
            "email": request.email,
            "phone": request.phone,
            "hotel_name": request.hotel_name,
            "room_count": request.room_count,
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "contacted": False,
        }

        await db.demo_requests.insert_one(demo_data)

        return {"success": True, "message": "Demo request received successfully", "request_id": demo_data["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save demo request: {str(e)}")
