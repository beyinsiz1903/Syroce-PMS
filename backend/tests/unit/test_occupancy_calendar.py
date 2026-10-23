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
    assert row["expected_rooms"] == 2
    assert row["assignment_conflicts"] == 1
    assert row["actual_rooms"] == 1
    assert row["arrivals"] == 2


def test_room_type_filter_assigned_room_authoritative_unknown_not_guessed():
    row = report([booking(room_id="r1", room_type="Wrong"), booking("b2", room_type="Unknown")], room_type="Standard")["rows"][0]
    assert row["expected_rooms"] == 1
    assert report([booking(room_id="missing")])["rows"][0]["unknown_room_references"] == 1


def test_comp_counts_and_early_checkout_stops_future_demand():
    result = report([booking(room_id="r1", status="checked_out", checked_out_at="2026-11-11T09:00:00Z", is_complimentary=True)])
    assert result["rows"][0]["actual_rooms"] == 1
    assert result["rows"][1]["expected_rooms"] == 0


def test_room_type_matrix_reconciles_to_house_and_keeps_unknown_inventory_bucket():
    rooms = [*ROOMS, {"id": "suite", "room_number": "301", "room_type": "Suite"},
             {"id": "untyped", "room_number": "401"}, {"id": "inactive", "room_type": "Old", "is_active": False}]
    bookings = [booking("s1"), booking("s2", room_id="r1"),
                booking("suite-booking", room_number="301", room_type="Wrong"), booking("untyped-booking", room_id="untyped")]
    data = occupancy_calendar(rooms, bookings, [{"room_id": "r2", "start_date": DAY.isoformat()}], DAY, DAY, DAY)
    assert [(group["room_type"], group["physical_rooms"]) for group in data["room_type_groups"]] == [('Standard', 2), ('Suite', 1), (None, 1)]
    rows = [group["rows"][0] for group in data["room_type_groups"]]
    for field in ('physical_rooms', 'blocked_rooms', 'available_rooms', 'expected_rooms', 'arrivals', 'stayovers', 'unassigned_rooms'):
        assert sum(row[field] for row in rows) == data['rows'][0][field]
    assert rows[0]['expected_occupancy'] == 200
    assert rows[0]['overbooked_rooms'] == 1
    assert rows[1]['expected_rooms'] == 1  # assigned room type is authoritative


def test_room_type_overbooking_is_visible_even_when_house_has_spare_rooms():
    rooms = [*ROOMS, *[{"id": f"suite-{i}", "room_type": "Suite"} for i in range(5)]]
    data = occupancy_calendar(rooms, [booking(str(i)) for i in range(3)], [], DAY, DAY, DAY)
    assert data['rows'][0]['expected_rooms'] == 3 and data['rows'][0]['available_rooms'] == 7
    assert data['rows'][0]['overbooked_rooms'] == 0
    standard = next(group for group in data['room_type_groups'] if group['room_type'] == 'Standard')
    assert standard['rows'][0]['overbooked_rooms'] == 1


def test_filter_scopes_both_matrix_and_house_without_fetching_other_types():
    rooms = [*ROOMS, {"id": "suite", "room_type": "Suite"}]
    data = occupancy_calendar(rooms, [booking(), booking('s', room_id='suite')], [], DAY, DAY, DAY, 'Suite')
    assert len(data['room_type_groups']) == 1
    assert data['room_type_groups'][0]['room_type'] == 'Suite'
    assert data['room_type_groups'][0]['rows'] == data['rows']


def test_distinct_arrival_and_stayover_on_same_room_are_two_commitments_not_one():
    row = report([booking('stay', room_id='r1', check_in='2026-11-09', status='checked_in'),
                  booking('arrival', room_id='r1')])['rows'][0]
    assert row['stayovers'] == row['arrivals'] == 1
    assert row['expected_rooms'] == 2
    assert row['actual_rooms'] == 1


def test_legacy_status_case_does_not_reintroduce_early_departures_or_closed_inventory():
    rows = report([booking(room_id='r1', status=' CHECKED_OUT ', checked_out_at='2026-11-11')],
                  [{'room_id': 'r2', 'start_date': '2026-11-10', 'end_date': '2026-11-12', 'status': ' Active '}])['rows']
    assert rows[0]['available_rooms'] == 1
    assert rows[1]['expected_rooms'] == 0


def test_duplicate_booking_versions_are_deduplicated_before_room_type_partitioning():
    rooms = [*ROOMS, {'id': 'suite', 'room_type': 'Suite'}]
    versions = [booking('same-id'), booking('same-id', room_type='Suite')]
    data = occupancy_calendar(rooms, versions, [], DAY, DAY, DAY)
    assert data['rows'][0]['expected_rooms'] == 1
    assert sum(group['rows'][0]['expected_rooms'] for group in data['room_type_groups']) == 1
    assert next(group for group in data['room_type_groups'] if group['room_type'] == 'Standard')['rows'][0]['expected_rooms'] == 0
