"""Module-scoped authorization primitives for Syroce staff users.

This module deliberately stays independent from the pre-pilot reset command.
It provides one canonical module vocabulary plus a reusable FastAPI dependency
that can be attached to module routers as they are migrated to module-scoped
RBAC.

Security model
--------------
* ``super_admin`` always has platform-wide access.
* An explicit ``module_scopes`` list is authoritative and overrides role
  defaults. This is what keeps module QA users restricted to exactly one
  module.
* Legacy users without ``module_scopes`` continue to receive the conservative
  role defaults below, preserving backwards compatibility.
* Unknown scopes fail closed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from fastapi import Depends, HTTPException, status

from core.security import get_current_user

MODULE_SCOPES = frozenset(
    {
        "cashier",
        "channel_manager",
        "finance",
        "frontdesk",
        "housekeeping",
        "hr",
        "invoice",
        "maintenance",
        "pos",
        "procurement",
        "reports",
        "sales",
        "stock",
        "tasks",
    }
)

# Used only when an older user document has no explicit module_scopes field.
# Once module_scopes is present, the explicit list is the complete authority.
ROLE_DEFAULT_MODULE_SCOPES: dict[str, frozenset[str]] = {
    "admin": MODULE_SCOPES,
    "supervisor": MODULE_SCOPES,
    "front_desk": frozenset({"frontdesk"}),
    "housekeeping": frozenset({"housekeeping", "tasks"}),
    "sales": frozenset({"sales", "reports"}),
    "finance": frozenset({"cashier", "finance", "invoice", "reports"}),
    "procurement": frozenset({"procurement", "stock"}),
    "staff": frozenset(),
}

_SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class InvalidModuleScope(ValueError):
    """Raised when code or stored data refers to an unknown module scope."""


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _role_value(user: Any) -> str:
    role = _value(user, "role", "")
    return str(getattr(role, "value", role)).strip().lower()


def normalize_module_scope(scope: str) -> str:
    """Normalize one scope and reject values outside the canonical registry."""
    if not isinstance(scope, str):
        raise InvalidModuleScope("MODULE_SCOPE_INVALID")
    normalized = scope.strip().lower().replace("-", "_")
    if normalized.endswith(".*"):
        normalized = normalized[:-2]
    if normalized == "*":
        return normalized
    if not _SCOPE_PATTERN.fullmatch(normalized) or normalized not in MODULE_SCOPES:
        raise InvalidModuleScope("MODULE_SCOPE_UNKNOWN")
    return normalized


def explicit_module_scopes(user: Any) -> frozenset[str] | None:
    """Return explicit scopes, or ``None`` when the legacy field is absent.

    An explicitly stored empty list is meaningful: it means no module access.
    Malformed/unknown stored values are ignored individually and therefore
    fail closed rather than widening access.
    """
    raw = _value(user, "module_scopes", None)
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()

    normalized: set[str] = set()
    for item in raw:
        try:
            normalized.add(normalize_module_scope(item))
        except InvalidModuleScope:
            continue
    return frozenset(normalized)


def effective_module_scopes(user: Any) -> frozenset[str]:
    """Resolve effective module scopes without ever widening malformed data."""
    role = _role_value(user)
    if role == "super_admin":
        return frozenset({"*"})

    explicit = explicit_module_scopes(user)
    if explicit is not None:
        return explicit
    return ROLE_DEFAULT_MODULE_SCOPES.get(role, frozenset())


def has_module_scope(user: Any, scope: str) -> bool:
    """Return whether *user* may enter the requested top-level module."""
    try:
        normalized = normalize_module_scope(scope)
    except InvalidModuleScope:
        return False

    granted = effective_module_scopes(user)
    return "*" in granted or normalized in granted


def require_module_scope(scope: str):
    """Build a FastAPI dependency that enforces one module scope.

    Router migrations can use ``Depends(require_module_scope("frontdesk"))``.
    The dependency returns the already-authenticated user so handlers do not
    need a second authentication dependency.
    """
    normalized = normalize_module_scope(scope)

    async def dependency(current_user: Any = Depends(get_current_user)) -> Any:
        if not has_module_scope(current_user, normalized):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MODULE_ACCESS_DENIED",
            )
        return current_user

    return dependency
