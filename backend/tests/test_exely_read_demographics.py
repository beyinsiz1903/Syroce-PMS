"""Offline REST scope, immutable-version reconciliation and secret regressions."""

from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from domains.channel_manager.providers.exely import demographics as demo
from domains.channel_manager.providers.exely import read_reservation as read
from domains.channel_manager.providers.exely import read_reservation_router as api
from tests.test_exely_connection_controls import local_mongo as local_mongo
from tests.test_exely_reservation_lifecycle import _Collection, _project

pytestmark = pytest.mark.exely_failure_stress

CONNECTION = {"tenant_id": "tenant-a", "id": "conn-a", "hotel_code": "501694", "mode": "sandbox", "is_active": True, "read_reservation_enabled": True}


@pytest.mark.parametrize("drift", [None, "tenant_id", "id", "hotel_code", "mode", "unapproved"])
def test_dry_run_exception_is_explicit_and_bound_to_only_the_test_connection(monkeypatch, drift):
    monkeypatch.setenv("E2E_EXTERNAL_DRY_RUN", "true")
    monkeypatch.setattr(read, "reservation_sync_block_reason", lambda: "")
    connection = {**CONNECTION, "read_reservation_test_read_scope": read.test_read_scope(CONNECTION)}
    if drift == "unapproved":
        connection.pop("read_reservation_test_read_scope")
    elif drift:
        connection[drift] = "different"
    if drift:
        with pytest.raises(read.ReadReservationError, match="EXELY_READ_DRY_RUN"):
            read.require_read_allowed(connection)
    else:
        read.require_read_allowed(connection)
        monkeypatch.setattr(read, "reservation_sync_block_reason", lambda: "EXELY_SYNC_DISABLED")
        with pytest.raises(read.ReadReservationError, match="EXELY_SYNC_DISABLED"):
            read.require_read_allowed(connection)


@pytest.mark.parametrize("method,path", [("POST", "/api/write"), ("GET", "/api/read-reservation/v1/properties/999/bookings/a"), ("DELETE", "/auth/token")])
async def test_approved_test_read_cannot_invoke_other_paths_or_methods(monkeypatch, method, path):
    monkeypatch.setenv("E2E_EXTERNAL_DRY_RUN", "true")
    monkeypatch.setattr(read, "reservation_sync_block_reason", lambda: "")
    request = AsyncMock()
    connection = {**CONNECTION, "read_reservation_test_read_scope": read.test_read_scope(CONNECTION)}
    client = read.ReadReservationClient(connection, {}, request)
    with pytest.raises(read.ReadReservationError, match="EXELY_READ_OPERATION_NOT_ALLOWED"):
        await client._json(method, path)
    request.assert_not_awaited()
VERSION = "2026-10-22T05:38:43Z"
NUMBER = "20261110-501694-1200421078"


def _mock_request(http):
    async def request(method, url, **kwargs):
        assert kwargs.pop("max_response_bytes") == 2_000_000
        return await http.request(method, url, **kwargs)
    return request


@pytest.fixture
def scenario(monkeypatch):
    database = SimpleNamespace(**{name: _Collection() for name in (
        "exely_connections", "exely_reservations", "exely_reservation_versions", "exely_room_mappings", "bookings", "exely_demographic_checks",
    )})
    reservation = {
        "tenant_id": "tenant-a", "property_id": "501694", "external_id": NUMBER,
        "state": "confirmed", "provider_version_identity": "immutable-identity", "provider_version_key": VERSION,
        "provider_payload_hash": "immutable-soap-hash", "delivery_confirmed": True,
        "currency": "USD", "total": 120, "pms_booking_ids": ["booking-a"],
        "rooms": [{"index_number": "1", "room_type_code": "soap-deluxe", "rate_plan_code": "soap-rate", "adults": 3, "children": 0, "amount": 120,
                   "check_in": "2026-11-10T14:00", "check_out": "2026-11-11T12:00"}],
        "room_stay_lineage": [{"active": True, "index_number": "1", "pms_booking_id": "booking-a"}],
    }
    booking = {
        "tenant_id": "tenant-a", "id": "booking-a", "property_id": "501694", "provider_version_key": VERSION,
        "provider_group_reservation_id": NUMBER, "booking_source": "exely", "status": "confirmed",
        "adults": 3, "children": 0, "children_ages": [], "guests_count": 3,
        "check_in": "2026-11-10T14:00", "check_out": "2026-11-11T12:00", "total_amount": 120, "currency": "USD",
        "room_id": "assigned-room", "paid_amount": 50, "updated_at": "unchanged-date", "exely_demographics": None,
        "room_type": "Deluxe",
    }
    remote = {
        "propertyId": "501694", "number": NUMBER, "status": "Active", "modifiedDateTime": VERSION,
        "currencyCode": "USD", "total": {"priceAfterTax": 120}, "roomStays": [{
            "index": 0, "roomType": {"id": "5003300"}, "stayDates": {"arrivalDateTime": "2026-11-10T14:00", "departureDateTime": "2026-11-11T12:00"},
            "total": {"priceAfterTax": 120}, "guestCount": {"adultCount": 2, "childAges": [6]},
        }],
    }
    database.exely_connections.documents = [deepcopy(CONNECTION)]
    database.exely_reservations.documents = [deepcopy(reservation)]
    database.exely_reservation_versions.documents = [{"tenant_id": "tenant-a", "property_id": "501694", "version_identity": "immutable-identity", "processing_state": "PMS_DURABLE"}]
    database.exely_room_mappings.documents = [{"tenant_id": "tenant-a", "pms_room_type": "Deluxe", "pms_api_room_code": "soap-deluxe", "pms_api_rate_plan_code": "soap-rate", "exely_room_code": "5003300", "exely_rate_plan_code": "rest-rate"}]
    database.bookings.documents = [deepcopy(booking)]
    monkeypatch.setattr(demo, "db", database)
    monkeypatch.setattr(api, "db", database)
    return database, reservation, booking, remote


