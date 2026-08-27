from core.channel_room_charge_pricing import (
    analyze_legacy_double_tax_charge,
    calculate_room_charge,
    is_channel_total_tax_inclusive,
)


def _hotelrunner_booking(**overrides):
    booking = {
        "id": "booking-1",
        "booking_source": "ota_import",
        "source": {"provider": "hotelrunner", "external_reservation_id": "R901318024"},
        "check_in": "2026-08-22",
        "check_out": "2026-08-23",
        "total_amount": 4750.0,
    }
    booking.update(overrides)
    return booking


def test_hotelrunner_total_is_recognized_as_tax_inclusive():
    assert is_channel_total_tax_inclusive(_hotelrunner_booking()) is True
    assert is_channel_total_tax_inclusive({"channel": "agency", "total_amount": 4750}) is False


def test_inclusive_channel_total_is_not_taxed_twice():
    charge = calculate_room_charge(_hotelrunner_booking(), "2026-08-22")

    assert charge["amount"] == 4241.07
    assert charge["tax_amount"] == 508.93
    assert charge["total"] == 4750.0
    assert charge["tax_breakdown"] == {"vat": 424.11, "accommodation_tax": 84.82}
    assert charge["tax_inclusive"] is True


def test_multi_night_allocation_preserves_provider_total_to_the_cent():
    booking = _hotelrunner_booking(
        check_out="2026-08-25",
        total_amount=100.0,
    )

    totals = [
        calculate_room_charge(booking, "2026-08-22")["total"],
        calculate_room_charge(booking, "2026-08-23")["total"],
        calculate_room_charge(booking, "2026-08-24")["total"],
    ]

    assert totals == [33.34, 33.33, 33.33]
    assert round(sum(totals), 2) == 100.0


def test_direct_booking_keeps_net_rate_behavior():
    charge = calculate_room_charge(
        {
            "source": "direct",
            "room_rate": 1000.0,
            "check_in": "2026-08-22",
            "check_out": "2026-08-23",
            "total_amount": 1000.0,
        },
        "2026-08-22",
    )

    assert charge["amount"] == 1000.0
    assert charge["tax_amount"] == 120.0
    assert charge["total"] == 1120.0
    assert charge["tax_inclusive"] is False


def test_exact_5320_legacy_signature_is_repairable():
    issue = analyze_legacy_double_tax_charge(
        _hotelrunner_booking(),
        {
            "id": "charge-1",
            "folio_id": "folio-1",
            "charge_category": "room",
            "charge_type": "room_charge",
            "posted_by": "night_audit",
            "business_date": "2026-08-22",
            "amount": 4750.0,
            "tax_amount": 570.0,
            "total": 5320.0,
            "voided": False,
        },
    )

    assert issue is not None
    assert issue["observed_total"] == 5320.0
    assert issue["expected_total"] == 4750.0
    assert issue["overcharge"] == 570.0
    assert issue["corrected"]["amount"] == 4241.07


def test_unrelated_room_charge_is_not_auto_repairable():
    issue = analyze_legacy_double_tax_charge(
        _hotelrunner_booking(),
        {
            "id": "charge-1",
            "charge_category": "room",
            "charge_type": "room_charge",
            "posted_by": "night_audit",
            "business_date": "2026-08-22",
            "amount": 4700.0,
            "total": 5000.0,
            "voided": False,
        },
    )

    assert issue is None
