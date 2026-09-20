"""Tenant-user workspace policy; never replaces operation/object/plan guards."""
import json
from pathlib import Path

from fastapi import HTTPException

from models.enums import UserRole

CATALOG = json.loads(Path(__file__).with_name("user_access_catalog.json").read_text())
PAGES = {page["key"]: page for page in CATALOG["pages"]}
# Administrative powers and destructive accounting operations cannot be delegated
# via a page toggle. They retain their dedicated role/operation guards.
DELEGABLE_PERMISSIONS = frozenset({
    "view_bookings", "create_booking", "edit_booking", "checkin", "checkout",
    "view_folio", "post_charge", "post_payment", "view_companies",
    "view_hk_board", "update_room_status", "assign_task", "view_reports",
    "view_financial_reports", "run_night_audit", "view_hr", "view_procurement",
    "view_contact_center", "manage_contact_center", "send_urgent_message",
})


def effective_permissions(user):
    from modules.pms_core.role_permission_service import RolePermissionService

    role = getattr(user.role, "value", user.role)
    return sorted(set(RolePermissionService().get_user_permissions(role))
                  | set(user.granted_permissions or []))


def can_access_page(user, key):
    from modules.pms_core.module_scope_service import has_module_scope

    if user.role == UserRole.SUPER_ADMIN:
        return True
    page = PAGES.get(key)
    if not page or not has_module_scope(user, page["module"]):
        return False
    if getattr(user, "page_access", {}).get(key) is False:
        return False
    # A visibility grant is never an operation-permission bypass.
    permissions = set(effective_permissions(user))
    return set(page["permissions"]).issubset(permissions) and (
        not page.get("any_permissions") or bool(permissions.intersection(page["any_permissions"])))


def enforce_request_access(user, path, method):
    """Apply resource policy to authenticated requests (including cached routes).

    Public/provider callbacks do not use get_current_user, so this guard does
    not interfere with integrations. Shared PMS resources are available to any
    authorised consuming page, rather than trusting a client-supplied page name.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return
    path = path.rstrip("/")
    if path in {"/api/night-audit/business-date", "/api/pms-core/night-audit/business-date"}:
        return  # Existing VIEW_BOOKINGS check is the authority for this metadata.
    if method == "GET" and path.startswith("/api/hr/staff/") and path.endswith("/profile"):
        return  # Existing object-level self-service/department guard.
    shared = {
        "/api/pms/rooms": ("rooms", "calendar", "bookings", "frontdesk", "housekeeping"),
        "/api/pms/room-blocks": ("rooms", "calendar", "housekeeping"),
        "/api/pms/bookings": ("bookings", "calendar", "frontdesk", "cashier", "reports"),
        "/api/pms/guests": ("guests", "bookings", "calendar", "frontdesk"),
        "/api/folio": ("cashier", "invoice"),
        "/api/folios": ("cashier", "invoice"),
        "/api/pms/folios": ("cashier", "invoice"),
    }
    for prefix, pages in sorted(shared.items(), key=lambda pair: -len(pair[0])):
        if path == prefix or path.startswith(prefix + "/"):
            if not any(can_access_page(user, key) for key in pages):
                raise HTTPException(403, "PAGE_ACCESS_DENIED")
            return
    matches = [(prefix, page["key"]) for page in PAGES.values()
               for prefix in page["api_prefixes"]
               if path == prefix or path.startswith(prefix + "/")]
    if matches and not can_access_page(user, max(matches, key=lambda match: len(match[0]))[1]):
        raise HTTPException(403, "PAGE_ACCESS_DENIED")


def role_access_matrix():
    from modules.pms_core.module_scope_service import ROLE_DEFAULT_MODULE_SCOPES
    from modules.pms_core.role_permission_service import RolePermissionService

    return [{
        "role": role.value,
        "modules": ["*"] if role == UserRole.SUPER_ADMIN else sorted(ROLE_DEFAULT_MODULE_SCOPES.get(role.value, [])),
        "permissions": sorted(RolePermissionService().get_user_permissions(role.value)),
    } for role in UserRole]
