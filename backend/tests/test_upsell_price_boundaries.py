"""Price-settings boundaries: rejected requests must not mutate stored settings."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.guest.experience_router import upsell


@pytest.fixture
def settings(monkeypatch):
    collection = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
    monkeypatch.setattr(upsell, "db", SimpleNamespace(upsell_settings=collection))
    monkeypatch.setattr(upsell, "create_audit_log", AsyncMock())
    return collection


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [10**500, True, "NaN", "Infinity", -1, 1_000_001, 1.001, "", None, [], {}])
async def test_invalid_settings_are_controlled_400_without_write(settings, raw):
    with pytest.raises(HTTPException) as error:
        await upsell.update_upsell_settings({"prices": {"early_checkin": raw}}, SimpleNamespace(tenant_id="qa", id="operator"), None)
    assert error.value.status_code == 400
    settings.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [0, "0", 25, "25.50", 1_000_000])
async def test_valid_price_is_tenant_scoped_and_partial_without_changing_other_fields(settings, raw):
    await upsell.update_upsell_settings({"prices": {"early_checkin": raw}}, SimpleNamespace(tenant_id="qa", id="operator"), None)
    query, update = settings.update_one.await_args.args
    assert query == {"tenant_id": "qa"}
    assert update["$set"]["prices.early_checkin"] == float(raw)
    assert not any(key.startswith("prices.") and key != "prices.early_checkin" for key in update["$set"])


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [True, "Infinity", float("inf"), 10**500, -1, 1.001])
async def test_corrupt_legacy_settings_cannot_become_generated_offer_prices(settings, raw):
    settings.find_one.return_value = {"prices": {"early_checkin": raw, "late_checkout": 0}}
    result = await upsell._get_upsell_prices("qa")
    assert result["early_checkin"] == upsell.DEFAULT_UPSELL_PRICES["early_checkin"]
    assert result["late_checkout"] == 0
    settings.update_one.assert_not_awaited()
