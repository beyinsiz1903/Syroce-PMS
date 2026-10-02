from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.revenue.rms_router import pricing_strategy


class _FailIfReadDB:
    def __getattr__(self, _name):
        raise AssertionError("Açık onay olmadan veritabanına erişilmemeli")


class _Recommendations:
    def __init__(self, recommendation):
        self.recommendation = recommendation
        self.updates = []

    async def find_one(self, _query, _projection):
        return dict(self.recommendation)

    async def update_one(self, query, update):
        self.updates.append((query, update))


class _Collection:
    def __init__(self):
        self.records = []

    async def update_one(self, query, update, upsert=False):
        self.records.append((query, update, upsert))

    async def insert_one(self, document):
        self.records.append(dict(document))


@pytest.mark.asyncio
async def test_single_recommendation_requires_confirmation_before_any_database_access(monkeypatch):
    monkeypatch.setattr(pricing_strategy, "db", _FailIfReadDB())

    with pytest.raises(HTTPException) as exc:
        await pricing_strategy.apply_pricing_recommendation(
            "rec-1",
            request=pricing_strategy.ApplyPricingRecommendationRequest(),
            current_user=SimpleNamespace(tenant_id="tenant-1", id="user-1"),
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_single_recommendation_writes_tenant_scoped_audit_trace(monkeypatch):
    recommendations = _Recommendations(
        {
            "id": "rec-1",
            "tenant_id": "tenant-1",
            "status": "pending",
            "date": "2099-10-03",
            "room_type": "Deluxe",
            "current_rate": 2000,
            "suggested_rate": 2400,
            "reasoning": "Beklenen talep artışı",
        }
    )
    db = SimpleNamespace(
        rms_pricing_recommendations=recommendations,
        rate_calendar=_Collection(),
        rms_price_adjustments=_Collection(),
    )
    monkeypatch.setattr(pricing_strategy, "db", db)

    result = await pricing_strategy.apply_pricing_recommendation(
        "rec-1",
        request=pricing_strategy.ApplyPricingRecommendationRequest(apply_confirmed=True),
        current_user=SimpleNamespace(tenant_id="tenant-1", id="user-1"),
    )

    assert result["recommendation_id"] == "rec-1"
    assert recommendations.updates[0][0] == {"id": "rec-1", "tenant_id": "tenant-1"}
    assert db.rate_calendar.records[0][0]["tenant_id"] == "tenant-1"
    assert db.rms_price_adjustments.records[0]["old_rate"] == 2000
    assert db.rms_price_adjustments.records[0]["new_rate"] == 2400
    assert db.rms_price_adjustments.records[0]["recommendation_id"] == "rec-1"
