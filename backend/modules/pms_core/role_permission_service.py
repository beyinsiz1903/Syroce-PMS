"""
Role & Permission Enforcement Service - Validates user permissions for PMS operations.
"""
from typing import Dict, List, Optional

from fastapi import HTTPException, status

from models.enums import UserRole, Permission, ROLE_PERMISSIONS


# Operation-to-permission mapping
OPERATION_PERMISSIONS = {
    "check_in": [Permission.CHECKIN],
    "checkout": [Permission.CHECKOUT],
    "create_booking": [Permission.CREATE_BOOKING],
    "edit_booking": [Permission.EDIT_BOOKING],
    "cancel_booking": [Permission.EDIT_BOOKING],
    "post_charge": [Permission.POST_CHARGE],
    "post_payment": [Permission.POST_PAYMENT],
    "void_charge": [Permission.VOID_CHARGE],
    "void_payment": [Permission.VOID_CHARGE],
    "split_folio": [Permission.TRANSFER_FOLIO],
    "close_folio": [Permission.CLOSE_FOLIO],
    "override_rate": [Permission.OVERRIDE_RATE],
    "room_move": [Permission.EDIT_BOOKING],
    "room_upgrade": [Permission.EDIT_BOOKING],
    "walk_in": [Permission.CREATE_BOOKING, Permission.CHECKIN],
    "update_room_status": [Permission.UPDATE_ROOM_STATUS],
    "run_night_audit": [Permission.SYSTEM_SETTINGS],
    "manage_users": [Permission.MANAGE_USERS],
}

# Roles that can override any operation
SUPERVISOR_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.SUPERVISOR}


class RolePermissionService:
    """Enforces role-based access control for PMS operations."""

    def check_permission(self, user_role: str, operation: str) -> bool:
        """Check if a user role has permission for an operation."""
        try:
            role_enum = UserRole(user_role)
        except ValueError:
            return False

        # Admin/Super Admin can do everything
        if role_enum in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            return True

        required_perms = OPERATION_PERMISSIONS.get(operation, [])
        if not required_perms:
            return True  # No specific permission required

        user_perms = ROLE_PERMISSIONS.get(role_enum, [])
        # User needs ALL required permissions
        return all(perm.value in [p.value if isinstance(p, Permission) else p for p in user_perms] for perm in required_perms)

    def enforce_permission(self, user_role: str, operation: str):
        """Raise 403 if user doesn't have permission."""
        if not self.check_permission(user_role, operation):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for operation: {operation}. Required role/permissions not met.",
            )

    def is_supervisor_override_required(self, user_role: str, operation: str) -> bool:
        """Check if the operation requires supervisor override for this user role."""
        try:
            role_enum = UserRole(user_role)
        except ValueError:
            return True

        # Supervisors and above don't need override
        if role_enum in SUPERVISOR_ROLES:
            return False

        # Operations that always need supervisor override for non-supervisors
        supervisor_operations = {"override_rate", "void_charge", "void_payment", "run_night_audit"}
        return operation in supervisor_operations

    def get_user_permissions(self, user_role: str) -> List[str]:
        """Get all permissions for a user role."""
        try:
            role_enum = UserRole(user_role)
        except ValueError:
            return []

        if role_enum in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            return [p.value for p in Permission]

        perms = ROLE_PERMISSIONS.get(role_enum, [])
        return [p.value if isinstance(p, Permission) else p for p in perms]
