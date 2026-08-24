from datetime import UTC, datetime

import pytest

from domains.ai.reputation_manager import ReputationManager


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    async def to_list(self, _limit):
        return list(self.rows)


class Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, _projection=None):
        tenant_id = query.get("tenant_id")
        return Cursor([row for row in self.rows if row.get("tenant_id") == tenant_id])


class DB:
    def __init__(self, rows):
        self.external_reviews = Collection(rows)


@pytest.mark.asyncio
async def test_reputation_uses_single_external_review_source_and_normalizes_scales():
    now = datetime.now(UTC).isoformat()
    manager = ReputationManager(DB([
        {"tenant_id": "t1", "platform": "booking", "rating": 8, "rating_scale": 10, "review_date": now},
        {"tenant_id": "t1", "platform": "google", "rating": 5, "rating_scale": 5, "review_date": now, "response_status": "responded"},
    ]))
    overview = await manager.aggregate_reviews("t1")
    trends = await manager.get_reputation_trends("t1", 30)
    alerts = await manager.detect_negative_reviews("t1")
    assert overview["overall_rating"] == 4.5
    assert overview["responded_reviews"] == 1
    assert trends["total_reviews"] == 2
    assert alerts == []

