from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from routers import reservation_detail as detail
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


@pytest.mark.parametrize('rate,quantity,total,net,vat', [(20, 1, 150, 125, 25), (20, 2, 300, 250, 50), (0, 1, 150, 150, 0), (20, .333, 49.95, 41.63, 8.32), (None, 1, 150, None, None)])
async def test_entered_gross_stays_fixed_with_explicit_vat_evidence(ledger_db, monkeypatch, rate, quantity, total, net, vat):  # noqa: F811
    await ledger_db.bookings.insert_one({'id': 'b', 'tenant_id': 't', 'currency': 'TRY'})
    monkeypatch.setattr(detail, 'db', ledger_db)
    monkeypatch.setattr(detail, '_enforce_perm', lambda *_: None)
    monkeypatch.setattr(detail, '_ensure_hotel_context', lambda *_: None)
    monkeypatch.setattr(detail, 'ensure_reservation_mutable', AsyncMock())
    monkeypatch.setattr(detail, '_log_activity', AsyncMock())
    async def stamp(db, tenant, row):
        row['business_date'] = '2026-11-12'
    monkeypatch.setattr(detail, 'stamp_open_business_date', stamp)
    from routers import webhook_retry_service
    monkeypatch.setattr(webhook_retry_service, 'schedule_emit_reservation_updated', lambda *_: None)
    result = await detail.add_extra_charge_detail('b', detail.ExtraChargeAdd(description='Minibar', amount=150, quantity=quantity, vat_rate=rate),
        current_user=SimpleNamespace(id='manager', name='Operator', role='admin', tenant_id='t'), _perm=None)
    row = await ledger_db.extra_charges.find_one({'id': result['charge']['id']})
    assert (row['total'], row['net_amount'], row['vat_amount'], row['tax_amount']) == (total, net, vat, 0 if rate is not None else None)
    assert row['tax_evidence_status'] == ('verified' if rate is not None else 'missing')
    if rate is not None:
        assert row['tax_inclusive']
    assert row['entered_amount'] == 150 and row['entered_total'] == total
    assert await ledger_db.extra_charges.count_documents({}) == 1
    from modules.folio.proforma import proforma_amounts
    snapshot = {'currency': 'TRY', 'charges': [row], 'payments': [], 'payments_by_currency': {}, 'opening_by_currency': {}}
    _, _, totals = proforma_amounts(snapshot)
    assert totals['grand_total'] == totals['balance_due'] == total
    assert totals['net_total'] == net and totals['vat_total'] == vat
    if rate is not None:
        from core.integrations.operational_gl_valuation import source_tax_components
        assert source_tax_components(row) == (round(vat * 100), 0)



@pytest.mark.parametrize('rate', [-1, 101, float('nan'), float('inf')])
def test_invalid_rate_never_reaches_posting(rate):
    with pytest.raises(ValidationError):
        detail.ExtraChargeAdd(description='Minibar', amount=150, vat_rate=rate)
