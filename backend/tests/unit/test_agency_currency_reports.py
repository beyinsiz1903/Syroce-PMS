from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import marketplace_b2b as market


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['agency', 'hotel'])
async def test_reconciliation_never_adds_try_and_eur(monkeypatch, kind):
    rows = [{'tenant_id': 't', 'agency_id': 'a', 'currency': currency, 'total_amount': amount,
             'commission_amount': amount / 10, 'syroce_b2b_fee_amount': amount / 100}
            for currency, amount in [('TRY', 1000), ('EUR', 100), (None, 50)]]
    rows.append({'currency': 'EUR', 'status': 'cancelled', 'total_amount': 9999})
    collection = SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=rows)))
    monkeypatch.setattr(market, 'get_system_db', lambda: SimpleNamespace(marketplace_bookings=collection))
    monkeypatch.setattr(market, '_require_hotel_admin', lambda user: 't')
    if kind == 'agency':
        result = await market.agency_reconciliation('2026-01-01', '2026-12-31', {'agency_id': 'a'})
    else:
        result = await market.hotel_reconciliation('2026-01-01', '2026-12-31', None)
    assert result['totals']['gross_revenue'] is None
    assert result['totals']['bookings'] == 3 and result['totals']['cancelled'] == 1
    totals = {r['currency']: r for r in result['totals_by_currency']}
    assert totals['TRY']['gross_revenue'] == 1000
    assert totals['EUR']['gross_revenue'] == 100
    assert totals['UNKNOWN']['gross_revenue'] == 50
    breakdown = result['by_hotel' if kind == 'agency' else 'by_agency']
    assert len(breakdown) == 3


def test_empty_and_single_currency_summary():
    from core.agency_reporting import combined_summary
    assert combined_summary({})['gross_revenue'] is None
    assert combined_summary({'EUR': {'currency': 'EUR', 'gross_revenue': 100}})['gross_revenue'] == 100
