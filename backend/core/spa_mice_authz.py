"""Role-based authorization for Spa & MICE write endpoints.

Centralizes the policy so the routers stay slim. Mirrors the
`_require_admin` pattern already used in `routers/pci_compliance.py`
and `routers/quick_id_proxy.py`.
"""
from __future__ import annotations

from fastapi import HTTPException

from models.enums import UserRole
from models.schemas import User

# Catalog (services / therapists / rooms / function spaces / menus) — only
# managers and above touch the catalog.
CATALOG_ROLES = {
    UserRole.SUPER_ADMIN, UserRole.ADMIN,
    UserRole.SUPERVISOR,
}

# Day-to-day spa scheduling — front desk + spa staff can book.
SPA_OPS_ROLES = CATALOG_ROLES | {UserRole.FRONT_DESK, UserRole.STAFF}

# Sales-driven MICE work.
MICE_OPS_ROLES = CATALOG_ROLES | {UserRole.SALES}

# Finance-impacting state changes (folio postings on completion etc.) —
# requires explicit cashier-grade authority.
FINANCE_ROLES = CATALOG_ROLES | {UserRole.FRONT_DESK, UserRole.FINANCE}


def _user_role(user: User) -> UserRole | None:
    role = getattr(user, "role", None)
    if isinstance(role, UserRole):
        return role
    if isinstance(role, str):
        try:
            return UserRole(role)
        except ValueError:
            return None
    return None


def require_roles(user: User, allowed: set[UserRole]) -> None:
    """Raise 403 unless *user* has one of *allowed* roles."""
    # Super admin: full bypass (covers role + roles[] representations).
    from core.security import _is_super_admin
    if _is_super_admin(user):
        return
    role = _user_role(user)
    if role is None or role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=(f"Bu işlem için yetkiniz yok. Gerekli rol: "
                    f"{', '.join(sorted(r.value for r in allowed))}"),
        )


def require_catalog(user: User) -> None:
    require_roles(user, CATALOG_ROLES)


def require_spa_ops(user: User) -> None:
    require_roles(user, SPA_OPS_ROLES)


def require_mice_ops(user: User) -> None:
    require_roles(user, MICE_OPS_ROLES)


def require_finance(user: User) -> None:
    require_roles(user, FINANCE_ROLES)
