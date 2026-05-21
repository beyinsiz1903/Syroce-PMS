"""
Role & Permission Enforcement Service - Validates user permissions for PMS operations.
"""

from fastapi import HTTPException, status

from models.enums import ROLE_PERMISSIONS, Permission, UserRole

# Operation-to-permission mapping
OPERATION_PERMISSIONS = {
    # Booking lifecycle
    "checkin": [Permission.CHECKIN],
    "check_in": [Permission.CHECKIN],
    "checkout": [Permission.CHECKOUT],
    "create_booking": [Permission.CREATE_BOOKING],
    "edit_booking": [Permission.EDIT_BOOKING],
    "delete_booking": [Permission.DELETE_BOOKING],
    "cancel_booking": [Permission.EDIT_BOOKING],
    # Folio / financial
    "view_folio": [Permission.VIEW_FOLIO],
    "post_charge": [Permission.POST_CHARGE],
    "post_payment": [Permission.POST_PAYMENT],
    "void_charge": [Permission.VOID_CHARGE],
    "void_payment": [Permission.VOID_CHARGE],
    "split_folio": [Permission.TRANSFER_FOLIO],
    "transfer_folio": [Permission.TRANSFER_FOLIO],  # Bug CQ fix — missing op key
    "close_folio": [Permission.CLOSE_FOLIO],
    "override_rate": [Permission.OVERRIDE_RATE],
    # Room operations
    "room_move": [Permission.EDIT_BOOKING],
    "room_upgrade": [Permission.EDIT_BOOKING],
    "walk_in": [Permission.CREATE_BOOKING, Permission.CHECKIN],
    "update_room_status": [Permission.UPDATE_ROOM_STATUS],
    "run_night_audit": [Permission.SYSTEM_SETTINGS],
    # Admin
    "manage_users": [Permission.MANAGE_USERS],
    # PCI / VCC card operations (Bug CS — v58)
    "store_card": [Permission.POST_PAYMENT],
    "reveal_card": [Permission.POST_PAYMENT],
    "delete_card": [Permission.VOID_CHARGE],
    "view_card_status": [Permission.VIEW_FOLIO],
    # Cashiering / City Ledger / AR (Bug CT — v59) — financial-sensitive
    "view_city_ledger": [Permission.VIEW_FINANCIAL_REPORTS],
    "view_city_ledger_transactions": [Permission.VIEW_FINANCIAL_REPORTS],
    "view_ar_aging": [Permission.VIEW_FINANCIAL_REPORTS],
    "view_outstanding_balance": [Permission.VIEW_FINANCIAL_REPORTS],
    "view_credit_limit": [Permission.VIEW_FINANCIAL_REPORTS],
    "manage_city_ledger": [Permission.VIEW_FINANCIAL_REPORTS, Permission.POST_PAYMENT],
    "manage_credit_limit": [Permission.VIEW_FINANCIAL_REPORTS, Permission.POST_PAYMENT],
    "post_direct_bill": [Permission.VIEW_FINANCIAL_REPORTS, Permission.POST_PAYMENT],
    "post_city_ledger_payment": [Permission.VIEW_FINANCIAL_REPORTS, Permission.POST_PAYMENT],
    # split-payment uses existing "post_payment" key (FRONT_DESK has POST_PAYMENT)
    # Departments / Reports / Rates / POS / Loyalty (Bug CU — v60)
    "view_finance_reports": [Permission.VIEW_FINANCIAL_REPORTS],
    # RMS / Revenue dashboard — finance-grade data (ADR/RevPAR/cancellation/total
    # revenue). Front desk & housekeeping intentionally locked out (Bug — yetki boşluğu).
    "view_revenue": [Permission.VIEW_FINANCIAL_REPORTS],
    "manage_pricing": [Permission.OVERRIDE_RATE],
    "export_data": [Permission.EXPORT_DATA],
    "view_corporate_accounts": [Permission.VIEW_COMPANIES],
    "view_vip_notes": [Permission.VIEW_REPORTS],
    # v71 Bug DH: reports/exec/HR/PII permission keys
    "view_reports": [Permission.VIEW_REPORTS],
    "view_executive_reports": [Permission.VIEW_FINANCIAL_REPORTS],
    # v2 HR module (Task #262). `view_hr` = okuma (liste/profil/master data);
    # `manage_hr` = CRUD (personel/departman/pozisyon). Geriye-uyumluluk:
    # `view_executive_reports` op key'i hâlâ HR endpoint'lerinde kullanılır
    # ve `VIEW_FINANCIAL_REPORTS` perm'i ile geçer (Finance + super_admin).
    # `view_hr_payroll` bordro/maaş alanlarını görme yetkisi — VIEW_HR ile
    # PII maskeleme bypass'ı için (HR + Finance).
    "view_hr": [Permission.VIEW_HR],
    "manage_hr": [Permission.MANAGE_HR],
    "view_hr_payroll": [Permission.VIEW_HR],
    "manage_hr_master_data": [Permission.MANAGE_HR],
    "view_guest_list": [Permission.VIEW_REPORTS],
    "view_it_system": [Permission.SYSTEM_SETTINGS],
    # v87 DR-FOLLOWUP-1: ops/devops diagnostics (production_golive, ops_events) — semantik ayrı key, ADMIN/SUPER_ADMIN only
    "view_system_diagnostics": [Permission.SYSTEM_SETTINGS],
    # Regulatory: tax/license/inspection — admin-grade tenant-administrative data
    "view_regulatory_reports": [Permission.SYSTEM_SETTINGS],
    # v88 DR-FOLLOWUP-2 (Bug DW): NO_AUTH write endpoints — semantik ayrı keys, hepsi ADMIN/SUPER_ADMIN only
    "manage_night_audit": [Permission.SYSTEM_SETTINGS],
    "manage_secrets": [Permission.SYSTEM_SETTINGS],
    "manage_budget_config": [Permission.SYSTEM_SETTINGS],
    "manage_channel_connectors": [Permission.SYSTEM_SETTINGS],
    "manage_rates": [Permission.OVERRIDE_RATE],
    "manage_pos_settings": [Permission.SYSTEM_SETTINGS],
    "manage_loyalty_tiers": [Permission.SYSTEM_SETTINGS],
    # v89 DR-FOLLOWUP-2 Phase 1.5: bulk NO_AUTH closure
    "manage_approvals": [Permission.SYSTEM_SETTINGS],
    "manage_sales": [Permission.VIEW_COMPANIES],  # SALES + FINANCE both have it
    "manage_guests": [Permission.VIEW_REPORTS],
    # Internal messaging — "urgent" priority is gated separately because it
    # generates a system alert on the recipient. Default messaging access alone
    # must NOT be enough to trigger it.
    "send_urgent_message": [Permission.SEND_URGENT_MESSAGE],
    # Manager-only audit-derived reports (Task #26 acil mesaj raporu vs.).
    "view_audit_log": [Permission.VIEW_AUDIT_LOG],
}

