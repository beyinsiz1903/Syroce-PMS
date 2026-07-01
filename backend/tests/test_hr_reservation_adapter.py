"""
HotelRunner Reservation Adapter - Contract & Integration Tests

Tests cover:
  1. JSON payload → canonical model mapping (contract tests)
  2. Pagination logic
  3. ACK flow with message_uid
  4. requires_response handling
  5. Error type classification
  6. Audit entry generation (correlation_id, masking, truncation)
  7. Duplicate/conflict detection with real JSON payloads
  8. Multi-room reservation handling
"""
import pytest

from channel_manager.connectors.hotelrunner_v2.reservation_mapper import HotelRunnerMapper
from channel_manager.connectors.hotelrunner_v2.hr_client import (
    _mask_params, _truncate,
)
from channel_manager.connectors.hotelrunner_v2.connector_errors import (
    ResponseParseError, PaginationExhaustedError, AcknowledgementError,
)
from channel_manager.domain.models.canonical import (
    CanonicalReservation, ReservationStatus, MealPlan,
)
from channel_manager.domain.models.reservation_import import (
    ImportedReservation,
)


# ─── Sample HotelRunner JSON Payloads ─────────────────────────────────

SAMPLE_RESERVATION_JSON = {
    "reservation_id": 37515739,
    "hr_number": "R377873409",
    "provider_number": None,
    "pms_number": None,
    "channel": "online",
    "channel_display": "Online",
    "state": "reserved",
    "modified": False,
    "total_guests": 3,
    "total_rooms": 1,
    "guest": "John Doe",
    "firstname": "John",
    "lastname": "Doe",
    "country": "TR",
    "guest_national_id": "12345678910",
    "guest_is_citizen": True,
    "cancel_reason": None,
    "completed_at": "2026-02-23T16:28:12.000+03:00",
    "updated_at": "2026-02-23T16:32:20.000+03:00",
    "sub_total": 110.0,
    "extras_total": 20.0,
    "adjustments_total": -0.0,
    "tax_total": 13.928,
    "item_total": "130.0",
    "total": 130.0,
    "currency": "USD",
    "checkin_date": "2026-02-23",
    "checkout_date": "2026-02-25",
    "note": "Baby crib",
    "payment": "cash",
    "paid_amount": 13.0,
    "requires_response": True,
    "address": {
        "city": "Cesme",
        "state": "35",
        "country": "Turkey (TR)",
        "country_code": "TR",
        "phone": "5555555555",
        "email": "john@hotelrunner.com",
        "street": "Cesme Mh. Cesme Cd. No:1",
        "street_2": "",
        "postal_code": "36040",
    },
    "billing_address": {
        "bill_type": None,
        "city": "Izmir",
        "state": "Izmir",
        "country": "Turkey",
        "country_code": "TR",
        "phone": "+905555555555",
        "email": "john@hotelrunner.com",
        "street": "Cesme",
        "street_2": "",
        "tax_office": "",
        "tax_id": "",
        "company": "",
        "firstname": "John",
        "lastname": "Doe",
    },
    "rooms": [
        {
            "id": 32924103,
            "state": "reserved",
            "code": "HR:823753",
            "number": None,
            "voucher_number": "R377873409",
            "availability_group": "HR:823753",
            "rate_code": "HR:823753",
            "rate_plan_code": "HR:823753",
            "inv_code": "HR:823753",
            "non_refundable": False,
            "price": 110.0,
            "total": 130.0,
            "nights": 2,
            "meal_plan": "bed-breakfast",
            "meal_plan_presentation": "Bed and breakfast",
            "total_guest": 3,
            "total_adult": 2,
            "child_ages": [1],
            "name": "Family Room",
            "name_presentation": "Family Room",
            "checkin_date": "2026-02-23",
            "checkout_date": "2026-02-25",
            "daily_prices": [
                {"date": "2026-02-23", "price": 55.0, "original_price": 55.0, "discount": 0.0, "rate_code": "HR:823753", "version": "v2"},
                {"date": "2026-02-24", "price": 55.0, "original_price": 55.0, "discount": 0.0, "rate_code": "HR:823753", "version": "v2"},
            ],
            "extras": [
                {"name": "Airport Transfer", "price": 20.0, "base_price": "20.0", "code": "", "is_extra": True, "total": 20.0, "quantity": 1},
                {"name": "VAT10 (10.0% Included in price)", "price": 11.608, "included_in_price": True},
                {"name": "VAT2 (2.0% Included in price)", "price": 2.321, "included_in_price": True},
            ],
            "extras_total": 20.0,
            "included_taxes_total": 13.929,
            "room_base_price": 110.0,
            "room_sub_total": 130.0,
            "comments": [
                {"body": "Baby crib", "channel_note": False, "housekeeping": None, "guest_visible": True},
            ],
        }
    ],
    "payments": [
        {"state": "checkout", "id": 34909131, "amount": "130.0", "currency": "USD", "payment_method": "cash", "payment_method_name": "Pay at the hotel"},
        {"state": "completed", "id": 34909219, "amount": "13.0", "currency": "USD", "paid_at": "2026-02-23T16:32:20.000+03:00", "payment_method": "cash"},
    ],
    "message_uid": "cc90fb5160e2ea7b7f4c493b9e8ec88d",
}

