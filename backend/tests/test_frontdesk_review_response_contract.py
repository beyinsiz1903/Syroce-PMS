from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from domains.guest.experience_router import feedback, reviews


def app_for(module, monkeypatch, exists=True):
    collection = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "r1"} if exists else None),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=int(exists))),
    )
    monkeypatch.setattr(module, "db", SimpleNamespace(guest_reviews=collection, external_reviews=collection))
    app = FastAPI()
    app.include_router(module.router)
    user = SimpleNamespace(id="actor", tenant_id="t1")
    app.dependency_overrides[module.get_current_user] = lambda: user
    for route in module.router.routes:
        for dep in route.dependant.dependencies:
            if dep.name == "_perm":
                app.dependency_overrides[dep.call] = lambda: None
    return app, collection


@pytest.mark.asyncio
@pytest.mark.parametrize("module,path", [(reviews, "/api/crm/reviews/r1/respond"), (feedback, "/api/feedback/external-reviews/r1/respond")])
async def test_response_json_matches_ui_and_is_tenant_scoped(module, path, monkeypatch):
    app, collection = app_for(module, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"response": " Yapay yanıt "})
    assert response.status_code == 200
    query, change = collection.update_one.await_args.args
    assert query == {"id": "r1", "tenant_id": "t1"}
    assert change["$set"]["response"] == "Yapay yanıt"
    assert response.json()["delivery"] == "stored_only"


@pytest.mark.asyncio
@pytest.mark.parametrize("module,path", [(reviews, "/api/crm/reviews/r1/respond"), (feedback, "/api/feedback/external-reviews/r1/respond")])
async def test_missing_or_other_tenant_review_is_not_success(module, path, monkeypatch):
    app, _ = app_for(module, monkeypatch, exists=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"response": "Yapay yanıt"})
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "", " ", 123, "x" * 2001])
@pytest.mark.parametrize("module,path", [(reviews, "/api/crm/reviews/r1/respond"), (feedback, "/api/feedback/external-reviews/r1/respond")])
async def test_invalid_response_never_writes(value, module, path, monkeypatch):
    app, collection = app_for(module, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"response": value})
    assert response.status_code in {400, 422}
    collection.update_one.assert_not_awaited()
