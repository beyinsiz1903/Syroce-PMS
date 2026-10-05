import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers import early_late_pricing


@pytest.mark.asyncio
async def test_settings_expose_tenant_currency(monkeypatch):
    monkeypatch.setattr(
        early_late_pricing,
        "db",
        SimpleNamespace(
            tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={})),
        ),
    )
    monkeypatch.setattr(
        early_late_pricing,
        "get_tenant_currency",
        AsyncMock(return_value=("EUR", "€")),
    )

    result = await early_late_pricing.get_pricing(
        current_user=SimpleNamespace(tenant_id="tenant-eur"),
    )

    assert result["_meta"]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_calculation_uses_tenant_currency_for_legacy_booking(monkeypatch):
    rule_config = {
        "early_checkin": [
            {
                "id": "early-flat",
                "label": "Erken",
                "from_hour": 0,
                "to_hour": 8,
                "charge_type": "flat",
                "charge_value": 25,
            }
        ],
        "late_checkout": [],
    }
    monkeypatch.setattr(
        early_late_pricing,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(
                find_one=AsyncMock(
                    return_value={"id": "booking-1", "total_amount": 100, "nights": 1}
                )
            ),
            tenant_settings=SimpleNamespace(
                find_one=AsyncMock(return_value={"early_late_pricing": rule_config})
            ),
        ),
    )
    monkeypatch.setattr(
        early_late_pricing,
        "get_tenant_currency",
        AsyncMock(return_value=("EUR", "€")),
    )

    result = await early_late_pricing.calculate(
        early_late_pricing.CalcRequest(
            booking_id="booking-1",
            direction="early_checkin",
            actual_hour=7,
        ),
        current_user=SimpleNamespace(tenant_id="tenant-eur"),
    )

    assert result["amount"] == 25
    assert result["currency"] == "EUR"


def test_currency_code_normalizes_legacy_tl():
    assert early_late_pricing._currency_code("TL", "EUR") == "TRY"
    assert early_late_pricing._currency_code(None, "USD") == "USD"