# v89: module → roles mapping for require_module() helper
MODULE_ROLES = {
    "housekeeping": {UserRole.HOUSEKEEPING, UserRole.SUPERVISOR, UserRole.ADMIN, UserRole.SUPER_ADMIN},
    "maintenance": {UserRole.SUPERVISOR, UserRole.ADMIN, UserRole.SUPER_ADMIN},
    "frontdesk": {UserRole.FRONT_DESK, UserRole.SUPERVISOR, UserRole.ADMIN, UserRole.SUPER_ADMIN},
    "pos": {UserRole.FRONT_DESK, UserRole.SUPERVISOR, UserRole.ADMIN, UserRole.SUPER_ADMIN},
}

# Roles that can override any operation
SUPERVISOR_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.SUPERVISOR}


def require_op(operation: str):
    """FastAPI dependency factory — Bug CU v60 cache-bypass remediation.

    `@cached`-dekoratorlu endpoint'lerde gövde içindeki `_enforce` cache hit'te
    atlanır. Bu helper bir Depends üretir: dependency injection cache wrapper'ından
    önce çalışır, dolayısıyla cache poisoning üzerinden RBAC bypass mümkün olmaz.

    Task #28: kullanıcı-özel `granted_permissions` listesi, rol-bazlı izinlere
    ek olarak değerlendirilir; admin panelinden tek tek verilen izinler bu yolla
    operasyon-seviyesinde kabul edilir.
    """
    from fastapi import Depends as _Depends

    from core.security import get_current_user
    from models.schemas import User as _User

    async def _dep(current_user: _User = _Depends(get_current_user)) -> None:
        # Super admin: full bypass on per-operation RBAC.
        from core.security import _is_super_admin as _is_sa
        if _is_sa(current_user):
            return
        RolePermissionService().enforce_permission(
            current_user.role,
            operation,
            granted_permissions=getattr(current_user, "granted_permissions", None),
        )
    return _dep