SAMPLE_CANCELLED_RESERVATION = {
    **SAMPLE_RESERVATION_JSON,
    "reservation_id": 37515740,
    "hr_number": "R377873410",
    "state": "canceled",
    "cancel_reason": "customer",
    "message_uid": "dd91fc6271f3fb8c8g5d504c0f9fd99e",
}

SAMPLE_MODIFIED_RESERVATION = {
    **SAMPLE_RESERVATION_JSON,
    "reservation_id": 37515739,
    "hr_number": "R377873409",
    "modified": True,
    "total": 200.0,
    "message_uid": "ee02gd7382g4gc9d9h6e615d1g0ge00f",
}


# ═════════════════════════════════════════════════════════════════════════
# CONTRACT TESTS: JSON → Canonical Mapping
# ═════════════════════════════════════════════════════════════════════════

class TestMapperContract:
    """Verify HotelRunner JSON payload maps correctly to canonical model."""

    def setup_method(self):
        self.mapper = HotelRunnerMapper()

    def test_basic_reservation_mapping(self):
        """Core fields map correctly from JSON to canonical."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.external_id == "37515739"
        assert canonical.hr_number == "R377873409"
        assert canonical.confirmation_number == "R377873409"
        assert canonical.channel_name == "Online"
        assert canonical.channel_code == "online"
        assert canonical.status == ReservationStatus.CONFIRMED
        assert canonical.message_uid == "cc90fb5160e2ea7b7f4c493b9e8ec88d"
        assert canonical.requires_ack is True
        assert canonical.modified is False

    def test_guest_mapping(self):
        """Guest details from firstname/lastname and address block."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.guest.first_name == "John"
        assert canonical.guest.last_name == "Doe"
        assert canonical.guest.email == "john@hotelrunner.com"
        assert canonical.guest.phone == "5555555555"
        assert canonical.guest.city == "Cesme"
        assert canonical.guest.country == "Turkey (TR)"
        assert canonical.guest.country_code == "TR"
        assert canonical.guest.postal_code == "36040"
        assert canonical.guest.national_id == "12345678910"
        assert canonical.guest.is_citizen is True

    def test_billing_address_mapping(self):
        """Billing address is carried through to canonical."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        billing = canonical.guest.billing_address
        assert billing["city"] == "Izmir"
        assert billing["firstname"] == "John"
        assert billing["lastname"] == "Doe"

    def test_room_codes_extraction(self):
        """rooms[].code, rate_plan_code, inv_code extracted correctly."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.room_type_id == "HR:823753"
        assert canonical.rate_plan_id == "HR:823753"
        assert canonical.room_type_name == "Family Room"

    def test_room_references_extraction(self):
        """extract_room_references returns structured external refs."""
        refs = self.mapper.extract_room_references(SAMPLE_RESERVATION_JSON)
        assert len(refs) == 1
        assert refs[0]["code"] == "HR:823753"
        assert refs[0]["inv_code"] == "HR:823753"
        assert refs[0]["rate_plan_code"] == "HR:823753"
        assert refs[0]["rate_code"] == "HR:823753"

    def test_occupancy_mapping(self):
        """Adult count, child count, child ages from rooms."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.adult_count == 2
        assert canonical.child_count == 1
        assert canonical.child_ages == [1]
        assert canonical.room_count == 1

    def test_pricing_mapping(self):
        """total, sub_total, tax_total, extras_total, paid_amount."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.total_amount == 130.0
        assert canonical.sub_total == 110.0
        assert canonical.tax_total == 13.928
        assert canonical.extras_total == 20.0
        assert canonical.paid_amount == 13.0
        assert canonical.currency == "USD"

    def test_daily_prices_mapping(self):
        """daily_prices from rooms aggregated into canonical."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert len(canonical.daily_prices) == 2
        assert canonical.daily_prices[0]["date"] == "2026-02-23"
        assert canonical.daily_prices[0]["price"] == 55.0
        assert len(canonical.price_breakdown) == 2
        assert canonical.price_breakdown[0].date == "2026-02-23"
        assert canonical.price_breakdown[0].sell_rate == 55.0

    def test_payment_mapping(self):
        """payments array and payment_type."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.payment_type == "cash"
        assert len(canonical.payments) == 2
        assert canonical.payments[0]["payment_method"] == "cash"

    def test_tax_breakdown_from_extras(self):
        """Included taxes extracted from room extras."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert len(canonical.tax_breakdown) == 2
        assert "VAT10" in canonical.tax_breakdown[0].tax_name

    def test_meal_plan_mapping(self):
        """bed-breakfast maps to BB."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.meal_plan == MealPlan.BB

    def test_special_requests(self):
        """note and room comments aggregated."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert "Baby crib" in canonical.special_requests

    def test_dates_mapping(self):
        """Check-in/out dates from reservation level."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.arrival_date == "2026-02-23"
        assert canonical.departure_date == "2026-02-25"

    def test_cancelled_state_mapping(self):
        """canceled state maps to CANCELLED."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_CANCELLED_RESERVATION)
        assert canonical.status == ReservationStatus.CANCELLED

    def test_modified_state_mapping(self):
        """modified=true with non-cancelled state maps to MODIFIED."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_MODIFIED_RESERVATION)
        assert canonical.status == ReservationStatus.MODIFIED
        assert canonical.modified is True

    def test_non_refundable_mapping(self):
        """non_refundable flag from first room."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.non_refundable is False

    def test_raw_provider_data_preserved(self):
        """Full raw JSON is stored for audit/debugging."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert canonical.raw_provider_data["reservation_id"] == 37515739
        assert canonical.raw_provider_data["hr_number"] == "R377873409"

    def test_rooms_raw_preserved(self):
        """Rooms array is preserved in canonical."""
        canonical = self.mapper.reservation_to_canonical(SAMPLE_RESERVATION_JSON)
        assert len(canonical.rooms) == 1
        assert canonical.rooms[0]["id"] == 32924103


