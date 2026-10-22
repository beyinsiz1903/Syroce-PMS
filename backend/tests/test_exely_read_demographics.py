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
VERSION = "2026-10-22T05:38:43Z"
NUMBER = "20261110-501694-1200421078"


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


@pytest.mark.parametrize("target,key,value", [
    ("remote", "propertyId", "other-property"), ("remote", "number", "other-booking"),
    ("remote", "modifiedDateTime", "2026-10-22T05:38:44Z"), ("remote", "currencyCode", "EUR"),
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


async def test_identical_multiroom_stays_are_held_instead_of_distributing_children_by_index(scenario):
    _, reservation, _, remote = scenario
    reservation["rooms"].append(deepcopy(reservation["rooms"][0]))
    remote["roomStays"].append(deepcopy(remote["roomStays"][0]))
    with pytest.raises(read.ReadReservationError, match="ROOM_JOIN_AMBIGUOUS"):
        await demo.reconciliation_plan("tenant-a", CONNECTION, reservation, remote)


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
        client = read.ReadReservationClient({**CONNECTION, "endpoint_url": "https://attacker.invalid"}, {"client_id": "synthetic-client", "client_secret": "synthetic-secret"}, http)
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
        client = read.ReadReservationClient(CONNECTION, {"client_id": "synthetic-client", "client_secret": "synthetic-secret"}, http)
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
    monkeypatch.setattr(api, "require_read_allowed", lambda: None)
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


async def test_routes_enforce_permission_dependency_before_any_write(monkeypatch):
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
        response = await http.post("/read-reservation/connect", json={"client_id": "synthetic-client", "client_secret": "synthetic-secret", "reservation_id": NUMBER, "confirmation": "ENABLE_READ_RESERVATION:501694"})
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
async def test_real_mongo_demographics_cas_immutable_source_and_tenant_isolation(scenario, local_mongo, monkeypatch):
    database, reservation, booking, remote = scenario
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
    assert actual["adults"] == 2 and actual["children_ages"] == [6] and actual["_version"] == 1
    assert other["adults"] == 3 and other["children"] == 0
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
        client = read.ReadReservationClient(CONNECTION, {"client_id": "synthetic", "client_secret": "synthetic"}, http)
        with pytest.raises(read.ReadReservationError):
            await client.booking(NUMBER)