async def test_rest_demographics_corrects_only_counts_with_durable_readback_and_append_only_evidence(scenario):
    database, reservation, booking, remote = scenario
    original_sources = deepcopy((database.exely_reservations.documents, database.exely_reservation_versions.documents))
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    result = await demo.apply_plan("tenant-a", CONNECTION, reservation, plans)
    assert result == {"success": True, "status": "verified", "rooms": [{"booking_id": "booking-a", "adults": 2, "children_ages": [6], "status": "verified"}], "provider_write_count": 0}
    actual = database.bookings.documents[0]
    assert actual["adults"] == 2 and actual["children"] == 1 and actual["children_ages"] == [6]
    assert actual["guests_count"] == 3 and actual["children_ages_complete"] is True
    assert demo.verified_booking(actual)
    permitted = {"adults", "children", "children_ages", "children_ages_complete", "guests_count", "exely_demographics", "updated_at", "_version"}
    assert {key: value for key, value in actual.items() if key not in permitted} == {key: value for key, value in booking.items() if key not in permitted}
    assert original_sources == (database.exely_reservations.documents, database.exely_reservation_versions.documents)
    assert len(database.exely_demographic_checks.documents) == 1
    first_evidence = deepcopy(database.exely_demographic_checks.documents)
    # Repeat reads are safe and do not replace the original evidence.
    await demo.apply_plan("tenant-a", CONNECTION, reservation, await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote))
    assert database.exely_demographic_checks.documents == first_evidence


async def test_observed_soap_and_rest_clocks_are_independent_without_mutating_source_version(scenario):
    database, reservation, _, remote = scenario
    soap_version = "2026-10-22T08:38:48.677"
    reservation["provider_version_key"] = soap_version
    database.exely_reservations.documents[0]["provider_version_key"] = soap_version
    database.bookings.documents[0]["provider_version_key"] = soap_version
    sources = deepcopy((database.exely_reservations.documents, database.exely_reservation_versions.documents))
    client = SimpleNamespace(booking=AsyncMock(return_value=remote))
    result = await demo.reconcile_one("tenant-a", CONNECTION, NUMBER, client)
    assert result["status"] == "verified"
    assert client.booking.await_count == 2
    actual = database.bookings.documents[0]
    assert (actual["adults"], actual["children"], actual["children_ages"], actual["total_amount"]) == (2, 1, [6], 120)
    assert actual["provider_version_key"] == soap_version
    assert actual["exely_demographics"]["rest_modified_at"] == VERSION
    assert actual["exely_demographics"]["rest_snapshot_hash"] == demo._rest_hash(remote)
    assert sources == (database.exely_reservations.documents, database.exely_reservation_versions.documents)


@pytest.mark.parametrize("value", [None, "", "garbage", "2026-10-22T05:38:43"])
async def test_rest_revision_requires_explicit_timezone(scenario, value):
    _, reservation, _, remote = scenario
    remote["modifiedDateTime"] = value
    with pytest.raises(read.ReadReservationError, match="REST_VERSION_INVALID"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)


@pytest.mark.parametrize("drift", ["version", "ages", "amount", "status", "property", "unmapped_field"])
async def test_remote_snapshot_change_between_reads_never_changes_pms(scenario, drift):
    database, _, _, remote = scenario
    changed = deepcopy(remote)
    if drift == "version":
        changed["modifiedDateTime"] = "2026-10-22T05:38:44Z"
    elif drift == "ages":
        changed["roomStays"][0]["guestCount"]["childAges"] = [7]
    elif drift == "amount":
        changed["total"]["priceAfterTax"] = 121
    elif drift == "status":
        changed["status"] = "Cancelled"
    elif drift == "property":
        changed["propertyId"] = "999"
    else:
        changed["comment"] = "Changed independently of modification timestamp"
    before = deepcopy(database.bookings.documents)
    client = SimpleNamespace(booking=AsyncMock(side_effect=[remote, changed]))
    with pytest.raises(read.ReadReservationError, match="REMOTE_CHANGED"):
        await demo.reconcile_one("tenant-a", CONNECTION, NUMBER, client)
    assert database.bookings.documents == before
    assert database.exely_demographic_checks.documents == []


async def test_failed_second_read_never_changes_pms(scenario):
    database, _, _, remote = scenario
    before = deepcopy(database.bookings.documents)
    client = SimpleNamespace(booking=AsyncMock(side_effect=[remote, read.ReadReservationError("EXELY_READ_HTTP_503")]))
    with pytest.raises(read.ReadReservationError, match="HTTP_503"):
        await demo.reconcile_one("tenant-a", CONNECTION, NUMBER, client)
    assert database.bookings.documents == before


@pytest.mark.parametrize("drift", ["older_version", "same_version_different_snapshot"])
async def test_rest_revision_cannot_regress_or_change_under_previously_verified_version(scenario, drift):
    database, reservation, _, remote = scenario
    await demo.apply_plan("tenant-a", CONNECTION, reservation, await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote))
    if drift == "older_version":
        remote["modifiedDateTime"] = "2026-10-22T05:38:42Z"
    else:
        remote["roomStays"][0]["guestCount"]["childAges"] = [7]
    before = deepcopy(database.bookings.documents)
    with pytest.raises(read.ReadReservationError, match="REST_VERSION_(REGRESSED|CONFLICT)"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert database.bookings.documents == before


async def test_newer_stable_rest_revision_uses_own_clock_and_preserves_pms_source_revision(scenario):
    database, reservation, _, remote = scenario
    await demo.apply_plan("tenant-a", CONNECTION, reservation, await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote))
    remote["modifiedDateTime"] = "2026-10-22T05:38:44Z"
    remote["roomStays"][0]["guestCount"]["childAges"] = [7]
    client = SimpleNamespace(booking=AsyncMock(return_value=remote))
    result = await demo.reconcile_one("tenant-a", CONNECTION, NUMBER, client)
    assert result["rooms"][0]["children_ages"] == [7]
    assert database.bookings.documents[0]["provider_version_key"] == VERSION
    assert database.bookings.documents[0]["total_amount"] == 120


