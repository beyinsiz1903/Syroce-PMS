"""
Ops Admin Guard — Role-based access control for /api/ops/* endpoints.

Protects operational endpoints with admin/operator role verification.
Only users with 'super_admin', 'admin', 'operator', or 'manager' roles can access.

Usage:
  from security.ops_guard import require_ops_access
  router = APIRouter(dependencies=[Depends(require_ops_access)])
"""

import logging

from fastapi import Depends, HTTPException

from core.security import _is_super_admin, get_current_user
from models.schemas import User

logger = logging.getLogger("security.ops_guard")

ALLOWED_OPS_ROLES = {"super_admin", "admin", "operator", "manager"}


async def require_ops_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """Verify the user has ops-level access.

    Returns the user if authorized, raises 403 otherwise.
    """
    # Super admin bypass — covers role + roles[] representations.
    if _is_super_admin(current_user):
        return current_user

    user_role = getattr(current_user, "role", "")
    # Also check string representation for enum roles
    role_str = str(user_role).lower().replace("userrole.", "")

    # Honor `roles[]` (list of role strings) in addition to the primary `role`.
    extra_roles = getattr(current_user, "roles", None) or []
    extra_role_strs = {str(r).lower().replace("userrole.", "") for r in extra_roles if r is not None} if isinstance(extra_roles, list) else set()

    if role_str not in ALLOWED_OPS_ROLES and not (extra_role_strs & ALLOWED_OPS_ROLES):
        logger.warning(
            "OPS_GUARD: Access denied for user=%s role=%s",
            getattr(current_user, "id", "?"),
            role_str,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient privileges. Required roles: {', '.join(sorted(ALLOWED_OPS_ROLES))}",
        )

    return current_user
