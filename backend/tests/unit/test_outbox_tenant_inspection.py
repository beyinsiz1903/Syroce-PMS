"""Read-only super-admin inspection can be bounded to one property/tenant."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import outbox_admin


@pytest.fixture
def inspection(monkeypatch):
    rows = [
        {"id": "demo-new", "tenant_id": "demo", "provider": "exely", "status": "pending", "created_at": "2026-10-28"},
        {"id": "other", "tenant_id": "other", "provider": "exely", "status": "pending", "created_at": "2026-10-27"},
        {"id": "demo-old", "tenant_id": "demo", "provider": None, "status": "pending", "created_at": "2026-10-26"},
        {"id": "demo-failed", "tenant_id": "demo", "provider": "exely", "status": "failed", "created_at": "2026-10-25"},
    ]

    class Cursor:
        def __init__(self, query):
            self.rows = [row.copy() for row in rows if all(row.get(k) == v for k, v in query.items())]
            self.offset = 0
            self.limit_count = 200

        def sort(self, key, direction):
            self.rows.sort(key=lambda row: row[key], reverse=direction == -1)
            return self

        def skip(self, offset):
            self.offset = offset
            return self

        def limit(self, limit):
            self.limit_count = limit
            return self

        async def to_list(self, _limit):
            return self.rows[self.offset:self.offset + self.limit_count]

    events = SimpleNamespace(
        find=MagicMock(side_effect=lambda query, projection: Cursor(query)),
        count_documents=AsyncMock(side_effect=lambda query: sum(all(row.get(k) == v for k, v in query.items()) for row in rows)),
    )
    # This fake intentionally has no mutation/dispatch/worker methods.
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    app = FastAPI()
    app.include_router(outbox_admin.outbox_admin_router, prefix="/api")
    app.dependency_overrides[outbox_admin.require_super_admin] = lambda: True
    with TestClient(app) as client:
        yield client, events, app


@pytest.mark.parametrize("query,expected", [
    ("tenant_id=demo", ["demo-new", "demo-old", "demo-failed"]),
    ("tenant_id=demo&status=pending", ["demo-new", "demo-old"]),
    ("tenant_id=demo&provider=exely", ["demo-new", "demo-failed"]),
    ("tenant_id=demo&status=failed&provider=exely", ["demo-failed"]),
    ("tenant_id=missing", []),
    ("tenant_id=%24ne", []),
])
def test_requested_tenant_is_applied_to_both_rows_and_count(inspection, query, expected):
    client, events, _app = inspection
    response = client.get(f"/api/outbox/events?{query}")
    assert response.status_code == 200
    data = response.json()
    assert [row["id"] for row in data["events"]] == expected
    assert data["total"] == len(expected)
    database_query = events.find.call_args.args[0]
    assert database_query["tenant_id"] in ("demo", "missing", "$ne")
    assert events.find.call_args.args[1] == {"_id": 0}
    events.count_documents.assert_awaited_once_with(database_query)


def test_tenant_filter_preserves_pagination_and_filtered_total(inspection):
    client, events, _app = inspection
    response = client.get("/api/outbox/events?tenant_id=demo&status=pending&limit=1&offset=1")
    assert response.status_code == 200
    assert response.json() == {"events": [{"id": "demo-old", "tenant_id": "demo", "provider": None, "status": "pending", "created_at": "2026-10-26"}], "total": 2, "limit": 1, "offset": 1}
    events.count_documents.assert_awaited_once_with({"tenant_id": "demo", "status": "pending"})


def test_explicitly_unfiltered_super_admin_view_keeps_existing_behavior(inspection):
    client, events, _app = inspection
    data = client.get("/api/outbox/events?status=pending").json()
    assert [row["id"] for row in data["events"]] == ["demo-new", "other", "demo-old"]
    assert data["total"] == 3
    events.count_documents.assert_awaited_once_with({"status": "pending"})


@pytest.mark.parametrize("tenant", ["", "   ", "x" * 129])
def test_invalid_tenant_filter_never_falls_back_to_global_view(inspection, tenant):
    client, events, _app = inspection
    response = client.get("/api/outbox/events", params={"tenant_id": tenant})
    assert response.status_code == 422
    events.find.assert_not_called()
    events.count_documents.assert_not_awaited()


def test_tenant_filter_does_not_remove_existing_super_admin_guard(inspection):
    client, events, app = inspection

    def deny():
        raise HTTPException(403, "admin required")

    app.dependency_overrides[outbox_admin.require_super_admin] = deny
    response = client.get("/api/outbox/events?tenant_id=demo")
    assert response.status_code == 403
    events.find.assert_not_called()
    events.count_documents.assert_not_awaited()
