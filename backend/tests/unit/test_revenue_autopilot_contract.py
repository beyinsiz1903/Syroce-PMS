from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from modules.revenue_autopilot.service import RevenueAutopilotService
from routers.revenue_autopilot_v2 import AutopilotPolicyUpdate, ProcessRecommendationReq


class Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if all(not isinstance(value, dict) and doc.get(key) == value or isinstance(value, dict) and value.get("$ne") != doc.get(key) for key, value in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        upserted_id = None
        if doc is None and upsert:
            doc = dict(query)
            doc.update(update.get("$setOnInsert", {}))
            self.docs.append(doc)
            upserted_id = doc.get("id")
        target = next((item for item in self.docs if item.get("id") == doc.get("id")), doc)
        target.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=0 if upserted_id else 1, modified_count=1, upserted_id=upserted_id)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class DB:
    def __init__(self):
        self.rate_plans = Collection([{"id": "rp1", "tenant_id": "t1", "room_type": "Standard", "is_active": True}])
        self.rate_overrides = Collection()
        self.audit_logs = Collection()


@pytest.mark.asyncio
async def test_autopilot_applies_dated_internal_override_without_provider_write():
    db = DB()
    result = await RevenueAutopilotService(db)._apply_price("t1", "Standard", "2026-09-01", 100, 120)
    assert result["success"] is True
    assert result["provider_write"] is False
    assert db.rate_plans.docs[0].get("base_price") is None
    assert db.rate_overrides.docs[0]["date"] == "2026-09-01"
    assert db.rate_overrides.docs[0]["new_rate"] == 120
    assert db.rate_overrides.docs[0]["provider_sync_status"] == "not_requested"


def test_autopilot_request_and_policy_reject_invalid_values():
    with pytest.raises(ValidationError):
        ProcessRecommendationReq(
            room_type="Standard",
            target_date=date(2026, 9, 1),
            current_price=100,
            recommended_price=-1,
            confidence=0.8,
        )
    with pytest.raises(ValidationError):
        AutopilotPolicyUpdate(confidence_threshold_queue=0.9, confidence_threshold_auto=0.8)

