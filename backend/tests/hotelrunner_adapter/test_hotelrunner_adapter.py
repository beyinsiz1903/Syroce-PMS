"""
HotelRunner Adapter — Unit Tests
==================================

Tests for all 12 modules:
- auth, endpoints, errors, retry, validators
- parser, mapper, paginator
- observability, schemas, client, provider
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

# ── Module imports ────────────────────────────────────────────────────

from domains.channel_manager.providers.hotelrunner.auth import (
    build_auth_params, validate_credentials, extract_credentials,
)
from domains.channel_manager.providers.hotelrunner import endpoints as ep
from domains.channel_manager.providers.hotelrunner.errors import (
    HotelRunnerError, HotelRunnerAuthError, HotelRunnerRateLimitError,
    HotelRunnerTemporaryError, HotelRunnerPayloadError, HotelRunnerParseError,
    HotelRunnerMappingError, HotelRunnerPaginationError, HotelRunnerValidationError,
)
from domains.channel_manager.providers.hotelrunner.retry import HotelRunnerRetryPolicy
from domains.channel_manager.providers.hotelrunner.validators import (
    validate_connection_credentials, validate_inventory_payload,
    validate_room_mapping, validate_reservation_pull_params,
)
from domains.channel_manager.providers.hotelrunner.parser import (
    parse_rooms_response, parse_channels_response,
    parse_connected_channels_response, parse_reservations_response,
)
from domains.channel_manager.providers.hotelrunner.mapper import (
    map_reservation_to_canonical, map_raw_payload_to_canonical,
    map_ari_delta_to_daily_payload, map_ari_delta_to_daterange_payload,
)
from domains.channel_manager.providers.hotelrunner.paginator import HotelRunnerPaginator
from domains.channel_manager.providers.hotelrunner.observability import (
    record_provider_call, get_provider_health, reset_metrics,
)
from domains.channel_manager.providers.hotelrunner.schemas import (
    ProviderResult, HotelRunnerRoom, HotelRunnerReservation, InventoryDateRangePayload,
)


# ══════════════════════════════════════════════════════════════════════
# 1. Auth Tests
# ══════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_build_auth_params(self):
        params = build_auth_params("tok123", "hr456")
        assert params == {"token": "tok123", "hr_id": "hr456"}

    def test_validate_credentials_valid(self):
        validate_credentials("valid_token", "valid_hr_id")

    def test_validate_credentials_empty_token(self):
        with pytest.raises(HotelRunnerAuthError, match="token"):
            validate_credentials("", "hr_id")

    def test_validate_credentials_empty_hr_id(self):
        with pytest.raises(HotelRunnerAuthError, match="HR ID"):
            validate_credentials("token", "")

    def test_extract_credentials_standard(self):
        t, h = extract_credentials({"token": "abc", "hr_id": "xyz"})
        assert t == "abc"
        assert h == "xyz"

    def test_extract_credentials_aliases(self):
        t, h = extract_credentials({"api_key": "abc", "hotel_id": "xyz"})
        assert t == "abc"
        assert h == "xyz"

    def test_extract_credentials_strips_whitespace(self):
        t, h = extract_credentials({"token": "  abc  ", "hr_id": " xyz "})
        assert t == "abc"
        assert h == "xyz"


# ══════════════════════════════════════════════════════════════════════
# 2. Endpoints Tests
# ══════════════════════════════════════════════════════════════════════

class TestEndpoints:
    def test_rooms_path(self):
        assert "/rooms" in ep.ROOMS
        assert ep.ROOMS.startswith(ep.V2_PREFIX)

    def test_reservations_path(self):
        assert "/reservations" in ep.RESERVATIONS

    def test_channels_path(self):
        assert "/channels" in ep.CHANNELS

    def test_rooms_daily(self):
        assert "/daily" in ep.ROOMS_DAILY

    def test_base_url(self):
        assert ep.BASE_URL == "https://app.hotelrunner.com"


# ══════════════════════════════════════════════════════════════════════
# 3. Error Tests
# ══════════════════════════════════════════════════════════════════════

class TestErrors:
    def test_base_error(self):
        e = HotelRunnerError("test", recoverable=True)
        assert e.recoverable is True
        assert str(e) == "test"

    def test_auth_error_not_recoverable(self):
        e = HotelRunnerAuthError("bad creds")
        assert e.recoverable is False

    def test_rate_limit_error_recoverable(self):
        e = HotelRunnerRateLimitError(retry_after_seconds=30)
        assert e.recoverable is True
        assert e.retry_after_seconds == 30

    def test_temporary_error_recoverable(self):
        e = HotelRunnerTemporaryError()
        assert e.recoverable is True

    def test_payload_error_not_recoverable(self):
        e = HotelRunnerPayloadError("bad payload", details={"field": "inv_code"})
        assert e.recoverable is False
        assert e.details == {"field": "inv_code"}

    def test_parse_error_stores_raw(self):
        e = HotelRunnerParseError("bad json", raw_response="x" * 3000)
        assert len(e.raw_response) <= 2000

    def test_mapping_error(self):
        e = HotelRunnerMappingError("no mapping", entity_type="room", entity_id="STD")
        assert e.entity_type == "room"

    def test_pagination_error(self):
        e = HotelRunnerPaginationError(max_pages=50, fetched_count=2500)
        assert e.max_pages == 50

    def test_error_hierarchy(self):
        assert issubclass(HotelRunnerAuthError, HotelRunnerError)
        assert issubclass(HotelRunnerRateLimitError, HotelRunnerError)
        assert issubclass(HotelRunnerTemporaryError, HotelRunnerError)


# ══════════════════════════════════════════════════════════════════════
# 4. Retry Tests
# ══════════════════════════════════════════════════════════════════════

class TestRetry:
    def test_should_retry_auth_error(self):
        policy = HotelRunnerRetryPolicy(max_retries=3)
        assert policy.should_retry(HotelRunnerAuthError(), 1) is False

    def test_should_retry_rate_limit(self):
        policy = HotelRunnerRetryPolicy(max_retries=3)
        assert policy.should_retry(HotelRunnerRateLimitError(), 1) is True

    def test_should_retry_temporary(self):
        policy = HotelRunnerRetryPolicy(max_retries=3)
        assert policy.should_retry(HotelRunnerTemporaryError(), 1) is True

    def test_should_not_retry_payload_error(self):
        policy = HotelRunnerRetryPolicy(max_retries=3)
        assert policy.should_retry(HotelRunnerPayloadError(), 1) is False

    def test_should_not_retry_parse_error(self):
        policy = HotelRunnerRetryPolicy(max_retries=3)
        assert policy.should_retry(HotelRunnerParseError(), 1) is False

    def test_should_not_retry_mapping_error(self):
        policy = HotelRunnerRetryPolicy(max_retries=3)
        assert policy.should_retry(HotelRunnerMappingError(), 1) is False

    def test_max_retries_exceeded(self):
        policy = HotelRunnerRetryPolicy(max_retries=3)
        # attempt=4 means we've exhausted 3 retries
        assert policy.should_retry(HotelRunnerTemporaryError(), 4) is False
        assert policy.should_retry(HotelRunnerTemporaryError(), 5) is False

    def test_backoff_exponential(self):
        policy = HotelRunnerRetryPolicy(base_delay=2.0, jitter=0.0)
        assert policy.get_backoff_seconds(0) == 2.0
        assert policy.get_backoff_seconds(1) == 4.0
        assert policy.get_backoff_seconds(2) == 8.0

    def test_backoff_rate_limit_uses_retry_after(self):
        policy = HotelRunnerRetryPolicy()
        e = HotelRunnerRateLimitError(retry_after_seconds=45)
        assert policy.get_backoff_seconds(0, e) == 45.0

    def test_backoff_max_delay(self):
        policy = HotelRunnerRetryPolicy(base_delay=2.0, max_delay=10.0, jitter=0.0)
        assert policy.get_backoff_seconds(10) == 10.0


# ══════════════════════════════════════════════════════════════════════
# 5. Validator Tests
# ══════════════════════════════════════════════════════════════════════

class TestValidators:
    def test_valid_credentials(self):
        validate_connection_credentials("abcdefgh", "hr12345")

    def test_empty_token(self):
        with pytest.raises(HotelRunnerValidationError, match="token"):
            validate_connection_credentials("", "hr123")

    def test_short_token(self):
        with pytest.raises(HotelRunnerValidationError, match="short"):
            validate_connection_credentials("abc", "hr123")

    def test_valid_inventory_payload(self):
        validate_inventory_payload({"inv_code": "STD", "start_date": "2026-04-01", "availability": 5})

    def test_missing_inv_code(self):
        with pytest.raises(HotelRunnerValidationError, match="inv_code"):
            validate_inventory_payload({"start_date": "2026-04-01", "availability": 5})

    def test_missing_date(self):
        with pytest.raises(HotelRunnerValidationError, match="date"):
            validate_inventory_payload({"inv_code": "STD", "availability": 5})

    def test_no_update_fields(self):
        with pytest.raises(HotelRunnerValidationError, match="update field"):
            validate_inventory_payload({"inv_code": "STD", "start_date": "2026-04-01"})

    def test_valid_room_mapping(self):
        validate_room_mapping({"external_code": "HR-STD"}, "STD")

    def test_missing_room_mapping(self):
        with pytest.raises(HotelRunnerMappingError):
            validate_room_mapping(None, "STD")

    def test_empty_external_code(self):
        with pytest.raises(HotelRunnerMappingError):
            validate_room_mapping({"external_code": ""}, "STD")

    def test_valid_pull_params(self):
        validate_reservation_pull_params(per_page=50, page=1)

    def test_invalid_per_page(self):
        with pytest.raises(HotelRunnerValidationError):
            validate_reservation_pull_params(per_page=200)


# ══════════════════════════════════════════════════════════════════════
# 6. Parser Tests
# ══════════════════════════════════════════════════════════════════════

class TestParser:
    def test_parse_rooms_response(self):
        data = {"rooms": [
            {"inv_code": "STD", "name": "Standard", "rate_plans": [{"code": "BAR"}]},
            {"inv_code": "DLX", "name": "Deluxe"},
        ]}
        rooms = parse_rooms_response(data)
        assert len(rooms) == 2
        assert rooms[0].inv_code == "STD"
        assert rooms[1].name == "Deluxe"

    def test_parse_rooms_empty(self):
        rooms = parse_rooms_response({"rooms": []})
        assert len(rooms) == 0

    def test_parse_rooms_not_list(self):
        with pytest.raises(HotelRunnerParseError):
            parse_rooms_response({"rooms": "invalid"})

    def test_parse_channels_response(self):
        data = {"channels": [{"code": "booking", "name": "Booking.com"}]}
        channels = parse_channels_response(data)
        assert len(channels) == 1
        assert channels[0].code == "booking"

    def test_parse_connected_channels(self):
        data = {"connected_channels": [{"code": "exp", "name": "Expedia", "status": "active"}]}
        channels = parse_connected_channels_response(data)
        assert len(channels) == 1
        assert channels[0].status == "active"

    def test_parse_reservations_response(self):
        data = {
            "reservations": [{
                "reservation_id": "123",
                "hr_number": "HR-001",
                "state": "reserved",
                "firstname": "Ali",
                "lastname": "Yilmaz",
                "checkin_date": "2026-04-10",
                "checkout_date": "2026-04-15",
                "total": 5000,
                "currency": "TRY",
                "rooms": [{"inv_code": "STD", "total_adult": 2}],
            }],
            "pages": 3,
            "page": 1,
        }
        page = parse_reservations_response(data)
        assert len(page.reservations) == 1
        assert page.reservations[0].hr_number == "HR-001"
        assert page.reservations[0].guest_firstname == "Ali"
        assert page.total_pages == 3
        assert page.reservations[0].adults == 2

    def test_parse_reservations_empty(self):
        page = parse_reservations_response({"reservations": [], "pages": 1})
        assert len(page.reservations) == 0


# ══════════════════════════════════════════════════════════════════════
# 7. Mapper Tests
# ══════════════════════════════════════════════════════════════════════

class TestMapper:
    def test_map_reservation_to_canonical(self):
        res = HotelRunnerReservation(
            reservation_id="123", hr_number="HR-001",
            status="reserved", guest_firstname="Ali", guest_lastname="Yilmaz",
            guest_email="ali@test.com", check_in="2026-04-10", check_out="2026-04-15",
            room_type_code="STD", rate_plan_code="BAR",
            adults=2, total_amount=5000, currency="TRY",
            channel="booking.com",
        )
        canonical = map_reservation_to_canonical(res)
        assert canonical["external_reservation_id"] == "HR-001"
        assert canonical["provider"] == "hotelrunner"
        assert canonical["guest_name"] == "Ali Yilmaz"
        assert canonical["status"] == "confirmed"
        assert canonical["total_amount"] == 5000
        assert canonical["room_type_code"] == "STD"

    def test_map_raw_payload_cancelled(self):
        raw = {
            "hr_number": "HR-002",
            "state": "cancelled",
            "firstname": "Test",
            "lastname": "User",
            "checkin_date": "2026-05-01",
            "checkout_date": "2026-05-03",
            "total": 3000,
            "currency": "TRY",
            "rooms": [],
        }
        canonical = map_raw_payload_to_canonical(raw)
        assert canonical["status"] == "cancelled"

    def test_map_raw_payload_modified(self):
        raw = {
            "hr_number": "HR-003",
            "state": "confirmed",
            "modified": True,
            "firstname": "Mod",
            "lastname": "User",
            "checkin_date": "2026-05-01",
            "checkout_date": "2026-05-03",
            "total": 2000,
            "rooms": [],
        }
        canonical = map_raw_payload_to_canonical(raw)
        assert canonical["status"] == "modified"

    def test_map_ari_daily_payload(self):
        delta = {"date": "2026-04-15", "availability": 5, "price": 1200}
        mapping = {"external_code": "HR-STD"}
        result = map_ari_delta_to_daily_payload(delta, mapping)
        assert result["inv_code"] == "HR-STD"
        assert result["date"] == "2026-04-15"
        assert result["availability"] == "5"
        assert result["price"] == "1200"

    def test_map_ari_daterange_payload(self):
        delta = {
            "start_date": "2026-04-15",
            "end_date": "2026-04-20",
            "availability": 3,
            "min_stay": 2,
        }
        mapping = {"external_code": "HR-DLX"}
        result = map_ari_delta_to_daterange_payload(delta, mapping)
        assert result["inv_code"] == "HR-DLX"
        assert result["start_date"] == "2026-04-15"
        assert result["end_date"] == "2026-04-20"
        assert result["min_stay"] == "2"


# ══════════════════════════════════════════════════════════════════════
# 8. Paginator Tests
# ══════════════════════════════════════════════════════════════════════

class TestPaginator:
    @pytest.mark.asyncio
    async def test_single_page(self):
        paginator = HotelRunnerPaginator(max_pages=10)

        async def fetch(page):
            return {"reservations": [{"hr_number": f"HR-{page}"}], "pages": 1}

        items = await paginator.fetch_all_pages(fetch)
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_multiple_pages(self):
        paginator = HotelRunnerPaginator(max_pages=10)

        async def fetch(page):
            return {"reservations": [{"hr_number": f"HR-{page}"}], "pages": 3}

        items = await paginator.fetch_all_pages(fetch)
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_empty_page_stops(self):
        paginator = HotelRunnerPaginator(max_pages=10)

        async def fetch(page):
            if page > 2:
                return {"reservations": [], "pages": 5}
            return {"reservations": [{"hr_number": f"HR-{page}"}], "pages": 5}

        items = await paginator.fetch_all_pages(fetch)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_duplicate_page_detection(self):
        paginator = HotelRunnerPaginator(max_pages=10)
        call_count = 0

        async def fetch(page):
            nonlocal call_count
            call_count += 1
            return {"reservations": [{"hr_number": "HR-SAME"}], "pages": 5}

        items = await paginator.fetch_all_pages(fetch)
        # Should stop after detecting duplicate first_id
        assert call_count == 2  # First page OK, second page detected as duplicate

    @pytest.mark.asyncio
    async def test_max_pages_safety(self):
        paginator = HotelRunnerPaginator(max_pages=3)

        async def fetch(page):
            return {"reservations": [{"hr_number": f"HR-{page}"}], "pages": 100}

        with pytest.raises(HotelRunnerPaginationError):
            await paginator.fetch_all_pages(fetch)


# ══════════════════════════════════════════════════════════════════════
# 9. Observability Tests
# ══════════════════════════════════════════════════════════════════════

class TestObservability:
    def setup_method(self):
        reset_metrics()

    def test_record_success(self):
        record_provider_call(
            path="/test", method="GET", status_code=200,
            duration_ms=150, success=True,
        )
        health = get_provider_health()
        assert health["success_count"] == 1
        assert health["call_count"] == 1
        assert health["success_rate_pct"] == 100.0

    def test_record_failure(self):
        record_provider_call(
            path="/test", method="GET", status_code=500,
            duration_ms=200, success=False,
        )
        health = get_provider_health()
        assert health["error_count"] == 1
        assert health["success_rate_pct"] == 0.0

    def test_mixed_calls(self):
        for _ in range(8):
            record_provider_call(path="/t", method="GET", status_code=200, duration_ms=100, success=True)
        for _ in range(2):
            record_provider_call(path="/t", method="GET", status_code=500, duration_ms=200, success=False)
        health = get_provider_health()
        assert health["call_count"] == 10
        assert health["success_rate_pct"] == 80.0


# ══════════════════════════════════════════════════════════════════════
# 10. Schema Tests
# ══════════════════════════════════════════════════════════════════════

class TestSchemas:
    def test_provider_result_success(self):
        r = ProviderResult(success=True, data={"rooms": []}, duration_ms=100)
        assert r.success is True
        assert r.error == ""

    def test_provider_result_failure(self):
        r = ProviderResult(success=False, error="timeout", error_type="HotelRunnerTemporaryError")
        assert r.success is False
        assert "timeout" in r.error

    def test_hotel_runner_room(self):
        room = HotelRunnerRoom(inv_code="STD", name="Standard")
        assert room.inv_code == "STD"
        assert room.rate_plans == []

    def test_inventory_payload(self):
        p = InventoryDateRangePayload(
            inv_code="STD", start_date="2026-04-15", end_date="2026-04-20",
            availability=5, price=1200.0,
        )
        assert p.inv_code == "STD"
        assert p.availability == 5
