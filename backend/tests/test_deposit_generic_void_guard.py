"""A source-owned deposit must only be reversed through its deposit ledger."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.misc import payments_folio
from modules.pms_core import folio_detail_service, folio_hardening_service
from routers.finance import folio

pytest_plugins = ('tests.test_report_ledger_mongo_acceptance',)


@pytest.mark.parametrize('owner', [{'deposit_id': 'deposit'}, {'payment_type': 'deposit'}])
@pytest.mark.parametrize('route', ['finance', 'legacy', 'hardening'])
async def test_source_owned_deposit_cannot_be_generically_voided(ledger_db, monkeypatch, owner, route):
    original = {'id': 'p', 'tenant_id': 't', 'folio_id': 'f', 'amount': 100, 'currency': 'TRY', 'method': 'cash', **owner}
    await ledger_db.payments.insert_one(dict(original))
    await ledger_db.folios.insert_one({'id': 'f', 'tenant_id': 't', 'balance': 0, 'status': 'open', 'currency': 'TRY'})
    await ledger_db.payments.insert_many([
        {'id': 'r1', 'tenant_id': 't', 'folio_id': 'f', 'amount': 40, 'payment_type': 'refund', 'deposit_id': 'deposit'},
        {'id': 'r2', 'tenant_id': 't', 'folio_id': 'f', 'amount': 60, 'payment_type': 'refund', 'deposit_id': 'deposit'},
    ])
    user = SimpleNamespace(tenant_id='t', id='u', name='Operator', role='admin')
    module = {'finance': folio, 'legacy': payments_folio, 'hardening': folio_hardening_service}[route]
    monkeypatch.setattr(module, 'db', ledger_db)
    if route == 'hardening':
        result = await module.FolioHardeningService().void_payment('t', 'p', 'negative test', 'u')
        assert result['success'] is False and 'Depozito' in result['error']
    else:
        with pytest.raises(HTTPException) as error:
            if route == 'finance':
                await module.void_payment('f', 'p', {'reason': 'negative test'}, user)
            else:
                await module.void_payment('p', 'negative test', user)
        assert error.value.status_code == 409 and 'Depozito' in error.value.detail
    assert not (await ledger_db.payments.find_one({'id': 'p'})).get('voided')
    assert await ledger_db.payments.count_documents({}) == 3
    assert (await ledger_db.folios.find_one({'id': 'f'}))['balance'] == 0


async def test_timeline_does_not_offer_generic_deposit_refund(ledger_db, monkeypatch):
    monkeypatch.setattr(folio_detail_service, 'db', ledger_db)
    await ledger_db.folios.insert_one({'id': 'f', 'tenant_id': 't', 'currency': 'TRY', 'status': 'open'})
    await ledger_db.payments.insert_one({'id': 'p', 'tenant_id': 't', 'folio_id': 'f', 'amount': 100,
        'currency': 'TRY', 'method': 'cash', 'payment_type': 'deposit', 'deposit_id': 'd'})
    result = await folio_detail_service.FolioDetailService().get_folio_detail('t', 'f')
    assert result['success'] is True
    event = next(e for e in result['timeline'] if e['id'] == 'p')
    assert event['can_void'] is False
