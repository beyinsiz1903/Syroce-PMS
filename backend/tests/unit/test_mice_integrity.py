from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core.mice_integrity import overlaps, peak_usage, protect_paid_schedule
from routers import mice

USER = SimpleNamespace(tenant_id="hotel-a", role="admin", roles=["admin"], username="tester", id="user-a")


def event(**patch):
    return mice.EventIn(**{"name": "Conference", "client_name": "Example Co", "start_date": "2026-10-21", "end_date": "2026-10-21", **patch})


def window(start="10:00", end="12:00", **extra):
    return {"space_id": "hall-a", "starts_at": f"2026-10-21T{start}", "ends_at": f"2026-10-21T{end}", **extra}


class Cursor:
    def __init__(self, rows): self.rows = rows
    def __aiter__(self): self.it = iter(self.rows); return self
    async def __anext__(self):
        try: return next(self.it)
        except StopIteration: raise StopAsyncIteration from None
    async def to_list(self, length=None): return self.rows
    def sort(self, *args): return self


@pytest.mark.parametrize("patch", [
    {"name": "   "}, {"client_name": ""}, {"end_date": "2026-10-20"},
    {"space_bookings": [window(end="09:00")]},
    {"space_bookings": [window(), window("11:00", "13:00")]},
    {"space_bookings": [window(setup_style="invalid")]},
    {"space_bookings": [window(starts_at="2026-10-20T10:00")]},
    {"resources": [{"name": "Lunch", "quantity": -1}]},
    {"resources": [{"name": "Lunch", "unit_price": float("inf")}]},
    {"resources": [{"name": "Lunch", "unit_price": float("nan")}]},
    {"resources": [{"name": "Lunch", "menu_id": "menu-a", "inventory_id": "stock-a"}]},
    {"agenda": [{"title": "Meal", "starts_at": "2026-10-21T12:00", "ends_at": "2026-10-21T11:00"}]},
])
def test_invalid_event_is_rejected_before_side_effects(patch):
    with pytest.raises(ValidationError): event(**patch)


def test_adjacent_bookings_are_allowed():
    assert len(event(space_bookings=[window(), window("12:00", "14:00")]).space_bookings) == 2


def test_conflicts_compare_instants_not_offset_text():
    assert overlaps(window("10:00+03:00", "12:00+03:00"), window("08:00Z", "09:30Z"))
    assert not overlaps(window(), window("12:00", "13:00"))


