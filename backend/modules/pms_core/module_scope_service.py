"""Per-user module-scope helpers.

The existing Syroce authorization model is role/permission based and tenant
module flags are shared by every user in a hotel.  ``module_scopes`` adds an
*opt-in* least-privilege layer for validation/pilot accounts:

* an absent or empty scope list preserves the legacy behaviour;
* a non-empty scope list is restrictive;
* ``*`` grants every module;
* ``prefix.*`` grants the prefix and its descendants.

The helper is intentionally pure so backend dependencies, reset tooling and
tests all use exactly the same matching rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def normalize_module_scope(value: Any) -> str:
    """Return a stable lower-case scope key or an empty string."""

    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_")


def normalize_module_scopes(values: Iterable[Any] | None) -> tuple[str, ...]:
    """Normalize and de-duplicate scopes while preserving sorted output."""

    if values is None:
        return ()
    normalized = {normalize_module_scope(value) for value in values}
    normalized.discard("")
    return tuple(sorted(normalized))


def module_scope_allows(module_scopes: Iterable[Any] | None, module_name: Any) -> bool:
    """Return whether ``module_name`` is allowed by an opt-in scope list.

    Empty scope lists mean that the account predates module scoping, so legacy
    role/permission checks remain authoritative.  Once at least one scope is
    present, access becomes fail-closed.
    """

    scopes = normalize_module_scopes(module_scopes)
    if not scopes:
        return True

    requested = normalize_module_scope(module_name)
    if not requested:
        return False
    if "*" in scopes or requested in scopes:
        return True

    for scope in scopes:
        if not scope.endswith(".*"):
            continue
        prefix = scope[:-2]
        if requested == prefix or requested.startswith(f"{prefix}.") or requested.startswith(f"{prefix}_"):
            return True
    return False


def filter_modules_for_scopes(
    modules: Mapping[str, Any],
    module_scopes: Iterable[Any] | None,
) -> dict[str, bool]:
    """Overlay per-user scopes on a tenant-wide module map.

    The returned mapping always keeps the original keys.  A restricted user
    sees a module as enabled only when the tenant enabled it *and* the user
    scope permits it.
    """

    scopes = normalize_module_scopes(module_scopes)
    if not scopes:
        return {str(key): bool(value) for key, value in modules.items()}
    return {
        str(key): bool(value) and module_scope_allows(scopes, key)
        for key, value in modules.items()
    }
