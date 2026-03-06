import os
from datetime import datetime, timedelta

import pytest

from tests.harnesses.contract import (
    assert_iso_datetime_string,
    assert_optional_field_types,
    assert_required_keys,
    build_contract_snapshot,
)
from tests.harnesses.tenant_isolation import TenantIsolationHarness


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def harness():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not configured")
    return TenantIsolationHarness(base_url=BASE_URL)


@pytest.fixture(scope="module")
def demo_token(harness: TenantIsolationHarness):
    token = harness.login("demo@hotel.com", "demo123")
    if not token:
        pytest.skip("Demo admin login failed")
    return token


@pytest.fixture(scope="module")
def secondary_tenant(harness: TenantIsolationHarness):
    tenant = harness.register_tenant()
    if not tenant:
        pytest.skip("Secondary tenant registration failed")
    return tenant


@pytest.fixture(scope="module")
def secondary_token(secondary_tenant):
    return secondary_tenant.get("access_token")


@pytest.fixture(scope="module")
def sample_folio_id(harness: TenantIsolationHarness, demo_token: str):
    response, payload = harness.get_json("/api/folio/list?limit=1", demo_token)
    if response.status_code != 200:
        pytest.skip("Folio list unavailable")
    folios = payload.get("folios", []) if isinstance(payload, dict) else []
    if not folios:
        pytest.skip("No folio available for detail contract tests")
    return folios[0]["id"]


def _today_range() -> tuple[str, str]:
    today = datetime.utcnow().date()
    return today.isoformat(), (today + timedelta(days=1)).isoformat()


def test_bookings_contract_snapshot_unfiltered(harness: TenantIsolationHarness, demo_token: str):
    response, payload = harness.get_json("/api/pms/bookings?limit=5", demo_token)
    assert response.status_code == 200
    assert isinstance(payload, list)

    if payload:
        booking = payload[0]
        assert_required_keys(booking, ["id", "tenant_id", "room_id", "check_in", "check_out", "status"])
        assert_iso_datetime_string(booking["check_in"])
        assert_iso_datetime_string(booking["check_out"])
        assert_optional_field_types(booking, "guest_name", (str,))
        assert_optional_field_types(booking, "room_number", (str,))

        snapshot = build_contract_snapshot(booking)
        assert snapshot["id"] == "str"
        assert snapshot["tenant_id"] == "str"
        assert snapshot["status"] == "str"


def test_bookings_contract_snapshot_filtered(harness: TenantIsolationHarness, demo_token: str):
    response, payload = harness.get_json("/api/pms/bookings?status=checked_out&limit=5", demo_token)
    assert response.status_code == 200
    assert isinstance(payload, list)
    for booking in payload:
        assert booking["status"] == "checked_out"


def test_bookings_empty_list_shape(harness: TenantIsolationHarness, demo_token: str):
    response, payload = harness.get_json("/api/pms/bookings?status=__no_match__&limit=5", demo_token)
    assert response.status_code == 200
    assert payload == []


def test_bookings_missing_auth_rejected(harness: TenantIsolationHarness):
    response = harness.get_without_auth("/api/pms/bookings")
    assert response.status_code in {401, 403}


def test_bookings_cross_tenant_isolation(harness: TenantIsolationHarness, secondary_token: str):
    response, payload = harness.get_json("/api/pms/bookings?limit=5", secondary_token)
    assert response.status_code == 200
    assert payload == []


def test_bookings_property_header_behavior_stable(harness: TenantIsolationHarness, demo_token: str):
    baseline_response, baseline_payload = harness.get_json("/api/pms/bookings?limit=5", demo_token)
    scoped_response, scoped_payload = harness.get_json(
        "/api/pms/bookings?limit=5",
        demo_token,
        property_id="invalid-property-scope",
    )

    assert scoped_response.status_code == baseline_response.status_code
    assert isinstance(scoped_payload, type(baseline_payload))


