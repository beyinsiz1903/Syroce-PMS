"""
leads

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
    PmsLiteLeadAdminUpdateRequest,
    PmsLiteLeadStatus,
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

# Public lead sources surfaced in the super-admin marketing inbox. All three
# admin lead endpoints (list / export / patch) share this allowlist so leads
# from the PMS-Lite landing page, the marketing contact form and the supplier
# application form land in one inbox. $in on the leading `source` field stays
# index-serviceable on the (source, <field>_lower) indexes.
PUBLIC_LEAD_SOURCES = ["pms_lite_landing", "marketing_contact", "supplier_application"]


# ── GET /admin/leads ──
@router.get("/admin/leads")
async def admin_list_pms_lite_leads(
    status: PmsLiteLeadStatus | None = None,
    q: str | None = None,
    follow_up: bool | None = False,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """List public marketing leads for super admin."""
    if not _is_super_admin(current_user) and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can access leads")

    query: dict[str, Any] = {"source": {"$in": PUBLIC_LEAD_SOURCES}}
    if status:
        query["status"] = status.value

    if q:
        # Index-serviceable anchored prefix search on `<field>_lower` companions
        # (backed by (source, <field>_lower) indexes — `leads` is a global,
        # super-admin-only collection keyed by `source`, not tenant_id),
        # replacing the un-indexable unanchored case-insensitive regex scan.
        from security.search_normalize import prefix_conditions

        conds = prefix_conditions(["contact.full_name", "contact.phone", "contact.email", "hotel.property_name", "hotel.location"], q)
        if conds:
            query["$or"] = conds

    def _parse_iso_dt(v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=UTC)
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except Exception:
            return None

    now = datetime.now(UTC)

    def _needs_follow_up(lead: dict[str, Any]) -> bool:
        s = lead.get("status", "new")
        if s not in {"new", "contacted", "qualified"}:
            return False
        created = _parse_iso_dt(lead.get("created_at"))
        last_contact = _parse_iso_dt(lead.get("last_contact_at"))
        if s == "new":
            return bool(created and (now - created).total_seconds() >= 3600)
        base = last_contact or created
        return bool(base and (now - base).total_seconds() > 24 * 3600)

    # Marketing leads dataset is small; fetch all matching to compute
    # accurate aggregates + correct follow_up filtering BEFORE pagination.
    # Hard cap (5000) prevents pathological loads while keeping aggregates honest.
    AGGREGATE_CAP = 5000
    all_docs: list[dict[str, Any]] = []
    async for lead in db.leads.find(query).sort("created_at", -1).limit(AGGREGATE_CAP):
        all_docs.append(lead)

    status_counts: dict[str, int] = {}
    follow_up_count = 0
    eligible: list[dict[str, Any]] = []
    for lead in all_docs:
        s_val = lead.get("status", PmsLiteLeadStatus.NEW.value)
        status_counts[s_val] = status_counts.get(s_val, 0) + 1
        is_followup = _needs_follow_up(lead)
        if is_followup:
            follow_up_count += 1
        if follow_up and not is_followup:
            continue
        eligible.append(lead)

    total = len(eligible)
    page = eligible[max(offset, 0) : max(offset, 0) + max(limit, 1)]

    leads: list[dict[str, Any]] = []
    for lead in page:
        leads.append(
            {
                "lead_id": lead.get("lead_id") or lead.get("id"),
                "created_at": lead.get("created_at"),
                "status": lead.get("status", PmsLiteLeadStatus.NEW.value),
                "note": lead.get("note"),
                "full_name": lead.get("contact", {}).get("full_name"),
                "phone": lead.get("contact", {}).get("phone"),
                "email": lead.get("contact", {}).get("email"),
                "property_name": lead.get("hotel", {}).get("property_name"),
                "location": lead.get("hotel", {}).get("location"),
                "rooms_count": lead.get("hotel", {}).get("rooms_count"),
                "last_contact_at": lead.get("last_contact_at"),
                "status_changed_at": lead.get("status_changed_at"),
                "source": lead.get("source"),
                "needs_follow_up": _needs_follow_up(lead),
            }
        )

    return {
        "leads": leads,
        "total": total,
        "count": len(leads),
        "status_counts": status_counts,
        "follow_up_count": follow_up_count,
    }


# ── GET /admin/leads/export.csv ──
@router.get("/admin/leads/export.csv")
async def admin_export_pms_lite_leads_csv(
    status: PmsLiteLeadStatus | None = None,
    q: str | None = None,
    follow_up: bool | None = False,
    current_user: User = Depends(get_current_user),
):
    """Export PMS Lite marketing leads as CSV for super admin."""
    if not _is_super_admin(current_user) and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can export leads")

    import csv
    from io import StringIO

    query: dict[str, Any] = {"source": {"$in": PUBLIC_LEAD_SOURCES}}
    if status:
        query["status"] = status.value

    if q:
        # Index-serviceable anchored prefix search on `<field>_lower` companions
        # (backed by (source, <field>_lower) indexes — `leads` is a global,
        # super-admin-only collection keyed by `source`, not tenant_id),
        # replacing the un-indexable unanchored case-insensitive regex scan.
        from security.search_normalize import prefix_conditions

        conds = prefix_conditions(["contact.full_name", "contact.phone", "contact.email", "hotel.property_name", "hotel.location"], q)
        if conds:
            query["$or"] = conds

    docs: list[dict[str, Any]] = []
    async for lead in db.leads.find(query):
        docs.append(lead)

    now = datetime.now(UTC)

    def _parse_iso_dt(v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=UTC)
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except Exception:
            return None

    if follow_up:
        filtered: list[dict[str, Any]] = []
        for lead in docs:
            s = lead.get("status", "new")
            created = _parse_iso_dt(lead.get("created_at"))
            last_contact = _parse_iso_dt(lead.get("last_contact_at"))

            if s not in {"new", "contacted", "qualified"}:
                continue

            if s == "new":
                if not created:
                    continue
                if (now - created).total_seconds() < 3600:
                    continue
                filtered.append(lead)
            else:
                cutoff = 24 * 3600
                base = last_contact or created
                if not base:
                    continue
                if (now - base).total_seconds() > cutoff:
                    filtered.append(lead)
        docs = filtered

    from core.csv_safe import safe_writerow  # Bug AN: defend against CSV formula injection

    output = StringIO()
    # BOM for Excel UTF-8
    output.write("\ufeff")
    writer = csv.writer(output)

    headers = [
        "created_at",
        "status",
        "full_name",
        "phone",
        "email",
        "property_name",
        "location",
        "rooms_count",
        "lead_id",
        "note",
        "last_contact_at",
        "status_changed_at",
        "source",
    ]
    safe_writerow(writer, headers)

    for lead in docs:
        contact = lead.get("contact", {})
        hotel = lead.get("hotel", {})
        row = [
            lead.get("created_at") or "",
            lead.get("status") or "",
            contact.get("full_name") or "",
            contact.get("phone") or "",
            contact.get("email") or "",
            hotel.get("property_name") or "",
            hotel.get("location") or "",
            hotel.get("rooms_count") or "",
            lead.get("lead_id") or lead.get("id") or "",
            lead.get("note") or "",
            lead.get("last_contact_at") or "",
            lead.get("status_changed_at") or "",
            lead.get("source") or "",
        ]
        safe_writerow(writer, row)

    csv_content = output.getvalue()
    from fastapi.responses import Response

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="pms-lite-leads.csv"',
        },
    )


# ── PATCH /admin/leads/{lead_id} ──
@router.patch("/admin/leads/{lead_id}")
async def admin_update_pms_lite_lead(
    lead_id: str,
    payload: PmsLiteLeadAdminUpdateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Update status/note of a PMS Lite marketing lead (super_admin only)."""
    if not _is_super_admin(current_user) and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can update leads")

    update: dict[str, Any] = {}
    if payload.status is not None:
        update["status"] = payload.status.value
    if payload.note is not None:
        update["note"] = payload.note

    if not update:
        return {"ok": True}

    result = await db.leads.update_one({"lead_id": lead_id, "source": {"$in": PUBLIC_LEAD_SOURCES}}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {"ok": True, "lead_id": lead_id}
