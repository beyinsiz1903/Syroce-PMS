from domains.pms.cashier_service import summarize_shift_transactions


def test_shift_summary_keeps_all_payment_methods_and_refunds_separate():
    summary = summarize_shift_transactions(
        [
            {"method": "card", "direction": "in", "amount": "12262.50"},
            {"method": "bank_transfer", "direction": "in", "amount": 2000},
            {"method": "bank_transfer", "direction": "in", "amount": 1000},
            {"method": "cash", "direction": "in", "amount": 200},
            {"method": "card", "direction": "out", "amount": 262.5},
        ]
    )

    assert summary["transaction_count"] == 5
    assert summary["total_in"] == 15462.5
    assert summary["total_out"] == 262.5
    assert summary["methods"]["card"] == {
        "count": 2,
        "in": 12262.5,
        "out": 262.5,
        "net": 12000.0,
    }
    assert summary["methods"]["bank_transfer"]["net"] == 3000.0


def test_shift_summary_ignores_invalid_rows_without_breaking_totals():
    summary = summarize_shift_transactions(
        [
            {"method": "card", "direction": "sideways", "amount": 100},
            {"method": "cash", "direction": "in", "amount": "invalid"},
            {"method": "voucher", "direction": "in", "amount": 25},
        ]
    )

    assert summary["transaction_count"] == 1
    assert summary["methods"]["other"]["net"] == 25.0
