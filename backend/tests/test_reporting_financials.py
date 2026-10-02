from modules.pms_core.reporting_financials import effective_collection, effective_revenue_adjustment


def test_rate_correction_reduces_revenue_but_is_not_a_collection():
    payment = {"amount": 2500, "method": "discount", "payment_type": "rate_correction", "status": "paid"}
    assert effective_collection(payment) == 0
    assert effective_revenue_adjustment(payment) == 2500


def test_real_payment_and_refund_remain_cash_movements():
    assert effective_collection({"amount": 1000, "method": "card", "status": "paid"}) == 1000
    assert effective_collection({"amount": 1000, "method": "card", "payment_type": "refund", "status": "paid"}) == -1000
