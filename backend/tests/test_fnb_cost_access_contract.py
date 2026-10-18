import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from bootstrap.router_registry import _router_dependencies
from core.security import get_current_user
from domains.hr import router as hr_router

HANDLERS = (
    hr_router.get_recipes, hr_router.get_recipe, hr_router.list_ingredients,
    hr_router.create_recipe, hr_router.update_recipe, hr_router.add_ingredient,
    hr_router.update_ingredient, hr_router.create_beo,
)
REQUESTS = (
    ("GET", "/api/fnb/recipes", None),
    ("GET", "/api/fnb/recipes/recipe-1", None),
    ("GET", "/api/fnb/ingredients", None),
    ("POST", "/api/fnb/recipes", {"dish_name": "Soup", "selling_price": 100}),
    ("PUT", "/api/fnb/recipes/recipe-1", {"selling_price": 120}),
    ("POST", "/api/fnb/ingredients", {"name": "Salt", "unit_cost": 5}),
    ("PUT", "/api/fnb/ingredients/ingredient-1", {"unit_cost": 20}),
    ("POST", "/api/fnb/beo", {"name": "Event"}),
)


def test_fnb_cost_and_supplier_reads_require_the_same_operation_as_mutations():
    """Cost, inventory value and supplier data must not be a login-only read."""
    for handler in HANDLERS:
        assert 'require_op("manage_sales")' in inspect.getsource(handler)


@pytest.mark.parametrize("handler", HANDLERS, ids=lambda handler: handler.__name__)
async def test_each_cost_handler_enforces_operation_even_without_outer_router_guard(handler):
    """Exercise the real Depends callable, not only its source spelling."""
    guard = inspect.signature(handler).parameters["_perm"].default.dependency
    with pytest.raises(HTTPException) as exc:
        await guard(current_user=SimpleNamespace(role="staff", module_scopes=["pos"]))
    assert exc.value.status_code == 403
    assert "manage_sales" in exc.value.detail
    await guard(current_user=SimpleNamespace(role="admin"))


class Collection:
    def __init__(self, docs=()):
        self.docs = list(docs)
        self.calls = []

    def matching(self, query):
        return [doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())]

    def find(self, query, _projection=None):
        self.calls.append(("find", query))
        docs = self.matching(query)
        class Cursor:
            def sort(self, *_args):
                return self

            async def to_list(self, limit):
                return [dict(doc) for doc in docs[:limit]]
        return Cursor()

    async def find_one(self, query, _projection=None):
        self.calls.append(("find_one", query))
        matches = self.matching(query)
        return dict(matches[0]) if matches else None

    async def insert_one(self, doc):
        self.calls.append(("insert_one", doc))
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        self.calls.append(("update_one", query))
        for doc in self.matching(query):
            doc.update(update["$set"])


@pytest.fixture
def fnb_app(monkeypatch):
    db = SimpleNamespace(
        recipes=Collection([{"id": "recipe-1", "tenant_id": "tenant-A", "dish_name": "Soup", "active": True,
                             "selling_price": 100, "ingredients": [{"ingredient_id": "ingredient-1", "quantity": 2}]}]),
        ingredients=Collection([{"id": "ingredient-1", "tenant_id": "tenant-A", "name": "Flour", "unit_cost": 10,
                                 "current_stock": 4, "supplier": "Private supplier"}]),
        banquet_event_orders=Collection(),
    )
    monkeypatch.setattr(hr_router, "db", db)
    enabled = AsyncMock(return_value=True)
    monkeypatch.setattr("core.entitlements.enforcement._module_enabled", enabled)
    monkeypatch.setenv("ENTITLEMENT_ENFORCEMENT_MODE", "enforce")
    user = SimpleNamespace(id="user-1", tenant_id="tenant-A", role="supervisor", module_scopes=["pos"])
    app = FastAPI()
    async def current_user():
        return user
    app.dependency_overrides[get_current_user] = current_user
    app.include_router(hr_router.fnb_router, dependencies=_router_dependencies("domains.hr.router", None, "fnb_router"))
    app.include_router(hr_router.router, dependencies=_router_dependencies("domains.hr.router", None))
    return TestClient(app), user, db, enabled


@pytest.mark.parametrize("method,path,payload", REQUESTS)
def test_authorized_pos_manager_can_configure_fnb_without_hr_access(fnb_app, method, path, payload):
    client, _user, _db, _enabled = fnb_app
    result = client.request(method, path, json=payload)
    assert result.status_code == 200, result.text
    # Moving F&B out of HR must not grant access to personnel records.
    assert client.get("/api/hr/departments").status_code == 403


@pytest.mark.parametrize("method,path,payload", REQUESTS)
@pytest.mark.parametrize("denied_by", ["role", "scope", "licence"])
def test_each_configuration_route_fails_closed_before_reading_or_writing(fnb_app, method, path, payload, denied_by):
    client, user, db, enabled = fnb_app
    if denied_by == "role":
        user.role = "staff"
    elif denied_by == "scope":
        user.module_scopes = ["hr"]
    else:
        enabled.return_value = False
    result = client.request(method, path, json=payload)
    assert result.status_code == 403, result.text
    assert all(not collection.calls for collection in vars(db).values())