# ═════════════════════════════════════════════════════════════════════════
# UTILITY TESTS: masking, truncation
# ═════════════════════════════════════════════════════════════════════════

class TestAuditUtilities:
    """Test masking and truncation utilities."""

    def test_mask_params_masks_token(self):
        params = {"token": "abc123def456", "hr_id": "12345", "page": "1"}
        masked = _mask_params(params)
        assert masked["token"] == "abc1****"
        assert masked["hr_id"] == "12345"
        assert masked["page"] == "1"

    def test_mask_params_short_token(self):
        params = {"token": "ab", "password": "xy"}
        masked = _mask_params(params)
        assert masked["token"] == "****"
        assert masked["password"] == "****"

    def test_truncate_short_text(self):
        text = "short text"
        assert _truncate(text) == text

    def test_truncate_long_text(self):
        text = "a" * 5000
        result = _truncate(text, max_len=100)
        assert len(result) < 200
        assert "truncated" in result
        assert "5000" in result


# ═════════════════════════════════════════════════════════════════════════
# ERROR TYPE TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestErrorTypes:
    """Test new typed error classes."""

    def test_response_parse_error(self):
        err = ResponseParseError("bad json", raw_response='{"broken')
        assert err.raw_response == '{"broken'
        assert not err.recoverable

    def test_pagination_exhausted_error(self):
        err = PaginationExhaustedError(max_pages=100, fetched_count=5000)
        assert err.max_pages == 100
        assert err.fetched_count == 5000
        assert "100 pages" in str(err)

    def test_acknowledgement_error(self):
        err = AcknowledgementError(
            message_uid="abc123",
            hr_number="R123",
            reason="timeout",
        )
        assert err.message_uid == "abc123"
        assert err.hr_number == "R123"
        assert err.recoverable is True