def require_module(module: str):
    """v89: FastAPI dependency factory — module-based access (role allowlist).

    Used for cross-domain endpoints where multiple roles legitimately operate
    (e.g. housekeeping mobile usable by HK + MANAGER + ADMIN).
    """
    from fastapi import Depends as _Depends
    from fastapi import HTTPException as _HTTPException

    from core.security import get_current_user
    from models.schemas import User as _User

    allowed = MODULE_ROLES.get(module, set())
    def _norm(r):
        return getattr(r, "value", str(r))
    allowed_norm = {_norm(r) for r in allowed}

    async def _dep(current_user: _User = _Depends(get_current_user)) -> None:
        # Super admin: full bypass on module-role allowlist (uniform check).
        from core.security import _is_super_admin as _is_sa
        if _is_sa(current_user):
            return
        if _norm(current_user.role) not in allowed_norm:
            raise _HTTPException(status_code=403, detail=f"Module '{module}' access denied")
    return _dep


def require_role(*allowed_roles):
    """FastAPI dependency factory — role allow-list (cache-wrapper-safe).

    Bug CV v61: `@cached`-dekoratorlu endpoint'lerde body içinde role check'i
    cache hit'te atlanır. Bu dependency cache wrapper'ından önce çalışır.
    """
    from fastapi import Depends as _Depends
    from fastapi import HTTPException as _HTTPException

    from core.security import get_current_user
    from models.schemas import User as _User

    # v66 Bug DC2: Python 3.11+ `str(StrEnum)` returns 'UserRole.X' (not 'x') —
    # so we normalize via .value where available, then fall back to str().
    def _norm(r):
        return getattr(r, "value", str(r))
    allowed = {_norm(r) for r in allowed_roles}
    async def _dep(current_user: _User = _Depends(get_current_user)) -> None:
        # Super admin: full bypass on role allowlist.
        from core.security import _is_super_admin as _is_sa
        if _is_sa(current_user):
            return
        if _norm(current_user.role) not in allowed:
            raise _HTTPException(status_code=403, detail="Insufficient role")
    return _dep


class RolePermissionService:
    """Enforces role-based access control for PMS operations."""

    def check_permission(
        self,
        user_role: str,
        operation: str,
        granted_permissions: list[str] | None = None,
    ) -> bool:
        """Check if a user has permission for an operation.

        Task #28: `granted_permissions` opsiyoneldir; verilirse rol-bazlı
        kontrolün ÜSTÜNE eklenir — kullanıcı, role'üne tanınmamış olsa bile
        operasyon için gerekli izne adı yazılı olarak sahipse erişimi açılır.
        Geriye dönük uyum: parametre verilmezse davranış değişmez.
        """
        try:
            role_enum = UserRole(user_role)
        except ValueError:
            return False

        # Admin/Super Admin can do everything
        if role_enum in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            return True

        required_perms = OPERATION_PERMISSIONS.get(operation)
        if required_perms is None:
            # Bug CQ fix — fail-closed: unknown operation rejected (was previously fail-open allow-all)
            return False
        if not required_perms:
            return True

        user_perms = ROLE_PERMISSIONS.get(role_enum, [])
        owned_values = {p.value if isinstance(p, Permission) else p for p in user_perms}
        # Task #28: kullanıcı-özel olarak verilen izinleri de havuza ekle.
        if granted_permissions:
            owned_values.update(str(g) for g in granted_permissions if g)
        # User needs ALL required permissions
        return all(perm.value in owned_values for perm in required_perms)

    def enforce_permission(
        self,
        user_role: str,
        operation: str,
        granted_permissions: list[str] | None = None,
    ):
        """Raise 403 if user doesn't have permission."""
        if not self.check_permission(user_role, operation, granted_permissions):
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

    def get_user_permissions(self, user_role: str) -> list[str]:
        """Get all permissions for a user role."""
        try:
            role_enum = UserRole(user_role)
        except ValueError:
            return []

        if role_enum in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            return [p.value for p in Permission]

        perms = ROLE_PERMISSIONS.get(role_enum, [])
        return [p.value if isinstance(p, Permission) else p for p in perms]
