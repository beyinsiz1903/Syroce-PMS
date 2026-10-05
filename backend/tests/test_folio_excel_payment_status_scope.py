from routers.finance.folio import _folio_export_transactions


def test_folio_export_includes_only_financially_effective_payments():
    transactions = _folio_export_transactions(
        [{"business_date": "2026-10-02", "description": "Konaklama", "amount": 1000}],
        [
            {"payment_date": "2026-10-02", "amount": 250, "status": "paid"},
            {"payment_date": "2026-10-02", "amount": 250, "status": "failed"},
            {"payment_date": "2026-10-02", "amount": 250, "status": "cancelled"},
            {"payment_date": "2026-10-02", "amount": 250, "status": "rejected"},
            {"payment_date": "2026-10-02", "amount": 250, "voided": True},
        ],
    )

    assert [(transaction["is_charge"], transaction["amount"]) for transaction in transactions] == [
        (True, 1000.0),
        (False, 250.0),
    ]


def test_folio_export_keeps_legacy_payment_without_status():
    transactions = _folio_export_transactions([], [{"amount": 375, "created_at": "2026-10-02T10:30:00"}])

    assert transactions == [
        {
            "date": "2026-10-02",
            "desc": "Payment",
            "type": "Payment",
            "amount": 375.0,
            "is_charge": False,
        }
    ]
