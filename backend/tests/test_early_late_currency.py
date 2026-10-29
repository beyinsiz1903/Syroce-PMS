import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

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


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_nights", [None, 1, 99])
async def test_late_checkout_derives_five_nights_from_stay_not_stale_cache(monkeypatch, stored_nights):
    booking = {"check_in": "2026-10-21T14:00:00+03:00", "check_out": "2026-10-26T12:00:00+03:00",
               "total_amount": 560, "currency": "USD", "nights": stored_nights}
    monkeypatch.setattr(early_late_pricing, "db", SimpleNamespace(
        bookings=SimpleNamespace(find_one=AsyncMock(return_value=booking)),
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={}))))
    monkeypatch.setattr(early_late_pricing, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    result = await early_late_pricing.calculate(
        early_late_pricing.CalcRequest(booking_id="synthetic", direction="late_checkout", actual_hour=14),
        current_user=SimpleNamespace(tenant_id="t"))
    assert (result["nights"], result["nightly_rate"], result["amount"], result["currency"]) == (5, 112, 56, "USD")
    assert booking["total_amount"] == 560  # Calculation does not rewrite source prices.


@pytest.mark.parametrize("booking", [
    {"check_in": "invalid", "check_out": "2026-10-26", "nights": 1},
    {"check_in": "2026-10-26", "check_out": "2026-10-26"},
    {"check_in": "2026-10-27", "check_out": "2026-10-26"},
    {"check_in": "2026-10-21"}, {"nights": None}, {"nights": 1.5}, {"nights": 0},
    {"nights": 1, "total_amount": "NaN"}, {"nights": 1, "total_amount": -10},
])
def test_invalid_stay_or_price_cannot_silently_become_one_night(booking):
    with pytest.raises(HTTPException) as exc:
        early_late_pricing._stay_pricing_base({"total_amount": 560, **booking})
    assert exc.value.status_code == 422


def test_zero_subtotal_is_not_replaced_by_a_nonzero_fallback():
    nights, total, source = early_late_pricing._stay_pricing_base({"nights": 5, "subtotal": 0, "base_amount": 560})
    assert (nights, total, source) == (5, 0, "subtotal")


@pytest.mark.asyncio
async def test_flat_tenant_price_is_not_relabelled_as_a_foreign_booking_currency(monkeypatch):
    monkeypatch.setattr(early_late_pricing, "db", SimpleNamespace(
        bookings=SimpleNamespace(find_one=AsyncMock(return_value={"currency": "USD", "nights": 1, "total_amount": 100})),
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={}))))
    monkeypatch.setattr(early_late_pricing, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    with pytest.raises(HTTPException) as exc:
        await early_late_pricing.calculate(
            early_late_pricing.CalcRequest(booking_id="synthetic", direction="early_checkin", actual_hour=7),
            current_user=SimpleNamespace(tenant_id="t"))
    assert exc.value.status_code == 422
