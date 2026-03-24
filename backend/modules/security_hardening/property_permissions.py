"""
Property-Scoped Permissions - RBAC enforcement at the property level.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db

logger = logging.getLogger("security.property_permissions")


PROPERTY_PERMISSIONS = {
    "super_admin": ["*"],
    "admin": ["read", "write", "manage", "configure", "report"],
    "front_desk": ["read", "write", "checkin", "checkout"],
    "housekeeping": ["read", "update_room_status", "view_tasks"],
    "revenue": ["read", "rate_management", "forecasting", "autopilot"],
    "finance": ["read", "folio_management", "invoicing", "reporting"],
    "maintenance": ["read", "work_orders", "asset_management"],
    "guest_services": ["read", "guest_requests", "messaging"],
}


class PropertyPermissionService:
    """Enforces property-level RBAC for multi-property tenants."""

    async def check_permission(self, tenant_id: str, user_id: str, role: str,
                               property_id: str, action: str) -> Dict[str, Any]:
        """Check if a user has permission for an action on a property."""
        allowed_actions = PROPERTY_PERMISSIONS.get(role, [])
        has_permission = "*" in allowed_actions or action in allowed_actions

        # Check property assignment
        user = await db.users.find_one(
            {"$or": [{"id": user_id}, {"user_id": user_id}], "tenant_id": tenant_id},
            {"_id": 0},
        )

        property_assigned = True
        if user:
            assigned_properties = user.get("property_ids", [])
            if assigned_properties and property_id not in assigned_properties:
                property_assigned = False
                has_permission = False

        result = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": role,
            "property_id": property_id,
            "action": action,
            "permitted": has_permission,
            "property_assigned": property_assigned,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        if not has_permission:
            logger.warning(
                f"Permission denied: user={user_id} role={role} "
                f"property={property_id} action={action}"
            )

        return result

    async def get_property_permissions(self, tenant_id: str,
                                       property_id: Optional[str] = None) -> Dict[str, Any]:
        """Get permission summary for properties."""
        q: Dict[str, Any] = {"tenant_id": tenant_id}
        users = await db.users.find(q, {"_id": 0}).to_list(500)

        property_users: Dict[str, list] = {}
        for u in users:
            role = u.get("role", "")
            if hasattr(role, "value"):
                role = role.value
            props = u.get("property_ids", [])
            if not props:
                props = ["all"]
            for pid in props:
                if property_id and pid != property_id and pid != "all":
                    continue
                property_users.setdefault(pid, []).append({
                    "user_id": u.get("id") or u.get("user_id"),
                    "name": u.get("name", ""),
                    "role": role,
                    "permissions": PROPERTY_PERMISSIONS.get(role, []),
                })

        return {
            "tenant_id": tenant_id,
            "properties": {
                pid: {
                    "user_count": len(u_list),
                    "users": u_list,
                    "roles": list({u.get("role", "") for u in u_list}),
                }
                for pid, u_list in property_users.items()
            },
            "available_roles": list(PROPERTY_PERMISSIONS.keys()),
        }

    def get_role_permissions(self) -> Dict[str, List[str]]:
        return dict(PROPERTY_PERMISSIONS)


property_permissions = PropertyPermissionService()
