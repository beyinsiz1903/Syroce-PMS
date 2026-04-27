"""Tests: Task #32 — Web push gönderim sayaçları (rollup)."""
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import domains.guest.messaging.web_push_metrics as wpm
from domains.guest.messaging.web_push_metrics import (
    SYSTEM_TENANT,
    get_metrics_summary,
    record_dispatch,
    record_scheduled_prune,
)


@pytest.fixture(autouse=True)
def _reset_index_flag():
    """ensure_indexes flag'ı testler arası izole olsun."""
    wpm._indexes_ensured = False
    yield
    wpm._indexes_ensured = False


def _mock_db():
    db = MagicMock()
    coll = MagicMock()
    coll.update_one = AsyncMock()
    coll.create_index = AsyncMock()
    coll.find = MagicMock()
    db.__getitem__ = MagicMock(return_value=coll)
    return db, coll


@pytest.mark.asyncio
async def test_record_dispatch_upsert_and_inc():
    db, coll = _mock_db()
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    await record_dispatch(
        db, tenant_id="t1", attempted=5, sent=4, failed=1, pruned=0, now=now,
    )
    coll.create_index.assert_awaited_once()
    coll.update_one.assert_awaited_once()
    args, kwargs = coll.update_one.call_args
    flt, update = args[0], args[1]
    assert flt == {"tenant_id": "t1", "date": "2026-04-27"}
    assert update["$inc"] == {"attempted": 5, "sent": 4, "failed": 1}
    assert "pruned" not in update["$inc"]  # zero atlanmalı
    assert kwargs.get("upsert") is True
    assert update["$set"]["last_updated"] == now.isoformat()
    assert update["$setOnInsert"] == {"tenant_id": "t1", "date": "2026-04-27"}


@pytest.mark.asyncio
async def test_record_dispatch_skips_when_all_zero():
    db, coll = _mock_db()
    await record_dispatch(
        db, tenant_id="t1", attempted=0, sent=0, failed=0, pruned=0,
    )
    coll.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_scheduled_prune_uses_system_tenant():
    db, coll = _mock_db()
    now = datetime(2026, 4, 27, tzinfo=UTC)
    await record_scheduled_prune(db, count=12, now=now)
    args, _ = coll.update_one.call_args
    assert args[0] == {"tenant_id": SYSTEM_TENANT, "date": "2026-04-27"}
    assert args[1]["$inc"] == {"scheduled_pruned": 12}


@pytest.mark.asyncio
async def test_record_scheduled_prune_skips_zero():
    db, coll = _mock_db()
    await record_scheduled_prune(db, count=0)
    coll.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_scheduled_prune_explicit_tenant():
    db, coll = _mock_db()
    await record_scheduled_prune(db, count=3, tenant_id="tX")
    args, _ = coll.update_one.call_args
    assert args[0]["tenant_id"] == "tX"


@pytest.mark.asyncio
async def test_record_dispatch_swallows_db_error(caplog):
    db, coll = _mock_db()
    coll.update_one = AsyncMock(side_effect=RuntimeError("mongo down"))
    with caplog.at_level("ERROR", logger="domains.guest.messaging.web_push_metrics"):
        # raise etmemeli — best-effort
        await record_dispatch(db, tenant_id="t1", attempted=1, sent=1,
                              failed=0, pruned=0)
    assert any("failed to increment" in r.getMessage() for r in caplog.records)


def _async_iter(items):
    class _It:
        def __init__(self, lst):
            self._it = iter(lst)
        def __aiter__(self):
            return self
        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration
    return _It(items)


@pytest.mark.asyncio
async def test_get_metrics_summary_aggregates_correctly():
    db, coll = _mock_db()
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    today = "2026-04-27"
    yesterday = "2026-04-26"
    older = "2026-04-20"

    docs = [
        {"tenant_id": "t1", "date": today,
         "attempted": 5, "sent": 4, "failed": 1, "pruned": 0},
        {"tenant_id": "t1", "date": yesterday,
         "attempted": 10, "sent": 8, "failed": 2, "pruned": 1},
        {"tenant_id": "t1", "date": older,
         "attempted": 3, "sent": 3, "failed": 0, "pruned": 0},
        # System tenant — yaş tabanlı temizlik (cross-tenant; tenant
        # totals'a karışmamalı, ayrı alanda dönmeli).
        {"tenant_id": SYSTEM_TENANT, "date": today,
         "scheduled_pruned": 7},
        {"tenant_id": SYSTEM_TENANT, "date": older,
         "scheduled_pruned": 12},
    ]
    coll.find = MagicMock(return_value=_async_iter(docs))

    summary = await get_metrics_summary(db, tenant_id="t1", days=30, now=now)

    assert summary["tenant_id"] == "t1"
    assert summary["range_days"] == 30
    # Tenant totals: yalnızca tenant docları
    assert summary["totals"] == {"attempted": 18, "sent": 15, "failed": 3, "pruned": 1}
    # Bugün: yalnızca tenant'ın bugünkü docu
    assert summary["today"] == {"attempted": 5, "sent": 4, "failed": 1, "pruned": 0}
    # Sistem tarafı ayrı alanda
    assert summary["system_scheduled_pruned"] == 19
    assert summary["system_scheduled_pruned_today"] == 7
    # Tenant totals scheduled_pruned alanı içermemeli (cross-tenant sızıntı yok)
    assert "scheduled_pruned" not in summary["totals"]
    assert "scheduled_pruned" not in summary["today"]
    # Daily seri sadece tenant satırlarını içermeli, sıralı.
    assert [d["date"] for d in summary["daily"]] == [older, yesterday, today]


@pytest.mark.asyncio
async def test_get_metrics_summary_clamps_days():
    db, coll = _mock_db()
    coll.find = MagicMock(return_value=_async_iter([]))
    s_low = await get_metrics_summary(db, tenant_id="t1", days=0)
    s_high = await get_metrics_summary(db, tenant_id="t1", days=10_000)
    assert s_low["range_days"] == 1
    assert s_high["range_days"] == 365
