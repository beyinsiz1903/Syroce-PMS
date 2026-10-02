from routers.finance.mobile import _is_reportable_collection, _received_collection_amount


def test_mobile_finance_excludes_voided_and_discount_payments_from_collections():
    assert not _is_reportable_collection({"amount": 100, "voided": True})
    assert not _is_reportable_collection({"amount": 100, "method": "discount"})
    assert not _is_reportable_collection({"amount": 100, "payment_method": "discount"})
    assert _is_reportable_collection({"amount": 100, "method": "card", "status": "paid"})


def test_mobile_finance_marks_refunds_negative_in_received_currency():
    assert _received_collection_amount(
        {
            "amount": 2500,
            "currency": "TRY",
            "received_amount": 75,
            "received_currency": "EUR",
            "payment_type": "refund",
        }
    ) == (-75.0, "EUR")
