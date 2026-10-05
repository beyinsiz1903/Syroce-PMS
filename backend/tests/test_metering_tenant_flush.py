from collections import defaultdict
from types import SimpleNamespace

import pytest

from core import metering
from core.tenant_db import tenant_context


@pytest.mark.asyncio
async def test_flush_buffer_uses_each_event_tenant_not_request_tenant(monkeypatch):
    writes = []

    class UsageCollection:
        def __init__(self, tenant_id):
            self.tenant_id = tenant_id

        async def update_one(self, filter_doc, update_doc, *, upsert):
            assert filter_doc["tenant_id"] == self.tenant_id
            assert update_doc["$setOnInsert"]["tenant_id"] == self.tenant_id
            assert upsert is True
            writes.append((self.tenant_id, filter_doc["event_type"], update_doc["$inc"]["count"]))

    monkeypatch.setattr(
        metering,
        "get_db_for_tenant",
        lambda tenant_id: SimpleNamespace(usage_daily=UsageCollection(tenant_id)),
    )
    monkeypatch.setattr(
        metering,
        "_buffer",
        defaultdict(lambda: defaultdict(int), {
            "tenant-a": defaultdict(int, {"api_call": 2}),
            "tenant-b": defaultdict(int, {"reservation_created": 1}),
        }),
    )

    # A tenant-b request can be the one that triggers a global buffer flush.
    with tenant_context("tenant-b"):
        await metering.flush_buffer()

    assert writes == [
        ("tenant-a", "api_call", 2),
        ("tenant-b", "reservation_created", 1),
    ]
    assert not metering._buffer


@pytest.mark.asyncio
async def test_usage_summary_reports_active_users_and_last_activity(monkeypatch):
    class AggregateResult:
        async def to_list(self, _limit):
            return [{"_id": "reservation_created", "total": 6}]

    class UsageDaily:
        def aggregate(self, _pipeline):
            return AggregateResult()

        async def find_one(self, _query, _projection, *, sort):
            assert sort == [("date", -1), ("updated_at", -1)]
            return {"date": "2026-10-01", "updated_at": "2026-10-01T09:15:00+00:00"}

    class CountCollection:
        def __init__(self, total, active=None):
            self.total = total
            self.active = total if active is None else active

        async def count_documents(self, query):
            return self.active if "is_active" in query else self.total

    tenant_db = SimpleNamespace(
        usage_daily=UsageDaily(),
        rooms=CountCollection(20),
        users=CountCollection(5, active=3),
        guests=CountCollection(80),
    )
    monkeypatch.setattr(metering, "get_db_for_tenant", lambda tenant_id: tenant_db)

    result = await metering.get_tenant_usage_summary("tenant-a", days=30)

    assert result["events"] == {"reservation_created": 6}
    assert result["current_resources"]["users"] == 5
    assert result["current_resources"]["active_users"] == 3
    assert result["last_activity_at"] == "2026-10-01T09:15:00+00:00"
