"""Agency reconciliation must reflect what the hotel changed in the PMS."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.marketplace_ledger_sync import ledger_patch_from_booking, refresh_ledger_from_pms
from routers.marketplace_b2b import _csv_text

LEDGER = {
    "id": "b1",
    "tenant_id": "t1",
    "agency_id": "a1",
    "status": "confirmed",
    "payment_status": "pending",
    "check_in": "2026-11-01",
    "check_out": "2026-11-03",
    "total_amount": 1000.0,
    "commission_pct": 10.0,
    "commission_amount": 100.0,
    "syroce_b2b_fee_pct": 2.0,
    "syroce_b2b_fee_amount": 20.0,
    "net_to_hotel": 900.0,
}


def test_in_sync_booking_produces_no_patch():
    booking = {"status": "confirmed", "payment_status": "pending", "check_in": "2026-11-01T14:00:00+00:00",
               "check_out": "2026-11-03T12:00:00+00:00", "total_amount": 1000}
    assert ledger_patch_from_booking(LEDGER, booking) == {}


def test_amount_change_recomputes_commission_fee_and_net():
    patch = ledger_patch_from_booking(LEDGER, {"total_amount": 1500, "check_out": "2026-11-04T12:00:00+00:00"})
    assert patch == {
        "check_out": "2026-11-04",
        "total_amount": 1500.0,
        "commission_amount": 150.0,
        "net_to_hotel": 1350.0,
        "syroce_b2b_fee_amount": 30.0,
    }


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


@pytest.mark.asyncio
async def test_refresh_persists_pms_cancellation_and_ignores_other_tenants():
    other = {**LEDGER, "id": "b2"}
    live = [
        {"id": "b1", "tenant_id": "t1", "status": "cancelled", "total_amount": 1000},
        {"id": "b2", "tenant_id": "someone-else", "status": "cancelled"},
    ]
    ledger = SimpleNamespace(update_one=AsyncMock())
    sysdb = SimpleNamespace(bookings=SimpleNamespace(find=lambda *a: _Cursor(live)), marketplace_bookings=ledger)

    refreshed = await refresh_ledger_from_pms(sysdb, [dict(LEDGER), other])

    assert refreshed[0]["status"] == "cancelled"
    assert refreshed[1]["status"] == "confirmed"
    ledger.update_one.assert_awaited_once()
    selector, update = ledger.update_one.await_args.args
    assert selector == {"id": "b1", "agency_id": "a1"}
    assert update["$set"]["status"] == "cancelled"


@pytest.mark.parametrize("value", ["=cmd|'/c calc'!A1", "+1+1", "-2", "@SUM(A1)", "\tx"])
def test_csv_text_neutralises_formula_prefixes(value):
    assert _csv_text(value).startswith("'")


def test_csv_text_keeps_plain_names_and_forces_codes():
    assert _csv_text("Syroce Demo Hotel") == "Syroce Demo Hotel"
    assert _csv_text("MKT-0001", force_text=True) == "'MKT-0001"
    assert _csv_text(None) == ""