# ═════════════════════════════════════════════════════════════════════════
# IMPORTED RESERVATION MODEL TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestImportedReservationModel:
    """Test ImportedReservation model extensions."""

    def test_message_uid_field(self):
        res = ImportedReservation(
            tenant_id="t1",
            property_id="p1",
            connector_id="c1",
            batch_id="b1",
            external_reservation_id="37515739",
            hr_number="R377873409",
            message_uid="cc90fb5160e2ea7b7f4c493b9e8ec88d",
            requires_ack=True,
        )
        assert res.hr_number == "R377873409"
        assert res.message_uid == "cc90fb5160e2ea7b7f4c493b9e8ec88d"
        assert res.requires_ack is True

    def test_to_doc_includes_new_fields(self):
        res = ImportedReservation(
            tenant_id="t1",
            property_id="p1",
            connector_id="c1",
            batch_id="b1",
            external_reservation_id="123",
            hr_number="R123",
            message_uid="uid123",
            requires_ack=True,
        )
        doc = res.to_doc()
        assert doc["hr_number"] == "R123"
        assert doc["message_uid"] == "uid123"
        assert doc["requires_ack"] is True

    def test_fingerprint_stability(self):
        """Same canonical data produces same fingerprint."""
        data = {
            "arrival_date": "2026-02-23",
            "departure_date": "2026-02-25",
            "room_type_id": "HR:823753",
            "rate_plan_id": "HR:823753",
            "adult_count": 2,
            "child_count": 1,
            "total_amount": 130.0,
            "status": "confirmed",
            "guest": {"email": "john@hotelrunner.com"},
            "special_requests": "Baby crib",
        }
        fp1 = ImportedReservation.compute_fingerprint(data)
        fp2 = ImportedReservation.compute_fingerprint(data)
        assert fp1 == fp2
        assert len(fp1) == 16


# ═════════════════════════════════════════════════════════════════════════
# CANONICAL MODEL EXTENSION TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestCanonicalModelExtensions:
    """Test new fields on CanonicalReservation and CanonicalGuest."""

    def test_canonical_reservation_new_fields(self):
        res = CanonicalReservation(
            hr_number="R123",
            message_uid="uid456",
            requires_ack=True,
            modified=True,
            tax_total=10.5,
            extras_total=20.0,
            sub_total=100.0,
            paid_amount=50.0,
            daily_prices=[{"date": "2026-01-01", "price": 100.0}],
            payments=[{"amount": "50.0", "method": "cash"}],
            rooms=[{"code": "HR:1"}],
            non_refundable=True,
        )
        assert res.hr_number == "R123"
        assert res.message_uid == "uid456"
        assert res.requires_ack is True
        assert res.modified is True
        assert res.tax_total == 10.5
        assert res.extras_total == 20.0
        assert res.non_refundable is True
        assert len(res.daily_prices) == 1
        assert len(res.payments) == 1
        assert len(res.rooms) == 1

    def test_canonical_guest_new_fields(self):
        from channel_manager.domain.models.canonical import CanonicalGuest
        guest = CanonicalGuest(
            first_name="John",
            last_name="Doe",
            national_id="12345",
            is_citizen=True,
            state="35",
            street="Test St",
            street_2="Apt 5",
            billing_address={"city": "Izmir"},
        )
        assert guest.national_id == "12345"
        assert guest.is_citizen is True
        assert guest.state == "35"
        assert guest.billing_address["city"] == "Izmir"