def test_availability_response_shape(harness: TenantIsolationHarness, demo_token: str):
    check_in, check_out = _today_range()
    response, payload = harness.get_json(
        f"/api/pms/rooms/availability?check_in={check_in}&check_out={check_out}",
        demo_token,
    )
    assert response.status_code == 200
    assert isinstance(payload, list)

    if payload:
        room = payload[0]
        assert_required_keys(room, ["id", "tenant_id", "room_number", "room_type", "available"])
        assert isinstance(room["available"], bool)
        assert isinstance(room.get("capacity", 0), (int, float))
        assert_optional_field_types(room, "deleted_at", (str,))
        assert_optional_field_types(room, "notes", (str,))
        if not room["available"]:
            assert isinstance(room.get("reason"), str)
            assert isinstance(room.get("blocks", []), list)


def test_availability_empty_result_shape(harness: TenantIsolationHarness, demo_token: str):
    check_in, check_out = _today_range()
    response, payload = harness.get_json(
        f"/api/pms/rooms/availability?check_in={check_in}&check_out={check_out}&room_type=__NO_ROOM_TYPE__",
        demo_token,
    )
    assert response.status_code == 200
    assert payload == []


def test_availability_missing_auth_rejected(harness: TenantIsolationHarness):
    check_in, check_out = _today_range()
    response = harness.get_without_auth(f"/api/pms/rooms/availability?check_in={check_in}&check_out={check_out}")
    assert response.status_code in {401, 403}


def test_availability_cross_tenant_isolation(harness: TenantIsolationHarness, secondary_token: str):
    check_in, check_out = _today_range()
    response, payload = harness.get_json(
        f"/api/pms/rooms/availability?check_in={check_in}&check_out={check_out}",
        secondary_token,
    )
    assert response.status_code == 200
    assert payload == []


def test_availability_property_header_behavior_stable(harness: TenantIsolationHarness, demo_token: str):
    check_in, check_out = _today_range()
    path = f"/api/pms/rooms/availability?check_in={check_in}&check_out={check_out}"
    baseline_response, baseline_payload = harness.get_json(path, demo_token)
    scoped_response, scoped_payload = harness.get_json(path, demo_token, property_id="invalid-property-scope")
    assert scoped_response.status_code == baseline_response.status_code
    assert isinstance(scoped_payload, type(baseline_payload))


def test_folio_read_contract_snapshot(harness: TenantIsolationHarness, demo_token: str, sample_folio_id: str):
    response, payload = harness.get_json(f"/api/folio/{sample_folio_id}", demo_token)
    assert response.status_code == 200
    assert isinstance(payload, dict)
    assert_required_keys(payload, ["folio", "charges", "payments", "balance"])
    assert isinstance(payload["charges"], list)
    assert isinstance(payload["payments"], list)
    assert isinstance(payload["balance"], (int, float))

    folio = payload["folio"]
    assert_required_keys(folio, ["id", "tenant_id", "status"])
    assert_optional_field_types(folio, "currency", (str,))
    assert_optional_field_types(folio, "guest_id", (str,))
    assert_optional_field_types(folio, "booking_id", (str,))
    assert_optional_field_types(folio, "closed_at", (str,))


def test_folio_read_missing_folio_returns_404(harness: TenantIsolationHarness, demo_token: str):
    response, payload = harness.get_json("/api/folio/non-existent-folio-id", demo_token)
    assert response.status_code == 404
    assert isinstance(payload, dict)
    assert payload.get("detail") == "Folio not found"


def test_folio_missing_auth_rejected(harness: TenantIsolationHarness, sample_folio_id: str):
    response = harness.get_without_auth(f"/api/folio/{sample_folio_id}")
    assert response.status_code in {401, 403}


def test_folio_cross_tenant_isolation(harness: TenantIsolationHarness, secondary_token: str, sample_folio_id: str):
    response, payload = harness.get_json(f"/api/folio/{sample_folio_id}", secondary_token)
    assert response.status_code == 404
    assert isinstance(payload, dict)
    assert payload.get("detail") == "Folio not found"


def test_folio_property_header_behavior_stable(
    harness: TenantIsolationHarness,
    demo_token: str,
    sample_folio_id: str,
):
    path = f"/api/folio/{sample_folio_id}"
    baseline_response, baseline_payload = harness.get_json(path, demo_token)
    scoped_response, scoped_payload = harness.get_json(path, demo_token, property_id="invalid-property-scope")
    assert scoped_response.status_code == baseline_response.status_code
    assert isinstance(scoped_payload, type(baseline_payload))