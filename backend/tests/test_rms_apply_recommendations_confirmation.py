from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.revenue.rms_router import pricing_strategy


class _FailIfReadDB:
    """A rejected bulk apply must not read or mutate tenant recommendations."""

    def __getattr__(self, _name):
        raise AssertionError("Açık onay olmadan veritabanına erişilmemeli")


@pytest.mark.asyncio
async def test_bulk_recommendation_apply_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(pricing_strategy, "db", _FailIfReadDB())

    with pytest.raises(HTTPException) as exc:
        await pricing_strategy.apply_all_recommendations(
            request=pricing_strategy.ApplyRecommendationsRequest(),
            current_user=SimpleNamespace(tenant_id="tenant-1", id="user-1"),
        )

    assert exc.value.status_code == 409
    assert "açık onay" in str(exc.value.detail).lower()
