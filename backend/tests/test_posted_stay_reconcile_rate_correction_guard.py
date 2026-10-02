"""A posted-stay reconciliation must not undo an approved correction."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import reservation_detail


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self._iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as error:
            raise StopAsyncIteration from error


class _Bookings:
    async def find_one(self, query, projection):
        return {
            "id": "booking-1",
            "check_in": "2026-10-01",
            "check_out": "2026-10-03",
            "total_amount": 10000,
        }


class _Folios:
    def find(self, query, projection):
        return _Rows([{"id": "folio-1"}])


class _Payments:
    async def find_one(self, query, projection):
        assert {"payment_type": "rate_correction"} in query["$and"]
        return {"id": "correction-1"}


class _MustNotReadCharges:
    def find(self, *args, **kwargs):
        raise AssertionError("Onaylı düzeltmeden sonra tahakkuklar okunmamalı")


@pytest.mark.asyncio
async def test_reconcile_rejects_booking_with_active_rate_correction(monkeypatch):
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *args: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *args: None)
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=_Bookings(),
            folios=_Folios(),
            payments=_Payments(),
            folio_charges=_MustNotReadCharges(),
        ),
    )

    with pytest.raises(HTTPException) as error:
        await reservation_detail.reconcile_posted_stay_total(
            "booking-1",
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            _perm=None,
        )

    assert error.value.status_code == 409
    assert "fiyat düzeltmesi" in error.value.detail.lower()
