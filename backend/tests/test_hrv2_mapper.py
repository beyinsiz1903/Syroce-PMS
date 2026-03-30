"""
HotelRunner v2 — Unit Tests (Mapper + Idempotency)
====================================================

Tests:
  1. reservation_to_canonical — various payload formats
  2. extract_identity — event dedup fields
  3. compute_idempotency_key — hash stability
  4. compute_payload_hash — change detection
  5. ari_to_daterange_payload — outbound mapping
  6. detect_event_type — event classification
"""
import pytest

from channel_manager.connectors.hotelrunner_v2.mapper import (
    ari_to_daterange_payload,
    ari_to_daily_payload,
    compute_idempotency_key,
    compute_payload_hash,
    detect_event_type,
    extract_identity,
    reservation_to_canonical,
)


# ── Reservation → Canonical ──────────────────────────────────────────

class TestReservationToCanonical:
    def test_full_hr_api_format(self):
        """Real HotelRunner API payload format."""
        raw = {
            "hr_number": "HR-12345",
            "firstname": "Ali",
            "lastname": "Yilmaz",
            "checkin_date": "2026-04-10",
            "checkout_date": "2026-04-15",
            "address": {"email": "ali@test.com", "phone": "+905551234567"},
            "rooms": [{"room_code": "STD", "rate_code": "RACK", "adults": 2, "children": 1}],
            "total": 5000.0,
            "currency": "TRY",
            "state": "confirmed",
            "channel": "booking.com",
            "updated_at": "2026-04-09T10:00:00Z",
        }
        c = reservation_to_canonical(raw)
        assert c["external_reservation_id"] == "HR-12345"
        assert c["guest_name"] == "Ali Yilmaz"
        assert c["guest_email"] == "ali@test.com"
        assert c["check_in"] == "2026-04-10"
        assert c["check_out"] == "2026-04-15"
        assert c["room_type_code"] == "STD"
        assert c["rate_plan_code"] == "RACK"
        assert c["adults"] == 2
        assert c["children"] == 1
        assert c["total_amount"] == 5000.0
        assert c["status"] == "confirmed"
        assert c["provider"] == "hotelrunner"

    def test_simplified_format(self):
        """Test format with direct guest dict."""
        raw = {
            "hr_number": "HR-99",
            "guest": {"first_name": "Mehmet", "last_name": "Demir", "email": "m@t.com"},
            "check_in": "2026-05-01",
            "check_out": "2026-05-03",
            "room_type": "DLX",
            "rate_plan": "BAR",
            "total": 2500.0,
            "status": "confirmed",
        }
        c = reservation_to_canonical(raw)
        assert c["guest_name"] == "Mehmet Demir"
        assert c["room_type_code"] == "DLX"
        assert c["rate_plan_code"] == "BAR"

    def test_string_guest(self):
        """HR sometimes sends guest as a string."""
        raw = {
            "hr_number": "HR-77",
            "guest": "Ayse Kaya",
            "check_in": "2026-06-01",
            "check_out": "2026-06-02",
            "total": 1000.0,
            "state": "new",
        }
        c = reservation_to_canonical(raw)
        assert c["guest_name"] == "Ayse Kaya"
        assert c["status"] == "confirmed"  # "new" maps to "confirmed"

    def test_cancelled_status(self):
        raw = {
            "hr_number": "HR-CC",
            "state": "cancelled",
            "check_in": "2026-07-01",
            "check_out": "2026-07-02",
        }
        c = reservation_to_canonical(raw)
        assert c["status"] == "cancelled"

    def test_modified_flag_override(self):
        raw = {
            "hr_number": "HR-MO",
            "state": "confirmed",
            "modified": True,
            "check_in": "2026-07-01",
            "check_out": "2026-07-02",
        }
        c = reservation_to_canonical(raw)
        assert c["status"] == "modified"

    def test_empty_rooms(self):
        raw = {
            "hr_number": "HR-EMPTY",
            "rooms": [],
            "check_in": "2026-08-01",
            "check_out": "2026-08-02",
        }
        c = reservation_to_canonical(raw)
        assert c["room_type_code"] == ""
        assert c["adults"] == 1


# ── Identity Extraction ──────────────────────────────────────────────

class TestExtractIdentity:
    def test_basic(self):
        raw = {"hr_number": "HR-ID-1", "event_type": "reservation_create", "updated_at": "2026-01-01T00:00:00Z"}
        identity = extract_identity(raw)
        assert identity["external_reservation_id"] == "HR-ID-1"
        assert "HR-ID-1" in identity["provider_event_id"]

    def test_missing_fields(self):
        identity = extract_identity({})
        assert identity["external_reservation_id"] == ""


# ── Idempotency Key ──────────────────────────────────────────────────

class TestIdempotencyKey:
    def test_deterministic(self):
        k1 = compute_idempotency_key("HR-123", "2026-01-01")
        k2 = compute_idempotency_key("HR-123", "2026-01-01")
        assert k1 == k2

    def test_different_for_different_inputs(self):
        k1 = compute_idempotency_key("HR-123", "2026-01-01")
        k2 = compute_idempotency_key("HR-123", "2026-01-02")
        assert k1 != k2


# ── Payload Hash ─────────────────────────────────────────────────────

class TestPayloadHash:
    def test_same_data_same_hash(self):
        c = {"check_in": "2026-04-10", "check_out": "2026-04-15", "total_amount": 5000.0, "status": "confirmed"}
        h1 = compute_payload_hash(c)
        h2 = compute_payload_hash(c)
        assert h1 == h2

    def test_different_amount_different_hash(self):
        c1 = {"check_in": "2026-04-10", "total_amount": 5000.0, "status": "confirmed"}
        c2 = {"check_in": "2026-04-10", "total_amount": 5001.0, "status": "confirmed"}
        assert compute_payload_hash(c1) != compute_payload_hash(c2)


# ── Event Type Detection ─────────────────────────────────────────────

class TestDetectEventType:
    def test_new(self):
        assert detect_event_type({"status": "confirmed"}) == "new"

    def test_modification(self):
        assert detect_event_type({"status": "modified"}) == "modification"

    def test_cancellation(self):
        assert detect_event_type({"status": "cancelled"}) == "cancellation"


# ── ARI Outbound Mapping ─────────────────────────────────────────────

class TestARIMapping:
    def test_daterange_full(self):
        p = ari_to_daterange_payload(
            "STD", "2026-04-10", "2026-04-15",
            availability=5, price=100.0, stop_sale=False, min_stay=2, cta=True,
        )
        assert p["inv_code"] == "STD"
        assert p["availability"] == "5"
        assert p["price"] == "100.0"
        assert p["stop_sale"] == "0"
        assert p["min_stay"] == "2"
        assert p["cta"] == "1"

    def test_daily_minimal(self):
        p = ari_to_daily_payload("DLX", "2026-04-10", availability=3)
        assert p["inv_code"] == "DLX"
        assert p["date"] == "2026-04-10"
        assert p["availability"] == "3"
        assert "price" not in p

    def test_stop_sale(self):
        p = ari_to_daterange_payload("STD", "2026-04-10", "2026-04-10", stop_sale=True)
        assert p["stop_sale"] == "1"