async def test_source_revision_change_during_second_rest_read_is_rejected(scenario):
    database, _, _, remote = scenario
    before = deepcopy(database.bookings.documents)
    async def second_read(_number):
        database.exely_reservations.documents[0]["provider_version_identity"] = "new-soap-revision"
        return remote
    client = SimpleNamespace()
    async def booking(_number):
        if client.booking.await_count == 2:
            return await second_read(_number)
        return remote
    client.booking = AsyncMock(side_effect=booking)
    with pytest.raises(read.ReadReservationError, match="CURRENT_VERSION_CHANGED"):
        await demo.reconcile_one("tenant-a", CONNECTION, NUMBER, client)
    assert database.bookings.documents == before


@pytest.mark.parametrize("target,key,value", [
    ("remote", "propertyId", "other-property"), ("remote", "number", "other-booking"),
    ("remote", "modifiedDateTime", "not-a-version"), ("remote", "currencyCode", "EUR"),
    ("remote", "status", "Cancelled"), ("remote", "total", {"priceAfterTax": 121}),
    ("remote", "total", {"priceAfterTax": "NaN"}), ("remote", "roomStays", []),
    ("reservation", "tenant_id", "tenant-b"), ("reservation", "property_id", "other-property"),
    ("booking", "status", "checked_in"), ("booking", "property_id", "other-property"),
    ("booking", "provider_version_key", "2026-10-22T05:38:44Z"), ("booking", "total_amount", 122),
    ("booking", "currency", "EUR"), ("booking", "adults", 4), ("booking", "check_in", "2026-11-12"),
    ("booking", "room_type", "Suite"),
])
async def test_scope_version_money_and_manual_edit_mismatches_never_write(scenario, target, key, value):
    database, reservation, _, remote = scenario
    objects = {"remote": remote, "reservation": reservation, "booking": database.bookings.documents[0]}
    objects[target][key] = value
    before = deepcopy(database.bookings.documents)
    with pytest.raises(read.ReadReservationError):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert database.bookings.documents == before
    assert database.exely_demographic_checks.documents == []


@pytest.mark.parametrize("guest_count", [
    {"adultCount": True, "childAges": [6]}, {"adultCount": 2, "childAges": [False]},
    {"adultCount": 2, "childAges": [18]}, {"adultCount": 2, "childAges": [6.5]},
    {"adultCount": 2, "childAges": None}, {"adultCount": 2, "childAges": []},
    {"adultCount": 1001, "childAges": []},
])
async def test_missing_ages_invalid_counts_and_total_mismatch_are_not_inferred(scenario, guest_count):
    _, reservation, _, remote = scenario
    remote["roomStays"][0]["guestCount"] = guest_count
    with pytest.raises(read.ReadReservationError):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)


@pytest.mark.parametrize("age", [0, 2, 3, 6, 7, 17])
async def test_completed_child_age_boundaries_survive(scenario, age):
    _, reservation, _, remote = scenario
    remote["roomStays"][0]["guestCount"]["childAges"] = [age]
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert plans[0]["proof"]["children_ages"] == [age]


