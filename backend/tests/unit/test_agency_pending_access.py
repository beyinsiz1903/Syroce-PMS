"""Pending actions use the authenticated party, never query-string ownership."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bootstrap import router_registry
from core import entitlement
from core.security import get_current_user
from routers import agency_pending
from routers.marketplace_b2b import get_marketplace_agency

HOTEL = "/api/marketplace/hotel/pending-actions"
AGENCY = "/api/marketplace/v1/pending-actions"


class ReadOnlyCollection:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def find(self, query, projection):
        self.queries.append(deepcopy(query))
        owner = {key: value for key, value in query.items() if key in ("tenant_id", "agency_id")}
        assert owner  # These system-db collections must never be read unscoped.

        async def cursor():
            for document in self.documents:
                if all(document.get(key) == value for key, value in owner.items()):
                    yield deepcopy(document)

        return cursor()


@pytest.fixture
def portal(monkeypatch):
    pairs = [("t1", "a1"), ("t2", "a1"), ("t1", "a2")]
    db = SimpleNamespace(
        agency_contracts=ReadOnlyCollection([
            {"id": f"c-{t}-{a}", "tenant_id": t, "agency_id": a, "contract_code": f"SOZ-{t}-{a}", "status": "pending"}
            for t, a in pairs
        ]),
        agency_statements=ReadOnlyCollection([
            {"id": f"s-{t}-{a}", "tenant_id": t, "agency_id": a, "status": "issued", "revision": 1,
             "agreements": {"hotel": 1, "agency": None}, "currency": "EUR"}
            for t, a in pairs
        ]),
    )
    state = SimpleNamespace(db=db, user=SimpleNamespace(role="admin", roles=[], tenant_id="t1"), licensed=True)

    async def user():
        return state.user

    async def agency():
        return {"agency_id": "a1"}

    async def licensed(_tenant_id, module):
        assert module == "agency_extranet"
        return state.licensed

    async def no_super_admin(_user_id):
        return False

    async def no_usage(*_args):
        pass

    monkeypatch.setattr(agency_pending, "get_system_db", lambda: db)
    monkeypatch.setattr(entitlement, "_decode_token_payload", lambda token: {
        "user_id": "u1", **({"tenant_id": state.user.tenant_id} if token == "hotel-token" else {}),
    })
    monkeypatch.setattr(entitlement, "_check_module_access", licensed)
    monkeypatch.setattr(entitlement, "_is_super_admin_user", no_super_admin)
    monkeypatch.setattr(entitlement, "record_usage", no_usage)
    app = FastAPI()
    app.add_middleware(entitlement.EntitlementMiddleware)
    for module, attr, tags, prefix, dependencies in router_registry._EXTRACTED_ROUTERS:
        if module == "routers.agency_pending":
            app.include_router(router_registry._safe_import(module, attr), prefix=prefix or "", tags=tags,
                               dependencies=router_registry._router_dependencies(module, dependencies, attr))
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_marketplace_agency] = agency
    with TestClient(app) as client:
        state.client = client
        yield state


@pytest.mark.parametrize("path,token,key,value,expected", [
    (HOTEL, "hotel-token", "tenant_id", "t1", {"c-t1-a1", "c-t1-a2", "s-t1-a1", "s-t1-a2"}),
    (AGENCY, "agency-token", "agency_id", "a1", {"c-t1-a1", "c-t2-a1", "s-t1-a1", "s-t2-a1"}),
])
def test_scope_comes_from_authenticated_identity(portal, path, token, key, value, expected):
    response = portal.client.get(path, headers={"Authorization": f"Bearer {token}"}, params={"tenant_id": "other", "agency_id": "other"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert {item["record_id"] for item in [*data["yours"], *data["theirs"]]} == expected
    for collection in (portal.db.agency_contracts, portal.db.agency_statements):
        assert collection.queries[-1][key] == value
        assert ("agency_id" if key == "tenant_id" else "tenant_id") not in collection.queries[-1]


def test_hotel_feature_entitlement_is_not_removed(portal):
    portal.licensed = False
    response = portal.client.get(HOTEL, headers={"Authorization": "Bearer hotel-token"})
    assert response.status_code == 403
    assert response.json()["required_module"] == "agency_extranet"
    assert portal.db.agency_contracts.queries == []


@pytest.mark.parametrize("role,tenant_id", [("front_desk", "t1"), ("agency_agent", "t1"), ("admin", "")])
def test_hotel_permissions_and_tenant_are_required(portal, role, tenant_id):
    portal.user.role = role
    portal.user.tenant_id = tenant_id
    response = portal.client.get(HOTEL)
    assert response.status_code == 403
    assert portal.db.agency_contracts.queries == []
    assert portal.db.agency_statements.queries == []


@pytest.mark.parametrize("path", [HOTEL, AGENCY])
def test_anonymous_users_cannot_read_pending_work(path):
    app = FastAPI()
    app.include_router(agency_pending.hotel_router)
    app.include_router(agency_pending.agency_router)
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
