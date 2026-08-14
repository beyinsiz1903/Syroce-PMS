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