async def test_conflicting_explicit_soap_child_age_is_held_for_review(scenario):
    database, reservation, _, remote = scenario
    reservation["rooms"][0].update(adults=2, children=1, children_ages=[7], children_ages_complete=True)
    database.bookings.documents[0].update(adults=2, children=1, children_ages=[7])
    with pytest.raises(read.ReadReservationError, match="STRUCTURED_DEMOGRAPHICS_CONFLICT"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert database.bookings.documents[0]["children_ages"] == [7]


async def test_identical_multiroom_stays_are_held_instead_of_distributing_children_by_index(scenario):
    _, reservation, _, remote = scenario
    reservation["rooms"].append(deepcopy(reservation["rooms"][0]))
    remote["roomStays"].append(deepcopy(remote["roomStays"][0]))
    with pytest.raises(read.ReadReservationError, match="ROOM_JOIN_AMBIGUOUS"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)


async def test_inspection_shows_amount_mismatch_without_leaking_or_writing(scenario):
    database, reservation, _, remote = scenario
    reservation["total"] = 420
    database.exely_reservations.documents[0] = deepcopy(reservation)
    remote["total"]["priceAfterTax"] = 420
    remote["roomStays"][0]["total"]["priceAfterTax"] = 420
    remote["roomStays"][0]["guests"] = [{"name": "SECRET-GUEST", "email": "private@example.com"}]
    remote["roomStays"][0]["services"] = [{"id": "5001517", "inclusive": False,
        "total": {"priceAfterTax": 300}, "name": "SECRET-SERVICE", "description": "SECRET-NOTE"}]
    before = deepcopy(vars(database))
    client = SimpleNamespace(booking=AsyncMock(return_value=remote))
    result = await demo.inspect_reconciliation("tenant-a", CONNECTION, NUMBER, client)
    assert client.booking.await_count == 2
    assert result["status"] == "EXELY_READ_ROOM_JOIN_NOT_FOUND"
    assert result["source_rooms"][0]["amount"] == "120"
    assert result["rest_rooms"][0]["amount"] == "420"
    assert result["rest_rooms"][0]["services"] == [{"id": "5001517", "inclusive": False, "amount": "300"}]
    assert result["rest_rooms"][0]["index"] == 0
    assert result["applied"] is False and result["provider_write_count"] == 0
    assert "SECRET" not in str(result) and "private@example.com" not in str(result)
    for key in vars(database):
        assert getattr(database, key).documents == before[key].documents


@pytest.mark.parametrize("drift", ["foreign_tenant", "remote_scope", "snapshot_change"])
async def test_inspection_scope_and_snapshot_fences(scenario, drift):
    database, _, _, remote = scenario
    changed = deepcopy(remote)
    if drift == "remote_scope":
        changed["propertyId"] = "999"
    elif drift == "snapshot_change":
        changed["roomStays"][0]["total"]["priceAfterTax"] = 121
    client = SimpleNamespace(booking=AsyncMock(side_effect=[remote, changed] if drift == "snapshot_change" else [changed]))
    before = deepcopy(database.bookings.documents)
    with pytest.raises(read.ReadReservationError):
        await demo.inspect_reconciliation("tenant-b" if drift == "foreign_tenant" else "tenant-a", CONNECTION, NUMBER, client)
    assert database.bookings.documents == before
    if drift == "foreign_tenant":
        client.booking.assert_not_awaited()


async def test_inspection_ready_still_never_applies_a_valid_plan(scenario):
    database, _, _, remote = scenario
    before = deepcopy(database.bookings.documents)
    result = await demo.inspect_reconciliation("tenant-a", CONNECTION, NUMBER,
        SimpleNamespace(booking=AsyncMock(return_value=remote)))
    assert result["status"] == "ready" and result["applied"] is False
    assert database.bookings.documents == before and database.exely_demographic_checks.documents == []


async def test_explicit_free_room_is_not_replaced_with_extra_service_booking_total(scenario):
    database, reservation, _, remote = scenario
    reservation["rooms"][0]["amount"] = 0
    database.bookings.documents[0]["total_amount"] = 0
    remote["roomStays"][0]["total"]["priceAfterTax"] = 0
    # The separate overall provider total remains 120 (e.g. extra services).
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert plans[0]["proof"]["total_amount"] == 0


async def test_no_matching_room_is_distinct_from_multiple_matching_rooms(scenario):
    _, reservation, _, remote = scenario
    remote["roomStays"][0]["roomType"]["id"] = "999"
    with pytest.raises(read.ReadReservationError, match="ROOM_JOIN_NOT_FOUND"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)


def _observed_service_booking(scenario):
    """Sanitized live TEST1827 shape: SOAP100+300, REST RoomStay400.

    The service identifiers really differ between the two official APIs;
    neither service ID nor room index may be used to guess a room match.
    """
    database, reservation, _, remote = scenario
    reservation["total"] = remote["total"]["priceAfterTax"] = 400
    room = reservation["rooms"][0]
    room.update(amount=100, adults=2, children=0, services=[{
        "provider_id": "5001517", "inclusive": False, "amount": 300, "currency": "USD",
        "scope": "room", "room_stay_indexes": ["1"], "quantity": 2, "duration": 1,
    }])
    database.exely_reservations.documents[0] = deepcopy(reservation)
    database.bookings.documents[0].update(total_amount=100, provider_booking_total=400,
        provider_services=deepcopy(room["services"]), adults=2, children=0, guests_count=2, paid_amount=0)
    rest_room = remote["roomStays"][0]
    rest_room.update(total={"priceAfterTax": 400}, guestCount={"adultCount": 2, "childAges": []},
        services=[{"id": "5002994", "inclusive": False, "total": {"priceAfterTax": 300}}])
    return database, reservation, remote


async def test_observed_service_gross_total_matches_without_repricing_reimport_or_source_changes(scenario):
    database, reservation, remote = _observed_service_booking(scenario)
    before_source = deepcopy((database.exely_reservations.documents, database.exely_reservation_versions.documents))
    before = deepcopy(database.bookings.documents[0])
    client = SimpleNamespace(booking=AsyncMock(return_value=remote))
    result = await demo.reconcile_one("tenant-a", CONNECTION, NUMBER, client)
    assert result["status"] == "verified" and result["provider_write_count"] == 0
    assert client.booking.await_count == 2
    actual = database.bookings.documents[0]
    assert demo.verified_booking(actual) and (actual["adults"], actual["children"]) == (2, 0)
    proof = actual["exely_demographics"]["room_amount_comparison"]
    assert proof == {"basis": "gross_less_room_extra_services", "rest_room_total": "400",
        "non_inclusive_services_total": "300", "accommodation_amount": "100"}
    # The300 service quote is already a total: quantity2 must NOT make it600.
    assert actual["total_amount"] == 100 and actual["provider_booking_total"] == 400
    assert actual["provider_services"] == before["provider_services"] and actual["paid_amount"] == 0
    allowed = {"exely_demographics", "children_ages_complete", "updated_at", "_version"}
    assert {k: v for k, v in actual.items() if k not in allowed} == {k: v for k, v in before.items() if k not in allowed}
    assert before_source == (database.exely_reservations.documents, database.exely_reservation_versions.documents)
    assert len(database.exely_demographic_checks.documents) == 1
    original_evidence = deepcopy(database.exely_demographic_checks.documents)
    await demo.reconcile_one("tenant-a", CONNECTION, NUMBER, client)
    assert database.exely_demographic_checks.documents == original_evidence
    assert database.bookings.documents[0]["total_amount"] == 100


async def test_service_inclusive_inspection_is_ready_but_still_never_writes(scenario):
    database, _, remote = _observed_service_booking(scenario)
    before = {k: deepcopy(v.documents) for k, v in vars(database).items()}
    result = await demo.inspect_reconciliation("tenant-a", CONNECTION, NUMBER, SimpleNamespace(booking=AsyncMock(return_value=remote)))
    assert result["status"] == "ready" and result["applied"] is False and result["provider_write_count"] == 0
    assert result["source_rooms"][0]["amount"] == "100" and result["rest_rooms"][0]["amount"] == "400"
    assert before == {k: v.documents for k, v in vars(database).items()}


@pytest.mark.parametrize("drift", [
    "missing_soap_services", "missing_rest_services", "soap_inclusive", "rest_inclusive", "missing_flag",
    "string_flag", "rest_service_amount", "source_service_amount", "gross_amount", "currency",
    "shared_service", "wrong_owner", "extra_stay", "duplicate_rest_service", "same_sum_different_parts",
    "room_type", "stay_dates", "missing_service_total", "invalid_service_total",
])
async def test_service_normalization_never_infers_missing_or_conflicting_breakdowns(scenario, drift):
    database, reservation, remote = _observed_service_booking(scenario)
    source = reservation["rooms"][0]
    rest_room = remote["roomStays"][0]
    if drift == "missing_soap_services":
        source.pop("services")
    elif drift == "missing_rest_services":
        rest_room.pop("services")
    elif drift == "soap_inclusive":
        source["services"][0]["inclusive"] = True
    elif drift == "rest_inclusive":
        rest_room["services"][0]["inclusive"] = True
    elif drift == "missing_flag":
        rest_room["services"][0].pop("inclusive")
    elif drift == "string_flag":
        rest_room["services"][0]["inclusive"] = "false"
    elif drift == "rest_service_amount":
        rest_room["services"][0]["total"]["priceAfterTax"] = 299
    elif drift == "source_service_amount":
        source["services"][0]["amount"] = 299
    elif drift == "gross_amount":
        rest_room["total"]["priceAfterTax"] = 401
    elif drift == "currency":
        source["services"][0]["currency"] = "EUR"
    elif drift == "shared_service":
        source["services"][0]["scope"] = "reservation"
    elif drift == "wrong_owner":
        source["services"][0]["room_stay_indexes"] = ["2"]
    elif drift == "extra_stay":
        rest_room["extraStayCharges"] = {"earlyArrival": {"total": {"priceAfterTax": 20}}}
    elif drift == "duplicate_rest_service":
        rest_room["services"].append(deepcopy(rest_room["services"][0]))
    elif drift == "same_sum_different_parts":
        rest_room["services"] = [{"inclusive": False, "total": {"priceAfterTax": 150}}] * 2
    elif drift == "room_type":
        rest_room["roomType"]["id"] = "999"
    elif drift == "stay_dates":
        rest_room["stayDates"]["departureDateTime"] = "2026-11-12T12:00"
    elif drift == "missing_service_total":
        rest_room["services"][0].pop("total")
    else:
        rest_room["services"][0]["total"]["priceAfterTax"] = "NaN"
    before = deepcopy(database.bookings.documents)
    with pytest.raises(read.ReadReservationError):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert database.bookings.documents == before and database.exely_demographic_checks.documents == []


async def test_identical_service_adjusted_rooms_still_fail_ambiguous_instead_of_guessing_by_index(scenario):
    database, reservation, remote = _observed_service_booking(scenario)
    reservation["rooms"].append(deepcopy(reservation["rooms"][0]))
    remote["roomStays"].append(deepcopy(remote["roomStays"][0]))
    before = deepcopy(database.bookings.documents)
    with pytest.raises(read.ReadReservationError, match="ROOM_JOIN_AMBIGUOUS"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert database.bookings.documents == before


async def test_explicit_free_accommodation_with_paid_services_remains_zero(scenario):
    database, reservation, remote = _observed_service_booking(scenario)
    reservation["rooms"][0]["amount"] = database.bookings.documents[0]["total_amount"] = 0
    reservation["total"] = remote["total"]["priceAfterTax"] = remote["roomStays"][0]["total"]["priceAfterTax"] = 300
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert plans[0]["proof"]["total_amount"] == 0
    assert plans[0]["proof"]["room_amount_comparison"]["accommodation_amount"] == "0"


@pytest.mark.parametrize("rest_extra_stay", [None, {"earlyArrival": None, "lateDeparture": None}])
async def test_inclusive_services_without_prices_are_not_subtracted_from_room_total(scenario, rest_extra_stay):
    _, reservation, remote = _observed_service_booking(scenario)
    included = {**reservation["rooms"][0]["services"][0], "provider_id": "other", "inclusive": True}
    included.pop("amount")
    reservation["rooms"][0]["services"].append(included)
    remote["roomStays"][0]["services"].append({"id": "different", "inclusive": True})
    remote["roomStays"][0]["extraStayCharges"] = rest_extra_stay
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert plans[0]["proof"]["room_amount_comparison"]["non_inclusive_services_total"] == "300"


async def test_different_net_room_amounts_match_independent_of_rest_order_and_indexes(scenario):
    database, reservation, remote = _observed_service_booking(scenario)
    second_room = deepcopy(reservation["rooms"][0])
    second_room.update(index_number="2", amount=120, adults=3)
    second_room["services"][0].update(amount=400, room_stay_indexes=["2"])
    reservation["rooms"].append(second_room)
    reservation["pms_booking_ids"].append("booking-b")
    reservation["room_stay_lineage"].append({"active": True, "index_number": "2", "pms_booking_id": "booking-b"})
    database.bookings.documents.append({**deepcopy(database.bookings.documents[0]),
        "id": "booking-b", "total_amount": 120, "adults": 3, "guests_count": 3})
    second_rest = deepcopy(remote["roomStays"][0])
    second_rest.update(index=91, total={"priceAfterTax": 520}, guestCount={"adultCount": 2, "childAges": [6]})
    second_rest["services"][0]["total"]["priceAfterTax"] = 400
    remote["roomStays"].insert(0, second_rest)
    reservation["total"] = remote["total"]["priceAfterTax"] = 920
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    assert [(p["booking"]["id"], p["proof"]["children_ages"]) for p in plans] == [("booking-a", []), ("booking-b", [6])]


async def test_direct_and_service_adjusted_candidates_do_not_prefer_one_or_guess_by_index(scenario):
    _, reservation, remote = _observed_service_booking(scenario)
    reservation["rooms"].append(deepcopy(reservation["rooms"][0]))
    second = deepcopy(remote["roomStays"][0])
    second["total"]["priceAfterTax"] = 100
    remote["roomStays"].append(second)
    with pytest.raises(read.ReadReservationError, match="ROOM_JOIN_AMBIGUOUS"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)


async def test_inspection_route_never_returns_credentials(monkeypatch, scenario):
    _, _, _, remote = scenario
    @asynccontextmanager
    async def fake_client(connection, credentials):
        yield SimpleNamespace(booking=AsyncMock(return_value=remote))
    monkeypatch.setattr(api, "read_client", fake_client)
    monkeypatch.setattr(api, "require_read_allowed", lambda *_: None)
    monkeypatch.setattr(api, "saved_read_credentials", AsyncMock(return_value={"client_id": "SECRET-CLIENT", "client_secret": "SECRET-KEY"}))
    result = await api.inspect_read_reservation(api.ReconcileRequest(reservation_id=NUMBER), SimpleNamespace(tenant_id="tenant-a"), None)
    assert result["status"] == "ready" and "SECRET" not in str(result)


@pytest.mark.parametrize("drift", ["booking", "source", "connection"])
async def test_compare_and_swap_rejects_races_without_repricing_or_reack(scenario, drift):
    database, reservation, _, remote = scenario
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    if drift == "booking":
        database.bookings.documents[0]["updated_at"] = "human-edit"
    elif drift == "source":
        database.exely_reservations.documents[0]["provider_version_identity"] = "newer-version"
    else:
        database.exely_connections.documents[0]["read_reservation_enabled"] = False
    before = deepcopy(database.bookings.documents)
    with pytest.raises(read.ReadReservationError):
        await demo.apply_plan("tenant-a", CONNECTION, reservation, plans)
    assert database.bookings.documents == before


async def test_client_uses_only_official_mode_host_token_cache_and_exact_property(monkeypatch, scenario):
    monkeypatch.setenv("E2E_EXTERNAL_DRY_RUN", "false")
    monkeypatch.setattr(read, "reservation_sync_block_reason", lambda: "")
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.path == "/auth/token":
            return httpx.Response(200, json={"access_token": "synthetic-token", "expires_in": 900})
        return httpx.Response(200, json={"booking": scenario[3]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = read.ReadReservationClient({**CONNECTION, "endpoint_url": "https://attacker.invalid"}, {"client_id": "synthetic-client", "client_secret": "synthetic-secret"}, _mock_request(http))
        await client.booking(NUMBER)
        await client.booking(NUMBER)
        with pytest.raises(read.ReadReservationError):
            await client.booking("../another-property")
    assert len(requests) == 3 and [request.method for request in requests] == ["POST", "GET", "GET"]
    assert all(request.url.host == "connect.test.hopenapi.com" for request in requests)
    assert requests[1].url.path == f"/api/read-reservation/v1/properties/501694/bookings/{NUMBER}"
    assert "synthetic-secret" not in str(requests[0].url)
    assert requests[1].headers["Authorization"] == "Bearer synthetic-token"


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500])
async def test_auth_errors_and_redirects_never_leak_provider_body_or_retry(monkeypatch, status):
    monkeypatch.setenv("E2E_EXTERNAL_DRY_RUN", "false")
    monkeypatch.setattr(read, "reservation_sync_block_reason", lambda: "")
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="synthetic-secret", headers={"Location": "https://attacker.invalid"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=False) as http:
        client = read.ReadReservationClient(CONNECTION, {"client_id": "synthetic-client", "client_secret": "synthetic-secret"}, _mock_request(http))
        with pytest.raises(read.ReadReservationError) as error:
            await client.booking(NUMBER)
    assert str(error.value) == f"EXELY_READ_HTTP_{status}" and "synthetic-secret" not in repr(error.value)
    assert len(calls) == 1


async def test_vault_is_distinct_from_soap_and_requires_connection_mode_property_binding(monkeypatch):
    credentials = {"client_id": "synthetic-client", "client_secret": "synthetic-secret", "connection_id": "conn-a", "property_id": "501694", "mode": "sandbox"}
    vault = SimpleNamespace(get_provider_credentials=AsyncMock(return_value=credentials))
    monkeypatch.setattr(read, "get_secrets_manager", lambda: vault)
    assert await read.saved_read_credentials("tenant-a", CONNECTION) == credentials
    vault.get_provider_credentials.assert_awaited_once_with("tenant-a", "exely-read-reservation", "501694", actor="exely_read_reservation")
    with pytest.raises(read.ReadReservationError, match="SCOPE_MISMATCH"):
        await read.saved_read_credentials("tenant-a", {**CONNECTION, "id": "replacement-connection"})


async def test_setup_validates_before_saving_scoped_keys_and_never_applies_or_returns_secrets(monkeypatch, scenario):
    database, _, _, remote = scenario
    @asynccontextmanager
    async def fake_client(connection, credentials):
        assert connection["hotel_code"] == "501694"
        yield SimpleNamespace(booking=AsyncMock(return_value=remote))
    vault = SimpleNamespace(store_provider_credentials=AsyncMock())
    monkeypatch.setattr(api, "read_client", fake_client)
    monkeypatch.setattr(api, "require_read_allowed", lambda *_: None)
    monkeypatch.setattr(api, "get_secrets_manager", lambda: vault)
    payload = api.ReadSetup(client_id="synthetic-client", client_secret="synthetic-secret", reservation_id=NUMBER, confirmation="ENABLE_READ_RESERVATION:501694")
    before = deepcopy(database.bookings.documents)
    result = await api.connect_read_reservation(payload, SimpleNamespace(tenant_id="tenant-a", name="Synthetic Operator"), None)
    assert result["success"] and result["enabled"] and result["applied"] is False
    assert "synthetic-secret" not in str(result) and "synthetic-client" not in str(result)
    assert database.bookings.documents == before
    saved = vault.store_provider_credentials.await_args.kwargs
    assert saved["provider"] == "exely-read-reservation" and saved["tenant_id"] == "tenant-a" and saved["property_id"] == "501694"
    assert saved["credentials"]["connection_id"] == "conn-a"
    assert "synthetic-secret" not in repr(payload)


async def test_setup_changed_remote_snapshot_never_saves_credentials_or_enables_connection(monkeypatch, scenario):
    database, _, _, remote = scenario
    database.exely_connections.documents[0]["read_reservation_enabled"] = False
    changed = {**remote, "modifiedDateTime": "2026-10-22T05:38:44Z"}
    @asynccontextmanager
    async def fake_client(*args):
        yield SimpleNamespace(booking=AsyncMock(side_effect=[remote, changed]))
    vault = SimpleNamespace(store_provider_credentials=AsyncMock())
    monkeypatch.setattr(api, "read_client", fake_client)
    monkeypatch.setattr(api, "require_read_allowed", lambda *_: None)
    monkeypatch.setattr(api, "get_secrets_manager", lambda: vault)
    payload = api.ReadSetup(client_id="synthetic-client", client_secret="synthetic-secret", reservation_id=NUMBER, confirmation="ENABLE_READ_RESERVATION:501694")
    with pytest.raises(HTTPException) as error:
        await api.connect_read_reservation(payload, SimpleNamespace(tenant_id="tenant-a", name="Synthetic Operator"), None)
    assert error.value.status_code == 409 and error.value.detail == "EXELY_READ_REMOTE_CHANGED"
    vault.store_provider_credentials.assert_not_awaited()
    assert database.exely_connections.documents[0]["read_reservation_enabled"] is False


async def test_explicit_test_consent_is_saved_only_after_remote_validation(monkeypatch, scenario):
    database, _, _, remote = scenario
    monkeypatch.setenv("E2E_EXTERNAL_DRY_RUN", "true")
    monkeypatch.setattr(read, "reservation_sync_block_reason", lambda: "")
    @asynccontextmanager
    async def fake_client(connection, credentials):
        read.require_read_allowed(connection)
        yield SimpleNamespace(booking=AsyncMock(return_value=remote))
    vault = SimpleNamespace(store_provider_credentials=AsyncMock())
    monkeypatch.setattr(api, "read_client", fake_client)
    monkeypatch.setattr(api, "get_secrets_manager", lambda: vault)
    payload = api.ReadSetup(client_id="synthetic-client", client_secret="synthetic-secret", reservation_id=NUMBER,
                            confirmation="ENABLE_READ_RESERVATION:501694", test_read_only_consent="ALLOW_TEST_READ:501694")
    await api.connect_read_reservation(payload, SimpleNamespace(tenant_id="tenant-a", name="Synthetic Operator"), None)
    connection = database.exely_connections.documents[0]
    assert connection["read_reservation_test_read_scope"] == read.test_read_scope(CONNECTION)
    read.require_read_allowed(connection)
    await api.pause_read_reservation(SimpleNamespace(tenant_id="tenant-a"), None)
    with pytest.raises(read.ReadReservationError, match="EXELY_READ_DRY_RUN"):
        read.require_read_allowed(database.exely_connections.documents[0])


@pytest.mark.parametrize("path", ["connect", "pause", "reconcile", "inspect"])
async def test_routes_enforce_permission_dependency_before_any_write(monkeypatch, path):
    app = FastAPI()
    app.include_router(api.router)
    async def user():
        return SimpleNamespace(tenant_id="tenant-a", name="Synthetic Viewer")
    async def forbidden():
        raise HTTPException(403, "FORBIDDEN")
    app.dependency_overrides[api.get_current_user] = user
    for route in api.router.routes:
        assert len(route.dependant.dependencies) == 2
        app.dependency_overrides[route.dependant.dependencies[1].call] = forbidden
    vault = SimpleNamespace(store_provider_credentials=AsyncMock())
    monkeypatch.setattr(api, "get_secrets_manager", lambda: vault)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(f"/read-reservation/{path}", json={"client_id": "synthetic-client", "client_secret": "synthetic-secret", "reservation_id": NUMBER, "confirmation": "ENABLE_READ_RESERVATION:501694"})
    assert response.status_code == 403
    vault.store_provider_credentials.assert_not_awaited()


async def test_test_booking_verification_reads_current_provenance_not_raw_bed_counts_or_old_audit(scenario, monkeypatch):
    from domains.channel_manager.providers.exely import exely_router

    database, reservation, _, remote = scenario
    monkeypatch.setattr(exely_router, "db", database)
    await demo.apply_plan("tenant-a", CONNECTION, reservation, await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote))
    request = exely_router.TestBookingVerifyRequest(reservation_id=NUMBER, expected_adults=2, expected_children_ages=[6])
    result = await exely_router._stored_test_booking_summary("tenant-a", CONNECTION, reservation, request)
    assert result["checks"]["guest_demographics"] == "passed"
    assert result["checks"]["expected_guest_counts"] == "matches_verified_counts"
    assert result["acceptance_status"] == "not_verified"  # Not a full commercial acceptance.
    database.bookings.documents[0]["children_ages"] = [7]  # Simulate a later manual correction.
    stale = await exely_router._stored_test_booking_summary("tenant-a", CONNECTION, reservation, request)
    assert stale["checks"]["guest_demographics"] == "not_verified"
    assert stale["acceptance_status"] == "mismatch"


@pytest.mark.live_mongo
@pytest.mark.parametrize("soap_version", [VERSION, "2026-10-22T08:38:48.677"])
@pytest.mark.parametrize("with_services", [False, True])
async def test_real_mongo_demographics_cas_immutable_source_and_tenant_isolation(scenario, local_mongo, monkeypatch, soap_version, with_services):
    database, reservation, booking, remote = scenario
    if with_services:
        database, reservation, remote = _observed_service_booking(scenario)
        booking = deepcopy(database.bookings.documents[0])
    reservation["provider_version_key"] = soap_version
    booking["provider_version_key"] = soap_version
    database.exely_reservations.documents[0]["provider_version_key"] = soap_version
    database.bookings.documents[0]["provider_version_key"] = soap_version
    for name in ("exely_connections", "exely_reservations", "exely_reservation_versions", "exely_room_mappings", "bookings"):
        await local_mongo[name].insert_many(deepcopy(getattr(database, name).documents))
    await local_mongo.bookings.insert_one({**deepcopy(booking), "tenant_id": "tenant-b"})
    monkeypatch.setattr(demo, "db", local_mongo)
    before_source = await local_mongo.exely_reservations.find_one({"tenant_id": "tenant-a"})
    plans = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    result = await demo.apply_plan("tenant-a", CONNECTION, reservation, plans)
    assert result["status"] == "verified"
    actual = await local_mongo.bookings.find_one({"tenant_id": "tenant-a", "id": "booking-a"})
    other = await local_mongo.bookings.find_one({"tenant_id": "tenant-b", "id": "booking-a"})
    assert actual["adults"] == 2 and actual["children_ages"] == ([] if with_services else [6]) and actual["_version"] == 1
    assert other["adults"] == booking["adults"] and other["children"] == 0
    assert actual["total_amount"] == booking["total_amount"] and actual["paid_amount"] == booking["paid_amount"]
    assert await local_mongo.exely_reservations.find_one({"tenant_id": "tenant-a"}) == before_source
    assert await local_mongo.exely_demographic_checks.count_documents({"tenant_id": "tenant-a"}) == 1
    stale = await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)
    await local_mongo.bookings.update_one({"tenant_id": "tenant-a", "id": "booking-a"}, {"$inc": {"_version": 1}})
    with pytest.raises(read.ReadReservationError, match="CONCURRENT_BOOKING_CHANGE"):
        await demo.apply_plan("tenant-a", CONNECTION, reservation, stale)


