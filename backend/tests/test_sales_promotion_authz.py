"""Task #246 — access-guard coverage for the OTA-promotion and group-booking
create endpoints.

These revenue-mutating endpoints share the same ``require_op("manage_sales")``
guard that Task #243 covered for the corporate-contract routes, but until now
nothing asserted the guard is wired to them. A future change could silently
weaken or drop it and let an unauthorized role create a pricing promotion or a
group booking.

Following the route-introspection approach of ``test_contract_approval_authz.py``,
these tests reach into the live ``sales.router`` route table, pull out the exact
``require_op`` dependency FastAPI will execute, and exercise it with real roles
WITHOUT mocking the guard:

  * the guard is actually present on both create routes — catches silent removal;
  * a caller WITHOUT ``manage_sales`` (housekeeping/staff/guest) is rejected 403;
  * a caller WITH ``manage_sales`` (sales/finance/admin) is allowed through;
  * a super-admin is allowed through via the uniform RBAC bypass;
  * an explicit per-user grant opens access (Task #28).
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import domains.revenue.rms_router.sales as sales

# Endpoint path suffix → HTTP method for every route that must be manage_sales-gated.
_GUARDED_ROUTES = [
    ("/sales/group-booking", "POST"),
    ("/sales/ota-promotion", "POST"),
]


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


# ── The guard is wired to every revenue-mutating create route ─────


@pytest.mark.parametrize("path_suffix,method", _GUARDED_ROUTES)
def test_route_is_manage_sales_gated(path_suffix, method):
    """Regression guard: group-booking/ota-promotion routes keep their manage_sales dep."""
    route = _find_route("/api" + path_suffix, method)
    _manage_sales_guard(route)  # raises if missing/duplicated


# ── Per-route access decisions ────────────────────────────────────


@pytest.fixture(params=[
    "/api/sales/group-booking",
    "/api/sales/ota-promotion",
])
def create_guard(request):
    return _manage_sales_guard(_find_route(request.param, "POST"))


async def test_role_without_manage_sales_is_rejected(create_guard):
    """Housekeeping lacks VIEW_COMPANIES → 403, can't create a promotion/booking."""
    with pytest.raises(HTTPException) as exc:
        await create_guard(current_user=_user("housekeeping"))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["staff", "guest"])
async def test_other_unauthorized_roles_are_rejected(create_guard, role):
    with pytest.raises(HTTPException) as exc:
        await create_guard(current_user=_user(role))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["sales", "finance", "admin"])
async def test_authorized_roles_pass(create_guard, role):
    """Roles holding manage_sales are allowed through (no exception)."""
    assert await create_guard(current_user=_user(role)) is None


async def test_super_admin_bypasses_guard(create_guard):
    assert await create_guard(current_user=_user("super_admin")) is None


async def test_per_user_granted_permission_opens_access(create_guard):
    """An otherwise-unauthorized role gains access via an explicit grant (Task #28)."""
    user = _user("housekeeping", granted_permissions=["view_companies"])
    assert await create_guard(current_user=user) is None
