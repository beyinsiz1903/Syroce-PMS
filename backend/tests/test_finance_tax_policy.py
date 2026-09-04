from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers.finance.accounting import folio_charge_to_invoice_items
from routers.finance import konaklama_vergisi_core as tax_core


class _AsyncCursor:
    def __init__(self, documents):
        self._documents = documents

    async def to_list(self, length=None):
        return list(self._documents)


def test_folio_invoice_lines_keep_accommodation_tax_outside_vat_base():
    lines = folio_charge_to_invoice_items(
        {
            "charge_category": "room",
            "description": "Konaklama Bedeli",
            "amount": 1_000,
            "total": 1_110,
            "tax_breakdown": {"vat": 100, "accommodation_tax": 10},
        }
    )

    assert lines == [
        {
            "description": "Konaklama Bedeli",
            "category": "room",
            "quantity": 1,
            "unit_price": 1_000.0,
            "vat_rate": 10.0,
            "total": 1_100.0,
        },
        {
            "description": "Konaklama Vergisi",
            "category": "city_tax",
            "tax_type": "accommodation_tax",
            "quantity": 1,
            "unit_price": 10.0,
            "vat_rate": 0.0,
            "total": 10.0,
        },
    ]


@pytest.mark.parametrize(
    ("charge", "expected_rate"),
    [
        ({"charge_category": "food", "description": "Akşam yemeği", "amount": 100}, 10.0),
        ({"charge_category": "food_beverage", "description": "Kahvaltı", "amount": 100}, 10.0),
        ({"charge_category": "beverage", "description": "Şarap", "amount": 100}, 20.0),
        ({"charge_category": "other", "description": "Transfer", "amount": 100}, 20.0),
    ],
)
def test_folio_invoice_lines_apply_service_specific_vat(charge, expected_rate):
    assert folio_charge_to_invoice_items(charge)[0]["vat_rate"] == expected_rate


@pytest.mark.asyncio
async def test_accommodation_tax_respects_config_effective_date(monkeypatch):
    monkeypatch.setattr(
        tax_core,
        "load_tax_config",
        AsyncMock(
            return_value={
                "active": True,
                "rate_percent": 1,
                "effective_from": "2026-05-01",
            }
        ),
    )

    assert await tax_core.get_accommodation_tax_rate("tenant", "2026-04-30") == 0.0
    assert await tax_core.get_accommodation_tax_rate("tenant", "2026-05-01") == 0.01


@pytest.mark.asyncio
async def test_checkout_does_not_post_accommodation_tax_twice(monkeypatch):
    folio_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: _AsyncCursor(
            [
                {
                    "amount": 1_000,
                    "tax_breakdown": {"vat": 100, "accommodation_tax": 10},
                }
            ]
        ),
        insert_one=AsyncMock(),
    )
    postings = SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock())
    fake_db = SimpleNamespace(
        folios=SimpleNamespace(find_one=AsyncMock(return_value={"id": "folio-1"})),
        accommodation_tax_postings=postings,
        city_tax_rules=SimpleNamespace(
            find_one=AsyncMock(return_value={"active": True, "rate_percent": 1, "auto_post": True})
        ),
        folio_charges=folio_charges,
        bookings=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(tax_core, "db", fake_db)

    result = await tax_core.post_konaklama_vergisi_to_folio(
        "tenant",
        "folio-1",
        "checkout:user-1",
    )

    assert result["ok"] is True
    assert result["already_included"] is True
    assert result["posted"] is False
    folio_charges.insert_one.assert_not_awaited()
    postings.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_checkout_keeps_legacy_tax_inclusive_room_charge_without_breakdown(monkeypatch):
    """A tax-inclusive reconciliation row is gross even without old details."""
    folio_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: _AsyncCursor(
            [{"amount": 5833.34, "tax_inclusive": True, "tax_breakdown": {}}]
        ),
        insert_one=AsyncMock(),
    )
    postings = SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock())
    fake_db = SimpleNamespace(
        folios=SimpleNamespace(find_one=AsyncMock(return_value={"id": "folio-1"})),
        accommodation_tax_postings=postings,
        city_tax_rules=SimpleNamespace(
            find_one=AsyncMock(return_value={"active": True, "rate_percent": 0.2576, "auto_post": True})
        ),
        folio_charges=folio_charges,
        bookings=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(tax_core, "db", fake_db)

    result = await tax_core.post_konaklama_vergisi_to_folio("tenant", "folio-1", "checkout:user-1")

    assert result["ok"] is True
    assert result["already_included"] is True
    assert result["posted"] is False
    folio_charges.insert_one.assert_not_awaited()