async def test_automatic_batch_only_reads_enabled_scoped_future_unverified_bookings(monkeypatch):
    connection_collection = SimpleNamespace(find_one=AsyncMock(return_value=CONNECTION))
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=[{"provider_group_reservation_id": NUMBER}]))
    cursor.sort = lambda fields: cursor
    bookings = SimpleNamespace(find=Mock(return_value=cursor))
    database = SimpleNamespace(exely_connections=connection_collection, bookings=bookings)
    monkeypatch.setattr(demo, "db", database)
    monkeypatch.setattr(demo, "saved_read_credentials", AsyncMock(return_value={"client_id": "synthetic", "client_secret": "synthetic"}))
    reconcile = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(demo, "reconcile_one", reconcile)
    @asynccontextmanager
    async def fake_client(*args):
        yield "synthetic-client"
    monkeypatch.setattr(demo, "read_client", fake_client)
    result = await demo.reconcile_pending("tenant-a", "501694")
    assert result == {"status": "verified", "verified": 1, "errors": []}
    reconcile.assert_awaited_once_with("tenant-a", CONNECTION, NUMBER, "synthetic-client")
    connection_collection.find_one.assert_awaited_once_with({"tenant_id": "tenant-a", "hotel_code": "501694", "is_active": True}, {"_id": 0})
    cursor.to_list.assert_awaited_once_with(25)
    scope = bookings.find.call_args.args[0]
    assert scope["tenant_id"] == "tenant-a" and scope["property_id"] == "501694"
    assert scope["booking_source"] == "exely" and scope["status"] == "confirmed"
    assert scope["exely_demographics.status"] == {"$ne": "verified"}
    assert "$gte" in scope["check_out"]


