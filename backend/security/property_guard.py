"""
Security — Property Guard
Enforces property-level access within multi-property tenants.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from core.database import db

logger = logging.getLogger(__name__)


class PropertyGuard:
    """Validates property-level access for multi-property tenants."""

    @staticmethod
    async def get_user_properties(user_id: str, tenant_id: str) -> List[str]:
        """Get list of property IDs a user has access to."""
        user = await db.users.find_one(
            {"id": user_id, "tenant_id": tenant_id},
            {"_id": 0, "property_ids": 1, "role": 1},
        )
        if not user:
            return []
        # Admin/super_admin have access to all properties
        if user.get("role") in ("admin", "super_admin"):
            props = await db.properties.find(
                {"tenant_id": tenant_id}, {"_id": 0, "id": 1}
            ).to_list(100)
            return [p["id"] for p in props]
        return user.get("property_ids", [])

    @staticmethod
    async def validate_property_access(
        user_id: str,
        tenant_id: str,
        property_id: str,
    ) -> Dict[str, Any]:
        """Check if a user has access to a specific property."""
        allowed = await PropertyGuard.get_user_properties(user_id, tenant_id)
        if not allowed:
            # Single-property tenant — access granted
            return {"allowed": True, "reason": "single_property_tenant"}
        if property_id in allowed:
            return {"allowed": True}
        logger.warning(
            f"Property guard: user {user_id} denied access to property {property_id}"
        )
        return {
            "allowed": False,
            "reason": f"User does not have access to property {property_id}",
        }


property_guard = PropertyGuard()
