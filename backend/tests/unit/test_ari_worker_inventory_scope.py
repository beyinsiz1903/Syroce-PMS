"""The background worker has no HTTP middleware tenant context."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import tenant_db
from domains.channel_manager.exely_inventory_source import assert_exely_inventory_source
from tests.test_exely_inventory_source import TENANT, update
from tests.test_exely_inventory_source import inventory as inventory
from workers import ari_push_worker as worker


def one_tick(monkeypatch, tenants, push):
    queue = SimpleNamespace(aggregate=lambda _: SimpleNamespace(to_list=AsyncMock(
        return_value=[{"_id": tid} for tid in tenants])))
    monkeypatch.setattr(worker, "db", {"ari_change_sets": queue})
    monkeypatch.setattr(worker, "push_pending_changes", push)
    monkeypatch.setattr(worker, "get_failure_tracker", lambda: SimpleNamespace(record=AsyncMock()))
    monkeypatch.setattr(worker, "asyncio", SimpleNamespace(sleep=AsyncMock(side_effect=asyncio.CancelledError)))


@pytest.mark.asyncio
async def test_worker_can_validate_seven_after_second_booking_without_http_context(inventory, monkeypatch):
    monkeypatch.setattr(tenant_db, "STRICT_TENANT_MODE", True)
    for row in inventory.calendar:
        if row["room_type_code"] == "DLX":
            row["availability"] = 9
    inventory.db.bookings.rows.extend([{"id": str(i), "tenant_id": TENANT, "room_id": None,
        "room_type": "Deluxe", "status": "confirmed", "check_in": "2026-11-23T14:00:00",
        "check_out": "2026-11-25T12:00:00"} for i in range(2)])
    saved = deepcopy(inventory.calendar)

    class RawDatabase:
        def __getitem__(self, name):
            return getattr(inventory.db, name)

    scoped = tenant_db.TenantAwareDBProxy(RawDatabase())
    validated = []

    async def push(tid, limit):
        assert limit == 20
        await assert_exely_inventory_source(scoped, tid, [update(7).model_dump()])
        validated.append(tid)
        return {"pushed": 1, "failed": 0}

    one_tick(monkeypatch, [TENANT], push)
    with tenant_db.tenant_context(None):
        with pytest.raises(asyncio.CancelledError):
            await worker.ari_push_worker_loop()
        assert tenant_db.get_current_tenant_id() is None
    assert validated == [TENANT]
    assert inventory.calendar == saved


@pytest.mark.asyncio
async def test_worker_scopes_each_tenant_and_restores_context_even_after_failure(monkeypatch):
    seen = []

    async def push(tid, limit):
        seen.append((tid, tenant_db.get_current_tenant_id()))
        if tid == "first":
            raise RuntimeError("injected first-tenant failure")
        return {"pushed": 1, "failed": 0}

    one_tick(monkeypatch, ["first", "second"], push)
    with tenant_db.tenant_context("caller"):
        with pytest.raises(asyncio.CancelledError):
            await worker.ari_push_worker_loop()
        assert tenant_db.get_current_tenant_id() == "caller"
    assert seen == [("first", "first"), ("second", "second")]