async def test_warmed_booking_projection_preserves_all_demographic_provenance(scenario):
    from cache_warmer import CacheWarmer

    _, reservation, booking, remote = scenario
    booking = {**booking, "exely_demographics": (await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote))[0]["proof"]}
    def find(_query, projection):
        cursor = SimpleNamespace(to_list=AsyncMock(return_value=[_project(booking, projection)]))
        cursor.limit = lambda _count: cursor
        return cursor
    warmer = CacheWarmer(SimpleNamespace(bookings=SimpleNamespace(count_documents=AsyncMock(return_value=1), find=find)))
    await warmer.warm_bookings_cache("tenant-a")
    warmed = warmer.cache["bookings:tenant-a"]["data"][0]
    for key in ("room_type", "property_id", "provider_group_reservation_id", "provider_version_key", "children_ages", "guests_count", "exely_demographics"):
        assert warmed[key] == booking[key]


@pytest.mark.parametrize("body", [b"not-json", b"[]", b" " * 2_000_001])
async def test_client_rejects_invalid_or_oversize_response_without_provider_data_leak(monkeypatch, body):
    monkeypatch.setenv("E2E_EXTERNAL_DRY_RUN", "false")
    monkeypatch.setattr(read, "reservation_sync_block_reason", lambda: "")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))) as http:
        client = read.ReadReservationClient(CONNECTION, {"client_id": "synthetic", "client_secret": "synthetic"}, _mock_request(http))
        with pytest.raises(read.ReadReservationError):
            await client.booking(NUMBER)


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_bounded_safe_request_keeps_dns_pinning_tls_host_and_rejects_large_decoded_bodies(monkeypatch, method):
    import gzip

    from integrations.xchange import safety

    target = "https://connect.test.hopenapi.com/auth/token"
    resolved = Mock(return_value=("connect.test.hopenapi.com", ("93.184.216.34",), 443))
    monkeypatch.setattr(safety, "_resolve_targets", resolved)
    response_body = b'{"synthetic":"body"}'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=gzip.compress(response_body), headers={"Content-Encoding": "gzip"}))
    pinned = Mock(return_value=transport)
    monkeypatch.setattr(safety, "_pinned_transport", pinned)
    response = await safety.safe_request_async(method, target, max_response_bytes=100)
    assert response.content == response_body and response.json() == {"synthetic": "body"}
    resolved.assert_called_once_with(target)
    pinned.assert_called_once_with("connect.test.hopenapi.com", ("93.184.216.34",))
    with pytest.raises(safety.EgressDenied, match="byte limit"):
        await safety.safe_request_async(method, target, max_response_bytes=5)