@pytest.mark.parametrize(("hours", "expected"), [(0.5, 100), (2, 200), (6, 500), (24, 500), (25, 1000), (49, 1500)])
def test_salon_multiday_rental_and_hour_minimum(hours, expected):
    from datetime import timedelta
    start = datetime(2026, 10, 21, 10)
    totals = mice._compute_totals({"space_bookings": [{"space_id": "a", "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=hours)).isoformat()}]}, {"a": {"hourly_rate": 100, "daily_rate": 500}})
    assert totals["grand_total"] == expected


def test_half_cent_is_rounded_half_up_and_totals_reconcile():
    totals = mice._compute_totals({"resources": [{"quantity": 1, "unit_price": 0.105}, {"quantity": 3, "unit_price": 0.1}]}, {})
    assert totals == {"space_total": 0, "resources_total": 0.41, "grand_total": 0.41}


def test_space_quote_keeps_saved_rate_after_catalog_change():
    bookings = [window()]
    mice._snapshot_space_rates(bookings, {"hall-a": {"hourly_rate": 500}}, [{**window(), "rate_snapshot": {"hourly_rate": 100, "daily_rate": 1000}}])
    assert mice._compute_totals({"space_bookings": bookings}, {"hall-a": {"hourly_rate": 500}})["grand_total"] == 200


def test_inventory_uses_peak_not_sum_of_disjoint_events():
    assert peak_usage([window("09:00", "18:00")], [([window("10:00", "11:00")], 2), ([window("12:00", "13:00")], 2)]) == 2
    assert peak_usage([window("09:00", "10:00"), window("17:00", "18:00")], [([window("12:00", "13:00")], 9)]) == 0


def test_zero_quantity_does_not_become_a_full_pax_kitchen_order():
    assert mice._build_fnb_lines({"expected_pax": 100, "resources": [{"type": "fb", "quantity": 0, "unit_price": 10}]}) == []


@pytest.mark.parametrize("proposed", [[], [{"paid": False}], [{"paid": True, "amount": 20}], [{"paid": True, "amount": 10}, {"paid": True, "amount": 20}]])
def test_paid_milestones_cannot_be_forged_or_rewritten(proposed):
    with pytest.raises(ValueError): protect_paid_schedule([{"paid": True, "amount": 10}], proposed)


def test_paid_timestamp_serialization_does_not_look_like_an_amount_change():
    protect_paid_schedule([{"paid": True, "amount": 10, "paid_at": "2026-10-21T10:00:00+00:00"}],
                          [{"paid": True, "amount": 10.0, "paid_at": "2026-10-21T10:00:00Z"}])


@pytest.mark.asyncio
@pytest.mark.parametrize("space", [None, {"active": False}, {"capacity_theatre": 0}, {"capacity_theatre": 5}])
async def test_missing_inactive_or_overcapacity_space_is_rejected(monkeypatch, space):
    collection = SimpleNamespace(find=lambda *_a: Cursor([] if space is None else [{"id": "hall-a", "name": "Hall", **space}]))
    monkeypatch.setattr(mice, "get_system_db", lambda: SimpleNamespace(mice_spaces=collection))
    with pytest.raises(HTTPException) as error:
        await mice._validate_setup_capacity("hotel-a", [window(expected_pax=10)])
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_invalid_catalog_before_quota_reservation(monkeypatch):
    monkeypatch.setattr(mice, "_ensure_indexes", AsyncMock())
    monkeypatch.setattr(mice, "_tenant_currency_code", AsyncMock(return_value="TRY"))
    monkeypatch.setattr(mice, "get_system_db", lambda: SimpleNamespace())
    monkeypatch.setattr(mice, "_validate_setup_capacity", AsyncMock(side_effect=HTTPException(422, "bad hall")))
    reserve = AsyncMock()
    monkeypatch.setattr(mice, "reserve_quota", reserve)
    with pytest.raises(HTTPException): await mice.create_event(event(status="tentative", space_bookings=[window()]), USER)
    reserve.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("old, patch", [({"status": "lead"}, {"status": "confirmed"}), ({"status": "lead", "gl_journal_entry_id": "journal-a"}, {}), ({"status": "lead", "signature": {"name": "A"}}, {})])
async def test_general_update_cannot_bypass_lifecycle_or_change_signed_financials(monkeypatch, old, patch):
    monkeypatch.setattr(mice, "_ensure_indexes", AsyncMock())
    writes = AsyncMock()
    monkeypatch.setattr(mice, "get_system_db", lambda: SimpleNamespace(mice_events=SimpleNamespace(find_one=AsyncMock(return_value=old), update_one=writes)))
    with pytest.raises(HTTPException) as error: await mice._update_event_impl("event-a", event(**patch), USER)
    assert error.value.status_code == 409
    writes.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_paid_retry_does_not_change_payment_timestamp(monkeypatch):
    item = {"paid": True, "paid_at": "2026-10-01T10:00", "amount": 100}
    collection = SimpleNamespace(find_one=AsyncMock(return_value={"payment_schedule": [item]}), update_one=AsyncMock())
    monkeypatch.setattr(mice, "get_system_db", lambda: SimpleNamespace(mice_events=collection))
    result = await mice.mark_payment_paid("event-a", 0, current_user=USER)
    assert result["already_paid"] and result["item"]["paid_at"] == item["paid_at"]
    collection.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_reading_catalog_does_not_create_demo_data(monkeypatch):
    monkeypatch.setattr(mice, "_ensure_indexes", AsyncMock())
    monkeypatch.setattr(mice, "_tenant_currency_code", AsyncMock(return_value="TRY"))
    seed = AsyncMock()
    monkeypatch.setattr(mice, "_seed_spaces", seed)
    monkeypatch.setattr(mice, "get_system_db", lambda: SimpleNamespace(mice_spaces=SimpleNamespace(find=lambda *_args: Cursor([]))))
    assert await mice.list_spaces.__wrapped__(USER) == {"spaces": []}
    seed.assert_not_awaited()
