from datetime import date

import pytest

from modules.pms_core.occupancy_calendar import occupancy_calendar

DAY = date(2026, 11, 10)
ROOMS = [{"id": "r1", "room_number": "101", "room_type": "Standard"},
         {"id": "r2", "room_number": "102", "room_type": "Standard"}]


def booking(id="b1", **kwargs):
    return {"id": id, "status": "confirmed", "room_type": "Standard", "check_in": "2026-11-10", "check_out": "2026-11-12", **kwargs}


def report(bookings, blocks=None, **kwargs):
    return occupancy_calendar(ROOMS, bookings, blocks or [], DAY, date(2026, 11, 12), DAY, **kwargs)


def test_expected_counts_unassigned_but_realised_does_not():
    row = report([booking(), booking("b2", room_id="r1", status="checked_in")])["rows"][0]
    assert (row["actual_rooms"], row["expected_rooms"], row["expected_occupancy"], row["unassigned_rooms"]) == (1, 2, 100, 1)


@pytest.mark.parametrize("status", ["cancelled", "canceled", "no_show", "noshow", "pending", "tentative"])
def test_non_deducting_status_is_not_demand(status):
    assert report([booking(status=status)])["rows"][0]["expected_rooms"] == 0


def test_checkout_exclusive_no_double_arrival_after_checkin():
    result = report([booking(room_id="r1", status="checked_in")])
    assert result["rows"][0]["arrivals"] == 1
    assert result["rows"][0]["stayovers"] == 0
    assert result["rows"][1]["arrivals"] == 0
    assert result["rows"][1]["stayovers"] == 1
    assert result["rows"][2]["expected_rooms"] == 0


def test_forecast_is_not_presented_as_actual_in_future_or_past():
    result = occupancy_calendar(ROOMS, [booking(status="confirmed", room_id="r1")], [], date(2026, 11, 9), date(2026, 11, 11), DAY)
    assert result["rows"][0]["expected_rooms"] is None
    assert result["rows"][1]["actual_rooms"] == 0
    assert result["rows"][2]["actual_rooms"] is None


def test_blocked_capacity_weighted_total_and_overbooking_not_capped():
    blocks = [{"room_id": "r2", "start_date": "2026-11-10", "end_date": "2026-11-11"}]
    result = report([booking("a"), booking("b")], blocks)
    assert result["rows"][0]["expected_occupancy"] == 200
    assert result["rows"][0]["overbooked_rooms"] == 1
    assert result["totals"]["expected"] == {"room_nights": 4, "available_room_nights": 5, "occupancy": 80}


def test_zero_capacity_has_no_invented_zero_percentage():
    result = occupancy_calendar([], [], [], DAY, DAY, DAY)
    assert result["rows"][0]["expected_occupancy"] is None
    assert result["totals"]["expected"]["occupancy"] is None


def test_duplicate_rows_and_room_assignment_conflicts_are_explicit():
    a = booking(room_id="r1", status="checked_in")
    row = report([a, a, booking("b2", room_number="101")])["rows"][0]
    assert row["expected_rooms"] == 1
    assert row["assignment_conflicts"] == 1


def test_room_type_filter_assigned_room_authoritative_unknown_not_guessed():
    row = report([booking(room_id="r1", room_type="Wrong"), booking("b2", room_type="Unknown")], room_type="Standard")["rows"][0]
    assert row["expected_rooms"] == 1
    assert report([booking(room_id="missing")])["rows"][0]["unknown_room_references"] == 1


def test_comp_counts_and_early_checkout_stops_future_demand():
    result = report([booking(room_id="r1", status="checked_out", checked_out_at="2026-11-11T09:00:00Z", is_complimentary=True)])
    assert result["rows"][0]["actual_rooms"] == 1
    assert result["rows"][1]["expected_rooms"] == 0
