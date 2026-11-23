import pytest
from fastapi import HTTPException

from core.laundry_tax import laundry_delivery_tax, laundry_tax_snapshot, laundry_vat_rate


def test_inclusive_price_never_adds_vat_and_fx_preserves_total():
    lines = [{'total': 150, 'vat_rate': 20}]
    snapshot = laundry_tax_snapshot(lines, 'TRY')
    assert (snapshot['gross'], snapshot['net'], snapshot['vat']) == (150, 125, 25)
    evidence = laundry_delivery_tax({'items': lines, 'tax_snapshot': snapshot},
        {'entered_currency': 'TRY', 'entered_total': 150, 'exchange_rate': .025, 'folio_total': 3.75})
    assert (evidence['net_amount'], evidence['vat_amount'], evidence['tax_amount']) == (3.12, .63, 0)
    assert round(evidence['net_amount'] + evidence['vat_amount'], 2) == 3.75


@pytest.mark.parametrize('rate', [None, 0, 20])
def test_unknown_is_distinct_from_explicit_zero(rate):
    snapshot = laundry_tax_snapshot([{'total': 25, 'vat_rate': rate}], 'TRY')
    assert snapshot['status'] == ('missing' if rate is None else 'verified')
    assert snapshot['vat'] == (None if rate is None else 0 if rate == 0 else 4.17)


@pytest.mark.parametrize('rate', [True, -1, 101, 'nan', 'Infinity', '20.001'])
def test_invalid_rate_is_rejected(rate):
    with pytest.raises(HTTPException): laundry_vat_rate(rate)


def test_snapshot_tampering_is_not_repriced_at_delivery():
    lines = [{'total': 150, 'vat_rate': 20}]
    snapshot = laundry_tax_snapshot(lines, 'TRY')
    with pytest.raises(HTTPException) as error:
        laundry_delivery_tax({'items': [{'total': 150, 'vat_rate': 10}], 'tax_snapshot': snapshot},
            {'entered_currency': 'TRY', 'entered_total': 150, 'exchange_rate': 1, 'folio_total': 150})
    assert error.value.status_code == 409


def test_legacy_missing_snapshot_stays_unknown():
    assert laundry_delivery_tax({'total': 25}, {})['tax_amount'] is None


@pytest.mark.parametrize('legacy_city', [0, 25])
def test_verified_laundry_is_one_vat_component_across_reports(legacy_city):
    from modules.folio.proforma import proforma_amounts
    from modules.pms_core.revenue_report import charge_breakdown
    row = {'id': 'laundry', 'charge_category': 'laundry', 'currency': 'TRY',
        'amount': 150, 'total': 150, 'net_amount': 125, 'vat_amount': 25,
        'tax_amount': legacy_city, 'tax_inclusive': True,
        'tax_snapshot': {'status': 'verified'}, 'report_source': 'folio'}
    original = dict(row)
    detail = charge_breakdown(row)
    assert (detail['net'], detail['vat'], detail['city_tax'], detail['difference']) == (125, 25, 0, 0)
    _, _, totals = proforma_amounts({'currency': 'TRY', 'charges': [row], 'payments': [],
        'payments_by_currency': {}, 'opening_by_currency': {}})
    assert (totals['net_total'], totals['vat_total'], totals['city_tax_total'], totals['grand_total']) == (125, 25, 0, 150)
    assert row == original
