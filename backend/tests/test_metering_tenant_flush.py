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
