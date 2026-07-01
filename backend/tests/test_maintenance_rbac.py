"""Wave 4 § maintenance 422 — tenant/RBAC enforcement contract.

`test_maintenance_schema_contract.py` locks the request *schema* (valid vs
bogus payloads). This module locks the *authorization* contract for the same
endpoints: every maintenance asset/plan route is tenant-scoped via
`get_current_user`, and the write (POST) routes additionally require the
`view_system_diagnostics` operation (RBAC), so an authenticated user without
that op cannot create assets/plans.

Asserted by route/dependency introspection so no DB or live auth is needed.
"""

from domains.pms.maintenance_router import router as maintenance_router


def _route(path, method):
    for r in maintenance_router.routes:
        if getattr(r, "path", "") == path and method in getattr(r, "methods", set()):
            return r
    return None


def _dep_names(route):
    return [getattr(d.call, "__name__", "") for d in route.dependant.dependencies]


def _gate_ops(route):
    ops = set()
    for d in route.dependant.dependencies:
        for cell in (getattr(d.call, "__closure__", None) or ()):
            try:
                v = cell.cell_contents
                if isinstance(v, str):
                    ops.add(v)
            except (ValueError, AttributeError):
                continue
    return ops


def test_asset_routes_registered():
    assert _route("/api/maintenance/assets", "POST") is not None
    assert _route("/api/maintenance/assets", "GET") is not None
    assert _route("/api/maintenance/plans", "POST") is not None
    assert _route("/api/maintenance/plans", "GET") is not None


def test_post_routes_require_rbac_op():
    for path in ("/api/maintenance/assets", "/api/maintenance/plans"):
        route = _route(path, "POST")
        assert "get_current_user" in _dep_names(route), f"{path} not tenant-scoped"
        assert "view_system_diagnostics" in _gate_ops(route), (
            f"{path} POST missing require_op RBAC gate"
        )


def test_list_routes_are_tenant_scoped():
    for path in ("/api/maintenance/assets", "/api/maintenance/plans"):
        route = _route(path, "GET")
        assert "get_current_user" in _dep_names(route), f"{path} GET not tenant-scoped"


# --- behavioral tenant scoping: tenant_id is bound on write & read ----------

import pytest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_create_asset_binds_tenant_id(monkeypatch):
    import domains.pms.maintenance_router as mr
    from models.schemas import MaintenanceAsset

    captured = {}

    class _Col:
        async def insert_one(self, doc):
            captured.update(doc)
            return SimpleNamespace(inserted_id="x")

    monkeypatch.setattr(mr, "db", SimpleNamespace(maintenance_assets=_Col()))
    user = SimpleNamespace(tenant_id="tenant-A", id="u1")
    data = MaintenanceAsset(name="hvac-1", asset_type="hvac", location="lab")
    result = await mr.create_maintenance_asset(data=data, current_user=user)
    assert captured.get("tenant_id") == "tenant-A"
    assert result.tenant_id == "tenant-A"


@pytest.mark.asyncio
async def test_list_assets_filters_by_tenant_id(monkeypatch):
    import domains.pms.maintenance_router as mr

    seen_query = {}

    class _Cursor:
        async def to_list(self, _n):
            return []

    class _Col:
        def find(self, query, _proj):
            seen_query.update(query)
            return _Cursor()

    monkeypatch.setattr(mr, "db", SimpleNamespace(maintenance_assets=_Col()))
    user = SimpleNamespace(tenant_id="tenant-B", id="u2")
    await mr.list_maintenance_assets(current_user=user)
    assert seen_query.get("tenant_id") == "tenant-B"
