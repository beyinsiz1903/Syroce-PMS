import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-that-is-at-least-32-characters-long")

from core import utils


class _AsyncCursor:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        self._iterator = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_night_audit_revenue_keeps_currencies_separate_and_uses_posted_tax(monkeypatch):
    charges = [
        {"charge_category": "room", "total": 5600, "tax_amount": 600, "currency": "TRY"},
        {"charge_category": "room", "total": 100, "tax_amount": 10, "currency": "EUR"},
        {"charge_category": "restaurant", "total": 400, "tax_amount": 40, "currency": "TRY"},
        {"charge_category": "spa", "total": 50, "tax_amount": 5, "currency": "EUR"},
        {"charge_category": "room", "total": 9999, "currency": "TRY", "voided": True},
    ]

    class _Collection:
        def find(self, *_args, **_kwargs):
            return _AsyncCursor([row for row in charges if not row.get("voided")])

    monkeypatch.setattr(utils, "db", SimpleNamespace(folio_charges=_Collection()))

    result = await utils.night_audit_calculate_revenue("tenant-a", "2026-10-01")

    assert result["total_revenue"] is None
    assert result["total_revenue_by_currency"] == {"TRY": 6000.0, "EUR": 150.0}
    assert result["room_revenue_by_currency"] == {"TRY": 5600.0, "EUR": 100.0}
    assert result["fnb_revenue_by_currency"] == {"TRY": 400.0}
    assert result["other_revenue_by_currency"] == {"EUR": 50.0}
    assert result["tax_revenue_by_currency"] == {"TRY": 640.0, "EUR": 15.0}
    assert result["mixed_currency"] is True
