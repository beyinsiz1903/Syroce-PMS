"""Task #243 — access-guard coverage for the corporate-contract endpoints.

The state-machine tests (``test_contract_approval_transition.py``, Task #239)
deliberately mock the permission dependency (``_perm=None``) so they can focus
on the transition logic. That leaves the *actual* access guard wired to the
endpoint — ``require_op("manage_sales")`` — with no automated coverage, so a
future change could silently weaken or drop it and let an unauthorized role flip
a contract to "approved".

These tests close that gap WITHOUT mocking the guard. They reach into the live
``sales.router`` route table, pull out the exact ``require_op`` dependency FastAPI
will execute, and exercise it with real roles:

  * the guard is actually present on the approval-transition route (and on the
    create/update routes that share it) — catches silent removal;
  * a caller WITHOUT ``manage_sales`` (housekeeping) is rejected with 403;
  * a caller WITH ``manage_sales`` (sales) is allowed through;
  * a super-admin is allowed through via the uniform RBAC bypass.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import domains.revenue.rms_router.sales as sales

# Endpoint path suffix → HTTP method for every route that must be manage_sales-gated.
_GUARDED_ROUTES = [
    ("/sales/corporate-contract", "POST"),                              # create
    ("/sales/corporate-contract/{contract_id}", "PUT"),                 # update
    ("/sales/corporate-contract/{contract_id}/approval-transition", "POST"),
]

_APPROVAL_PATH = "/api/sales/corporate-contract/{contract_id}/approval-transition"


def _operation_of(call):
    """Recover the ``operation`` a ``require_op(...)`` closure was built for.

    ``require_op`` returns an inner ``_dep`` that captures ``operation`` as a
    free variable; reading it back lets us assert *which* permission a route is
    actually gated on, not merely that some guard exists. Non-closure callables
    (e.g. the HTTPBearer security scheme) return ``None``.
    """
    code = getattr(call, "__code__", None)
    if code is None:
        return None
    for name, cell in zip(code.co_freevars or (), call.__closure__ or ()):
        if name == "operation":
            return cell.cell_contents
    return None


def _find_route(path: str, method: str):
    for route in sales.router.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"route not found: {method} {path}")


def _manage_sales_guard(route):
    """Return the single ``require_op('manage_sales')`` dependency on a route."""
    guards = [
        dep.call
        for dep in route.dependant.dependencies
        if _operation_of(dep.call) == "manage_sales"
    ]
    assert guards, f"route {route.path} has no require_op('manage_sales') guard"
    assert len(guards) == 1, f"route {route.path} has duplicate manage_sales guards"
    return guards[0]


def _user(role, *, granted_permissions=None):
    # Plain object (not MagicMock) so `_is_super_admin`'s getattr(..., "roles")
    # short-circuits cleanly instead of returning a truthy mock.
    return SimpleNamespace(role=role, roles=None,
                           granted_permissions=granted_permissions)


# ── The guard is wired to every contract-mutating route ───────────


@pytest.mark.parametrize("path_suffix,method", _GUARDED_ROUTES)
def test_route_is_manage_sales_gated(path_suffix, method):
    """Regression guard: create/update/approval routes keep their manage_sales dep."""
    route = _find_route("/api" + path_suffix, method)
    _manage_sales_guard(route)  # raises if missing/duplicated


# ── Approval-transition access decisions ──────────────────────────


@pytest.fixture
def approval_guard():
    return _manage_sales_guard(_find_route(_APPROVAL_PATH, "POST"))


async def test_role_without_manage_sales_is_rejected(approval_guard):
    """Housekeeping lacks VIEW_COMPANIES → 403, can't touch approval status."""
    with pytest.raises(HTTPException) as exc:
        await approval_guard(current_user=_user("housekeeping"))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["staff", "guest"])
async def test_other_unauthorized_roles_are_rejected(approval_guard, role):
    with pytest.raises(HTTPException) as exc:
        await approval_guard(current_user=_user(role))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["sales", "finance", "admin"])
async def test_authorized_roles_pass(approval_guard, role):
    """Roles holding manage_sales are allowed through (no exception)."""
    assert await approval_guard(current_user=_user(role)) is None


async def test_super_admin_bypasses_guard(approval_guard):
    assert await approval_guard(current_user=_user("super_admin")) is None


async def test_per_user_granted_permission_opens_access(approval_guard):
    """An otherwise-unauthorized role gains access via an explicit grant (Task #28)."""
    user = _user("housekeeping", granted_permissions=["view_companies"])
    assert await approval_guard(current_user=user) is None