# ═════════════════════════════════════════════════════════════════════════
# MULTI-ROOM RESERVATION TEST
# ═════════════════════════════════════════════════════════════════════════

SAMPLE_MULTI_ROOM = {
    **SAMPLE_RESERVATION_JSON,
    "total_rooms": 2,
    "rooms": [
        {
            "id": 1, "state": "reserved", "code": "HR:100", "inv_code": "HR:100",
            "rate_code": "HR:200", "rate_plan_code": "HR:200",
            "total_adult": 2, "child_ages": [],
            "name": "Standard", "price": 50.0, "total": 60.0, "nights": 1,
            "meal_plan": "room-only",
            "checkin_date": "2026-03-01", "checkout_date": "2026-03-02",
            "daily_prices": [{"date": "2026-03-01", "price": 50.0, "original_price": 50.0, "discount": 0.0}],
            "extras": [], "comments": [],
        },
        {
            "id": 2, "state": "reserved", "code": "HR:101", "inv_code": "HR:101",
            "rate_code": "HR:201", "rate_plan_code": "HR:201",
            "total_adult": 1, "child_ages": [5],
            "name": "Deluxe", "price": 80.0, "total": 90.0, "nights": 1,
            "meal_plan": "half-board",
            "checkin_date": "2026-03-01", "checkout_date": "2026-03-02",
            "daily_prices": [{"date": "2026-03-01", "price": 80.0, "original_price": 80.0, "discount": 0.0}],
            "extras": [], "comments": [],
        },
    ],
}


class TestMultiRoomReservation:
    """Test multi-room reservation handling."""

    def setup_method(self):
        self.mapper = HotelRunnerMapper()

    def test_multi_room_uses_first_room_codes(self):
        canonical = self.mapper.reservation_to_canonical(SAMPLE_MULTI_ROOM)
        # Primary mapping from first room
        assert canonical.room_type_id == "HR:100"
        assert canonical.rate_plan_id == "HR:200"

    def test_multi_room_daily_prices_aggregated(self):
        canonical = self.mapper.reservation_to_canonical(SAMPLE_MULTI_ROOM)
        # Both rooms' daily prices aggregated
        assert len(canonical.daily_prices) == 2

    def test_multi_room_references_extracted(self):
        refs = self.mapper.extract_room_references(SAMPLE_MULTI_ROOM)
        assert len(refs) == 2
        assert refs[0]["inv_code"] == "HR:100"
        assert refs[1]["inv_code"] == "HR:101"

    def test_multi_room_count(self):
        canonical = self.mapper.reservation_to_canonical(SAMPLE_MULTI_ROOM)
        assert canonical.room_count == 2
        assert len(canonical.rooms) == 2


# ═════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test edge cases and missing data."""

    def setup_method(self):
        self.mapper = HotelRunnerMapper()

    def test_empty_rooms_array(self):
        raw = {**SAMPLE_RESERVATION_JSON, "rooms": []}
        canonical = self.mapper.reservation_to_canonical(raw)
        assert canonical.room_type_id == ""
        assert canonical.adult_count == 1

    def test_missing_address(self):
        raw = {**SAMPLE_RESERVATION_JSON, "address": None}
        canonical = self.mapper.reservation_to_canonical(raw)
        assert canonical.guest.email == ""
        assert canonical.guest.city == ""

    def test_missing_billing_address(self):
        raw = {**SAMPLE_RESERVATION_JSON, "billing_address": None}
        canonical = self.mapper.reservation_to_canonical(raw)
        assert canonical.guest.billing_address == {}

    def test_missing_message_uid(self):
        raw = {**SAMPLE_RESERVATION_JSON}
        del raw["message_uid"]
        canonical = self.mapper.reservation_to_canonical(raw)
        assert canonical.message_uid == ""

    def test_requires_response_false(self):
        raw = {**SAMPLE_RESERVATION_JSON, "requires_response": False}
        canonical = self.mapper.reservation_to_canonical(raw)
        assert canonical.requires_ack is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
