from domains.pms.frontdesk_financials import calculate_departure_balance


def test_departure_balance_includes_active_extra_charges_and_paid_payments():
    balance = calculate_departure_balance(
        charges=[{"total": "100"}, {"total": 999, "voided": True}],
        payments=[
            {"amount": "40", "status": "paid"},
            {"amount": 20, "status": "pending"},
        ],
        extra_charges=[
            {"charge_amount": "50"},
            {"charge_amount": 999, "voided": True},
        ],
    )

    assert balance == 110.0


def test_departure_balance_tolerates_malformed_legacy_amounts():
    assert (
        calculate_departure_balance(
            charges=[{"total": None}],
            payments=[{"amount": "not-a-number", "status": "paid"}],
            extra_charges=[{"amount": float("nan")}],
        )
        == 0.0
    )


def test_departure_balance_includes_unposted_booking_total():
    balance = calculate_departure_balance(
        charges=[{"total": "50", "charge_category": "minibar"}],
        payments=[{"amount": "40", "status": "paid"}],
        extra_charges=[{"charge_amount": "25"}],
        booking_total="100",
    )

    assert balance == 135.0


def test_departure_balance_does_not_double_count_posted_room_revenue():
    balance = calculate_departure_balance(
        charges=[{"total": "100", "charge_type": "room_charge"}],
        payments=[{"amount": "100", "status": "paid"}],
        extra_charges=[],
        booking_total="100",
    )

    assert balance == 0.0


def test_departure_balance_includes_the_unposted_portion_of_a_partly_posted_stay():
    balance = calculate_departure_balance(
        charges=[{"total": 5833.34, "charge_type": "room_charge"}],
        payments=[{"amount": 5833.34, "status": "paid"}],
        extra_charges=[],
        booking_total=7500.0,
    )

    assert balance == 1666.66


def test_departure_balance_preserves_explicit_zero_after_extra_charge_split():
    balance = calculate_departure_balance(
        charges=[],
        payments=[],
        extra_charges=[{"total": 0, "charge_amount": 50}],
    )

    assert balance == 0.0
