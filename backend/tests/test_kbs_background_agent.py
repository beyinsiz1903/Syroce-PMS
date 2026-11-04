"""Local Mongo queue semantics and HTTP authorization; no authority network."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from core.security import get_current_user
from routers import kbs


def request(user, **overrides):
    headers = {"x-kbs-background": "1", "x-kbs-tenant": user.tenant_id, "x-kbs-user": user.id}
    headers.update(overrides)
    return Request({"type": "http", "headers": [(key.encode(), value.encode()) for key, value in headers.items()]})


@pytest.fixture
async def context(monkeypatch):
    from core.tenant_db import get_system_db

    database = get_system_db()
    user = SimpleNamespace(id="worker-user", tenant_id="test_police_agent_" + uuid.uuid4().hex)
    monkeypatch.setattr(kbs, "db", database)
    yield database, user
    for collection in (database.kbs_reports, database.kbs_cloud_configs):
        await collection.delete_many({"tenant_id": user.tenant_id})


@pytest.mark.parametrize("headers", [
    {"x-kbs-user": "different-user"}, {"x-kbs-tenant": "different-hotel"}, {"x-kbs-background": "0"},
])
def test_background_context_never_retargets_cookie_login(headers):
    user = SimpleNamespace(id="u1", tenant_id="t1")
    with pytest.raises(HTTPException) as error:
        kbs._check_background_context(request(user, **headers), user)
    assert error.value.status_code == 403


def test_legacy_workers_work_but_background_requires_all_context_headers():
    user = SimpleNamespace(id="u1", tenant_id="t1")
    empty = Request({"type": "http", "headers": []})
    kbs._check_background_context(empty, user)
    with pytest.raises(HTTPException):
        kbs._check_background_context(empty, user, required=True)
    kbs._check_background_context(request(user), user, required=True)


@pytest.mark.asyncio
async def test_metadata_feed_is_fair_scoped_ready_and_contains_no_guest_data(context):
    database, user = context
    now = datetime.now(UTC)
    stamp = now.isoformat()
    records = []
    for index in range(25):
        records.append({"id": f"job-{index:02}", "created_at": stamp, "status": "pending"})
    records.extend([
        {"id": "future", "created_at": stamp, "status": "pending", "next_retry_at": (now + timedelta(hours=1)).isoformat()},
        {"id": "uncertain", "created_at": stamp, "status": "pending", "delivery_uncertain": True},
        {"id": "leased", "created_at": stamp, "status": "in_progress", "leased_until": (now + timedelta(hours=1)).isoformat()},
        {"id": "done", "created_at": stamp, "status": "done"},
        {"id": "stale", "created_at": stamp, "status": "in_progress", "leased_until": (now - timedelta(hours=1)).isoformat()},
    ])
    for row in records:
        await database.kbs_reports.insert_one({**row, "tenant_id": user.tenant_id, "_kind": kbs.QUEUE_KIND,
            "payload": {"id_number": "10000000146", "guest_name": "Synthetic Secret"}})
    # Explicit other-tenant row cannot leak even when the cursor is supplied.
    foreign = {"id": "alien", "tenant_id": user.tenant_id + "other", "_kind": kbs.QUEUE_KIND, "created_at": stamp, "status": "pending"}
    await database.kbs_reports.insert_one(foreign)
    try:
        first = await kbs.kbs_background_jobs(request(user), None, None, 20, user, None)
        assert [row["id"] for row in first["jobs"]] == [f"job-{index:02}" for index in range(20)]
        cursor = first["cursor"]
        second = await kbs.kbs_background_jobs(request(user), cursor["created_at"], cursor["id"], 20, user, None)
        assert [row["id"] for row in second["jobs"]] == [f"job-{index:02}" for index in range(20, 25)] + ["stale"]
        assert all(set(row) == {"id", "created_at"} for row in first["jobs"] + second["jobs"])
        assert "10000000146" not in str(first) and "Synthetic Secret" not in str(first)
        cursor = second["cursor"]
        assert (await kbs.kbs_background_jobs(request(user), cursor["created_at"], cursor["id"], 20, user, None))["cursor"] is None
    finally:
        await database.kbs_reports.delete_one({"tenant_id": foreign["tenant_id"], "id": "alien"})


@pytest.mark.asyncio
async def test_managed_cloud_is_rejected_even_if_paused(context):
    database, user = context
    from core.kbs_cloud import config_query

    await database.kbs_cloud_configs.insert_one({**config_query(user.tenant_id), "enabled": False})
    for operation in (
        lambda: kbs.kbs_background_context(request(user), user, None),
        lambda: kbs.kbs_background_jobs(request(user), None, None, 20, user, None),
    ):
        with pytest.raises(HTTPException) as error:
            await operation()
        assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_server_test_mode_never_hands_work_to_live_police_agent(context, monkeypatch):
    _, user = context
    monkeypatch.setenv("KBS_TEST_MODE", "1")
    for operation in (
        lambda: kbs.kbs_background_context(request(user), user, None),
        lambda: kbs.kbs_background_jobs(request(user), None, None, 20, user, None),
    ):
        with pytest.raises(HTTPException) as error:
            await operation()
        assert error.value.status_code == 423


@pytest.mark.asyncio
async def test_http_worker_mutations_enforce_context_before_any_queue_access():
    app = FastAPI()
    app.include_router(kbs.router)
    user = SimpleNamespace(id="user-a", tenant_id="tenant-a")
    app.dependency_overrides[get_current_user] = lambda: user
    for route in app.routes:
        for dep in getattr(getattr(route, "dependant", None), "dependencies", []):
            if dep.name == "_perm":
                app.dependency_overrides[dep.call] = lambda: None
    bad = {"X-KBS-Background": "1", "X-KBS-Tenant": "tenant-a", "X-KBS-User": "different-user"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        for operation, body in [
            ("claim", {"worker_id": "worker"}),
            ("complete", {"worker_id": "worker", "kbs_reference": "EGM-local"}),
            ("fail", {"worker_id": "worker", "error": "synthetic", "retry": False}),
        ]:
            response = await client.post(f"/api/kbs/queue/synthetic-job/{operation}", headers=bad, json=body)
            assert response.status_code == 403
            assert response.json()["detail"] == "kbs_background_context_changed"
        response = await client.get("/api/kbs/background/jobs")
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_feed_rejects_malformed_cursor(context):
    _, user = context
    for created, job_id in [("not-a-date", "one"), (None, "one"), ("2026-11-04T00:00:00", "one")]:
        with pytest.raises(HTTPException) as error:
            await kbs.kbs_background_jobs(request(user), created, job_id, 20, user, None)
        assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_background_routes_require_normal_login_and_existing_report_permission():
    app = FastAPI()
    app.include_router(kbs.router)
    user = SimpleNamespace(id="user-a", tenant_id="tenant-a")
    headers = {"X-KBS-Background": "1", "X-KBS-Tenant": "tenant-a", "X-KBS-User": "user-a"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        for path in ("/background/context", "/background/jobs"):
            assert (await client.get("/api/kbs" + path, headers=headers)).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: user

        def denied():
            raise HTTPException(403, "view_reports_required")

        for route in app.routes:
            for dep in getattr(getattr(route, "dependant", None), "dependencies", []):
                if dep.name == "_perm":
                    app.dependency_overrides[dep.call] = denied
        for path in ("/background/context", "/background/jobs"):
            response = await client.get("/api/kbs" + path, headers=headers)
            assert response.status_code == 403 and response.json()["detail"] == "view_reports_required"
        response = await client.post("/api/kbs/queue/one/claim", headers=headers, json={"worker_id": "worker"})
        assert response.status_code == 403 and response.json()["detail"] == "view_reports_required"
