"""Real HTTP authorization for the read-only module-readiness endpoints."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bootstrap import router_registry
from core.security import get_current_user
from routers import module_readiness

ADMIN = "/api/admin/tenants/t2/module-readiness"
HOTEL = "/api/modules/readiness"


@pytest.fixture
def readiness_app(monkeypatch):
    state = SimpleNamespace(user=SimpleNamespace(role="admin", roles=[], tenant_id="t1"), queries=[])

    class Tenants:
        async def find_one(self, query, *_args):
            state.queries.append(query)
            return {"id": query["id"]} if query["id"] in ("t1", "t2") else None

    async def flags(_tenant):
        return {"dashboard": True}

    async def user():
        return state.user

    monkeypatch.setattr(module_readiness, "get_system_db", lambda: SimpleNamespace(tenants=Tenants()))
    monkeypatch.setattr(module_readiness, "effective_tenant_modules", flags)
    app = FastAPI()
    for module, attr, tags, prefix, dependencies in router_registry._EXTRACTED_ROUTERS:
        if module == "routers.module_readiness":
            app.include_router(router_registry._safe_import(module, attr), tags=tags, prefix=prefix or "",
                               dependencies=router_registry._router_dependencies(module, dependencies, attr))
    app.dependency_overrides[get_current_user] = user
    with TestClient(app) as client:
        state.client = client
        yield state


@pytest.mark.parametrize("role", ["admin", "supervisor"])
def test_hotel_roles_can_only_read_their_own_hotel(readiness_app, role):
    state = readiness_app
    state.user.role = role
    response = state.client.get(HOTEL, params={"tenant_id": "t2"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "t1"
    assert response.json()["modules"]["dashboard"]["status"] == "ready"
    assert state.queries == [{"id": "t1"}]
    assert state.client.get(ADMIN).status_code == 404
    assert len(state.queries) == 1


@pytest.mark.parametrize("role", ["staff", "front_desk", "agency_agent"])
def test_unauthorized_roles_cannot_inspect_setup(readiness_app, role):
    state = readiness_app
    state.user.role = role
    assert state.client.get(HOTEL).status_code == 403
    assert state.client.get(ADMIN).status_code == 404
    assert state.queries == []


def test_only_super_admin_can_select_another_hotel(readiness_app):
    state = readiness_app
    state.user.role = "super_admin"
    response = state.client.get(ADMIN)
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "t2"
    assert state.client.get("/api/admin/tenants/missing/module-readiness").status_code == 404


@pytest.mark.parametrize("path", [ADMIN, HOTEL])
def test_authentication_is_required(path):
    app = FastAPI()
    app.include_router(module_readiness.admin_router)
    app.include_router(module_readiness.hotel_router)
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
