"""Legacy lifecycle rows remain visible without falsifying OTA queue age."""
from datetime import UTC, datetime, timedelta
from inspect import unwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from routers import outbox_admin


@pytest.mark.asyncio
async def test_status_keeps_total_and_separates_legacy_from_ota_worker_rows(monkeypatch):
    now = datetime.now(UTC)

    async def count(query):
        if query == {"status": "pending"}:
            return 3
        if query == {"status": "pending", "max_attempts": {"$exists": False}}:
            return 2
        return 0

    async def find_one(query, _projection, **_kwargs):
        if query.get("status") == {"$in": ["pending", "retry"]}:
            assert query["max_attempts"] == {"$exists": True}
            return {"created_at": (now - timedelta(seconds=5)).isoformat()}
        return None

    async def failures():
        if False:
            yield {}

    events = SimpleNamespace(count_documents=AsyncMock(side_effect=count),
        find_one=AsyncMock(side_effect=find_one), aggregate=MagicMock(return_value=failures()))
    # No mutation or dispatch methods exist on the fake database.
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    result = await unwrap(outbox_admin.outbox_status)()
    assert result.pending == 3
    assert result.legacy_pending == 2
    assert result.ota_pending == 1
    assert 4 <= result.oldest_pending_seconds <= 10
