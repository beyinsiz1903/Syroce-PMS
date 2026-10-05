from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import cashier_router


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.limits = []

    async def to_list(self, limit):
        self.limits.append(limit)
        return self.rows


@pytest.mark.asyncio
async def test_currency_exchange_uses_all_receipts_and_prior_exchanges(monkeypatch):
    payment_cursor = _Cursor([{"received_currency": "EUR", "received_amount": 1}])
    exchange_cursor = _Cursor([])
    monkeypatch.setattr(
        cashier_router,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(find_one=AsyncMock(return_value={"id": "booking-a"})),
            payments=SimpleNamespace(find=lambda *_args, **_kwargs: payment_cursor),
            currency_exchanges=SimpleNamespace(find=lambda *_args, **_kwargs: exchange_cursor),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await cashier_router.currency_exchange(
            {"booking_id": "booking-a", "source_currency": "EUR", "source_amount": 2, "rate": 40},
            current_user=SimpleNamespace(tenant_id="tenant-a"),
            idempotency_key=None,
            _perm=None,
        )

    assert exc.value.status_code == 409
    assert payment_cursor.limits == [None]
    assert exchange_cursor.limits == [None]
