"""HTTP regressions for the real registry, scope, feature and licence layers.

All persistence is in memory; no production credentials or database are used.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bootstrap import router_registry
from core import entitlement, helpers
from core.entitlements import enforcement
from core.security import get_current_user
from domains.pms import marketplace_router, pos_fnb_router, supplies_orders_router
from domains.pms.pos_fnb_router import pos_core

ORDER_PATH = "/api/marketplace/orders"
POS_PATH = "/api/pos/table-layout/test-outlet"
ORDER = {
    "items": [{"product_id": "linen", "quantity": 2, "unit_price": 100}],
    "total_amount": 200,
    "delivery_address": "Hotel receiving desk",
}


class MemoryCollection:
    def __init__(self):
        self.rows = []
        self.queries = []

    def find(self, query, projection=None):
        self.queries.append(deepcopy(query))
        rows = [deepcopy(row) for row in self.rows if all(row.get(k) == v for k, v in query.items())]

        async def to_list(length=None):
            return rows if length is None else rows[:length]

        return SimpleNamespace(to_list=to_list)

    async def insert_one(self, document):
        self.rows.append(deepcopy(document))
        return SimpleNamespace(inserted_id=document["id"])


@pytest.fixture
def marketplace(monkeypatch):
    state = SimpleNamespace(
        user=SimpleNamespace(id="buyer", tenant_id="hotel-a", role="procurement", roles=[]),
        tenant={"id": "hotel-a", "subscription_plan": "pms_lite", "features": {"hidden_marketplace": True}},
        licences={"pos_fnb": False, "channel_manager": False},
        licence_checks=[],
        orders=MemoryCollection(),
        products=MemoryCollection(),
        tables=MemoryCollection(),
    )
    state.tables.rows.append({
        "id": "table-1", "tenant_id": "hotel-a", "outlet_id": "test-outlet", "status": "available",
    })

    async def current_user():
        return state.user

    async def tenant_doc(_tenant_id):
        return state.tenant

    async def module_enabled(_tenant_id, module_key):
        state.licence_checks.append(module_key)
        return state.licences.get(module_key, False)

    async def not_super_admin(_user_id):
        return False

    async def no_usage(*_args, **_kwargs):
        pass

    monkeypatch.setenv("ENTITLEMENT_ENFORCEMENT_MODE", "enforce")
    monkeypatch.setattr(helpers, "load_tenant_doc", tenant_doc)
    monkeypatch.setattr(enforcement, "_module_enabled", module_enabled)
    monkeypatch.setattr(entitlement, "_check_module_access", module_enabled)
    monkeypatch.setattr(entitlement, "_is_super_admin_user", not_super_admin)
    monkeypatch.setattr(entitlement, "record_usage", no_usage)
    monkeypatch.setattr(entitlement, "_decode_token_payload", lambda _token: {
        "tenant_id": state.user.tenant_id, "user_id": state.user.id,
    })
    monkeypatch.setattr(supplies_orders_router, "db", SimpleNamespace(orders=state.orders))
    monkeypatch.setattr(marketplace_router, "db", SimpleNamespace(marketplace_products=state.products))
    monkeypatch.setattr(pos_core, "db", SimpleNamespace(table_layouts=state.tables))

    app = FastAPI()
    app.add_middleware(entitlement.EntitlementMiddleware)
    app.dependency_overrides[get_current_user] = current_user
    selected = {
        "domains.pms.marketplace_router",
        "domains.pms.supplies_orders_router",
        "domains.pms.pos_fnb_router",
    }
    mounted = set()
    for module, attr, tags, prefix, dependencies in router_registry._EXTRACTED_ROUTERS:
        if module not in selected:
            continue
        router = router_registry._safe_import(module, attr)
        assert router is not None
        app.include_router(router, tags=tags, prefix=prefix or "",
                           dependencies=router_registry._router_dependencies(module, dependencies, attr))
        mounted.add(module)
    assert mounted == selected
    with TestClient(app, headers={"Authorization": "Bearer isolated-test-token"}) as client:
        state.client = client
        yield state


@pytest.mark.parametrize("plan", ["pms_lite", "core_small_hotel", "deluxe_plus"])
@pytest.mark.parametrize("role", ["admin", "procurement"])
def test_procurement_works_without_pos_or_channel_licences(marketplace, plan, role):
    state = marketplace
    state.tenant["subscription_plan"] = plan
    state.user.role = role
    assert state.client.get("/api/marketplace/products").status_code == 200
    assert state.client.get(ORDER_PATH).json() == []
    created = state.client.post(ORDER_PATH, json=ORDER)
    assert created.status_code == 200, created.text
    assert created.json()["tenant_id"] == "hotel-a"
    assert created.json()["status"] == "pending"
    # No stale five-minute cache after either creation or a later read.
    assert state.client.get(ORDER_PATH).json() == [created.json()]
    second = state.client.post(ORDER_PATH, json=ORDER)
    assert second.status_code == 200
    assert len(state.client.get(ORDER_PATH).json()) == 2
    assert state.licence_checks == []


@pytest.mark.parametrize("features", [{}, {"hidden_marketplace": False}])
@pytest.mark.parametrize("role", ["admin", "procurement"])
def test_disabled_or_ungranted_feature_blocks_read_and_write(marketplace, features, role):
    state = marketplace
    state.tenant["features"] = features
    state.user.role = role
    state.licences["pos_fnb"] = True
    assert state.client.get(ORDER_PATH).status_code == 404
    assert state.client.post(ORDER_PATH, json=ORDER).status_code == 404
    assert state.orders.queries == []
    assert state.orders.rows == []


def test_feature_revocation_is_not_hidden_by_a_cached_response(marketplace):
    state = marketplace
    assert state.client.get(ORDER_PATH).status_code == 200
    state.tenant["features"]["hidden_marketplace"] = False
    assert state.client.get(ORDER_PATH).status_code == 404
    assert state.client.post(ORDER_PATH, json=ORDER).status_code == 404
    assert len(state.orders.queries) == 1
    assert state.orders.rows == []


@pytest.mark.parametrize("role,scopes", [
    ("procurement", ["pos"]), ("admin", []), ("front_desk", None), ("staff", None),
])
def test_procurement_user_scope_is_required(marketplace, role, scopes):
    state = marketplace
    state.user.role = role
    if scopes is not None:
        state.user.module_scopes = scopes
    for response in (state.client.get(ORDER_PATH), state.client.post(ORDER_PATH, json=ORDER)):
        assert response.status_code == 403
        assert response.json()["detail"] == "MODULE_ACCESS_DENIED"
    assert state.orders.queries == []
    assert state.orders.rows == []


def test_procurement_scope_does_not_grant_write_permission(marketplace):
    state = marketplace
    state.user.role = "staff"
    state.user.module_scopes = ["procurement"]
    assert state.client.get(ORDER_PATH).status_code == 403
    assert state.client.post(ORDER_PATH, json=ORDER).status_code == 403
    state.user.granted_permissions = ["view_procurement"]
    assert state.client.get(ORDER_PATH).status_code == 200
    assert state.client.post(ORDER_PATH, json=ORDER).status_code == 403
    assert state.orders.rows == []
    state.user.granted_permissions.append("manage_procurement")
    assert state.client.post(ORDER_PATH, json=ORDER).status_code == 200


def test_orders_are_tenant_scoped_and_cannot_be_forged(marketplace):
    state = marketplace
    response = state.client.post(ORDER_PATH, json={**ORDER, "tenant_id": "hotel-b"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "hotel-a"
    state.orders.rows.append({**response.json(), "id": "other-hotel-order", "tenant_id": "hotel-b"})
    assert state.client.get(ORDER_PATH).json() == [response.json()]
    assert state.orders.queries[-1] == {"tenant_id": "hotel-a"}
    state.user.tenant_id = "hotel-b"
    assert [row["id"] for row in state.client.get(ORDER_PATH).json()] == ["other-hotel-order"]
    assert state.orders.queries[-1] == {"tenant_id": "hotel-b"}


def test_actual_pos_endpoints_keep_licence_and_user_scope_guards(marketplace):
    state = marketplace
    state.user.role = "admin"
    denied = state.client.get(POS_PATH)
    assert denied.status_code == 403
    assert denied.json()["required_module"] == "pos_fnb"
    state.licences["pos_fnb"] = True
    state.user.role = "procurement"
    denied = state.client.get(POS_PATH)
    assert denied.status_code == 403
    assert denied.json()["detail"] == "MODULE_ACCESS_DENIED"
    state.user.role = "admin"
    assert state.client.get(POS_PATH).status_code == 200
    assert state.tables.queries == [{"tenant_id": "hotel-a", "outlet_id": "test-outlet"}]


def test_pos_router_guard_still_applies_without_central_middleware(marketplace):
    state = marketplace
    state.user.role = "admin"
    app = FastAPI()
    app.include_router(pos_fnb_router.router)
    app.dependency_overrides[get_current_user] = lambda: state.user
    with TestClient(app) as client:
        denied = client.get(POS_PATH)
    assert denied.status_code == 403
    assert "pos_fnb" in denied.json()["detail"]
    assert state.tables.queries == []


def test_orders_still_require_authentication(marketplace):
    app = FastAPI()
    app.include_router(supplies_orders_router.router)
    with TestClient(app) as client:
        assert client.get(ORDER_PATH).status_code == 401
        assert client.post(ORDER_PATH, json=ORDER).status_code == 401
    assert marketplace.orders.queries == []
    assert marketplace.orders.rows == []
