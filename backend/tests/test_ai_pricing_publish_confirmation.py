from types import SimpleNamespace

import pytest

from domains.revenue.pricing_router import ai_pricing


class _FailIfReadDB:
    """The confirmation guard must return before touching tenant data."""

    def __getattr__(self, _name):
        raise AssertionError("Yayın onayı olmadan veritabanına erişilmemeli")


@pytest.mark.asyncio
async def test_ai_rate_publish_requires_explicit_confirmation_before_database_access(monkeypatch):
    monkeypatch.setattr(ai_pricing, "db", _FailIfReadDB())

    result = await ai_pricing.auto_publish_rates_based_on_forecast(
        start_date="2026-10-02",
        end_date="2026-10-31",
        dry_run=False,
        publish_confirmed=False,
        current_user=SimpleNamespace(tenant_id="tenant-1", email="rate-manager@example.com"),
    )

    assert result["success"] is False
    assert result["confirmation_required"] is True
    assert result["rates_persisted"] == 0
    assert result["outbox_events_emitted"] == 0
    assert result["published_rates"] == []
