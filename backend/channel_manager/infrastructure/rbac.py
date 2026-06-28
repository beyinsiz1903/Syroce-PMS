"""
RBAC Enforcement — Phase 4: Role-Based Access Control for Credentials.

Allowed roles for credential operations:
  - tenant_owner
  - system_admin
  - integration_admin

Restricted roles (read-only or no access):
  - operator
  - staff
  - viewer

Unauthorized attempts are logged via audit trail.
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.infrastructure.rbac")

CREDENTIAL_ADMIN_ROLES = {"tenant_owner", "system_admin", "integration_admin", "admin", "super_admin"}
CREDENTIAL_VIEW_ROLES = CREDENTIAL_ADMIN_ROLES | {"operator"}
RESTRICTED_ROLES = {"staff", "viewer"}


async def enforce_credential_access(
    user,
    action: str,
    connector_id: str = "",
    repo: ChannelManagerRepository | None = None,
    require_write: bool = True,
) -> None:
    """
    Enforce RBAC for credential operations.
    Raises HTTPException(403) if the user lacks permissions.
    Logs unauthorized attempts.
    """
    user_role = getattr(user, "role", "viewer")
    tenant_id = getattr(user, "tenant_id", "")
    user_id = getattr(user, "id", "")

    allowed_roles = CREDENTIAL_ADMIN_ROLES if require_write else CREDENTIAL_VIEW_ROLES

    if user_role not in allowed_roles:
        logger.warning(
            "RBAC denied: user=%s role=%s action=%s connector=%s",
            user_id,
            user_role,
            action,
            connector_id,
        )
        # Audit unauthorized attempt
        if repo:
            log = IntegrationAuditLog(
                tenant_id=tenant_id,
                connector_id=connector_id,
                action=AuditAction.UNAUTHORIZED_CREDENTIAL_ACCESS,
                actor_id=user_id,
                metadata={
                    "attempted_action": action,
                    "user_role": user_role,
                    "required_roles": list(allowed_roles),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            await repo.create_audit_log(log.to_doc())

        raise HTTPException(
            status_code=403,
            detail=f"Bu islem icin yetkiniz yok. Gerekli roller: {', '.join(sorted(allowed_roles))}",
        )

    logger.debug(
        "RBAC allowed: user=%s role=%s action=%s",
        user_id,
        user_role,
        action,
    )
