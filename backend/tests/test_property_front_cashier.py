from modules.pms_core.property_front_cashier import property_front_cashier
from modules.pms_core.property_reporting_currency import HistoricalRates

DAY = '2026-11-12'

def rates():
    return HistoricalRates('TRY', [{'effective_date': DAY, 'from_currency': 'USD', 'to_currency': 'TRY', 'rate': 50}])

def source(amount, currency='TRY', **kwargs):
    return {'amount': amount, 'currency': currency, 'business_date': DAY, **kwargs}

def test_selected_day_cashier_converts_signed_flows_and_keeps_offsets_out_of_cash():
    result = property_front_cashier([source(100), source(10, 'USD')], [
        source(2, 'USD', id='paid', payment_method='cash'),
        source(1, 'USD', id='refund', payment_method='cash', payment_type='refund'),
        source(20, id='discount', payment_method='discount')], rates())
    s = result['front_cashier']
    assert s['charge_total_by_currency'] == {'TRY': 600}
    assert s['collection_total'] == s['cash_total'] == 50
    assert s['daily_balance_change'] == 530
    assert s['uncollected_charges'] == 530
    assert result['payments']['total_paid'] == 50

def test_missing_currency_proof_is_not_a_partial_total_or_zero():
    s = property_front_cashier([source(100), source(10, 'EUR')], [], rates())['front_cashier']
    assert s['charge_total'] is None and s['daily_balance_change'] is None
    assert s['uncollected_charges'] is None and s['currency_policy']['missing_rate_count'] == 1

def test_duplicate_payment_id_and_recorded_posting_value():
    p = source(2, 'USD', id='one', payment_method='card', reporting_currency='TRY', reporting_amount=90)
    result = property_front_cashier([], [p, dict(p)], rates())
    assert result['payments']['total_paid'] == 90
    assert result['front_cashier']['non_cash_total'] == 90
    assert result['front_cashier']['daily_balance_change'] == -90
    assert result['front_cashier']['uncollected_charges'] == 0

def test_empty_eur_property_does_not_default_to_try():
    r = property_front_cashier([], [], HistoricalRates('EUR'))
    assert r['front_cashier']['charge_total_by_currency'] == {'EUR': 0}
    assert r['payments']['reporting_currency'] == 'EUR'
