"""Merge preserves original ledger rows and source accounting history."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from modules.pms_core.folio_merge import FolioMergeRequest, merge_folio_windows
from modules.pms_core.receivable_reporting import folio_snapshots
from tests.unit.test_folio_allocation import Collection, matches


class MergeCollection(Collection):
    async def update_many(self, query, update, *, session):
        assert session is not None
        if self.fail_write:
            raise RuntimeError("injected write failure")
        count = 0
        for row in self.rows:
            if matches(row, query):
                row.update(update['$set'])
                count += 1
        return SimpleNamespace(modified_count=count)


class Database(SimpleNamespace):
    def __getitem__(self, key):
        return getattr(self, key)


@pytest.fixture
def ledger():
    base = {'tenant_id': 'hotel-a', 'booking_id': 'booking', 'status': 'open', 'currency': 'TRY'}
    row = {'tenant_id': 'hotel-a', 'booking_id': 'booking', 'folio_id': 'source', 'currency': 'TRY'}
    return Database(
        folios=MergeCollection([{**base, 'id': 'source', 'opening_balance': 100, 'balance': 123456},
                               {**base, 'id': 'target', 'payor_type': 'company', 'cari_account_id': 'ar-1', 'opening_balance': 50}]),
        bookings=MergeCollection([{'id': 'booking', 'tenant_id': 'hotel-a', 'currency': 'TRY', 'status': 'checked_in'}]),
        tenant_settings=MergeCollection([{'tenant_id': 'hotel-a', 'business_date': '2026-11-10'}]),
        folio_charges=MergeCollection([
            {**row, 'id': 'room', 'total': 110, 'amount': 100, 'tax_amount': 10, 'charge_category': 'room', 'business_date': '2026-11-09'},
            {**row, 'id': 'food', 'total': 55, 'amount': 50, 'tax_amount': 5, 'charge_category': 'food', 'business_date': '2026-11-10'},
            {**row, 'id': 'voided', 'total': 999, 'voided': True},
            {**row, 'id': 'mirror', 'source_extra_charge_id': 'extra', 'total': 20}]),
        payments=MergeCollection([
            {**row, 'id': 'cash', 'amount': 40, 'method': 'cash', 'payment_type': 'collection', 'status': 'completed'},
            {**row, 'id': 'comp', 'amount': 55, 'payment_type': 'concession', 'method': 'concession', 'status': 'completed', 'concession_id': 'comp-1'},
            {**row, 'id': 'refund', 'amount': -10, 'method': 'cash', 'payment_type': 'refund', 'status': 'refunded', 'original_payment_id': 'cash'}]),
        extra_charges=MergeCollection([{**row, 'id': 'extra', 'total': 20}]),
        deposits=MergeCollection([{**row, 'id': 'security-1', 'amount': 500, 'status': 'held'}]),
        folio_postings=MergeCollection([{**row, 'id': 'posting-1', 'charge_id': 'room', 'amount': 110}]),
        billing_concessions=MergeCollection([{**row, 'id': 'comp-1', 'charge_ids': ['food'], 'status': 'applied'}]),
        invoices=MergeCollection(), folio_operations=MergeCollection(), pms_audit_trail=MergeCollection(),
        folio_routing=MergeCollection([{'id': 'rule', 'tenant_id': 'hotel-a', 'source_folio_id': 'source', 'dest_folio_id': 'target', 'active': True}]))


async def request(db, **overrides):
    snaps = await folio_snapshots(db, 'hotel-a', db.folios.rows, fallback_currency='TRY', session=object(), include_booking_extras=True)
    values = dict(request_id=uuid4(), booking_id='booking', source_folio_id='source', target_folio_id='target',
                  expected_source_balance=snaps['source']['balance_by_currency']['TRY'], expected_target_balance=50, reason='Hesapları birleştir')
    return FolioMergeRequest(**(values | overrides))


async def merge(db, body, tenant='hotel-a'):
    return await merge_folio_windows(db, tenant, 'operator', body, session=object())


@pytest.mark.asyncio
async def test_moves_originals_preserves_tax_comp_refund_deposit_and_replays(ledger):
    original = deepcopy(vars(ledger))
    body = await request(ledger)
    result = await merge(ledger, body)
    assert result['target_balance'] == float(body.expected_source_balance) + 50
    for name in ('folio_charges', 'payments', 'extra_charges', 'folio_postings', 'deposits'):
        assert ledger[name].rows == [{**row, 'folio_id': 'target'} for row in original[name].rows]
    assert ledger.billing_concessions.rows == original['billing_concessions'].rows
    assert ledger.folios.rows[0]['status'] == 'closed' and ledger.folios.rows[0]['balance'] == 0
    assert ledger.folios.rows[1]['opening_balance'] == 150
    assert ledger.folios.rows[1]['cari_account_id'] == 'ar-1'
    assert not ledger.folio_routing.rows[0]['active']
    assert len(ledger.pms_audit_trail.rows) == 1
    after = deepcopy(vars(ledger))
    assert (await merge(ledger, body))['replayed']
    assert {k: v.rows for k, v in vars(ledger).items()} == {k: v.rows for k, v in after.items()}


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['tenant', 'different_booking', 'closed', 'stale', 'currency', 'invoice', 'pending_comp', 'business_day', 'mixed_zero', 'settlement', 'posted_payment'])
async def test_invalid_merge_leaves_every_collection_untouched(ledger, case):
    body = await request(ledger)
    tenant = 'hotel-a'
    if case == 'tenant': tenant = 'hotel-b'
    if case == 'different_booking': ledger.folios.rows[1]['booking_id'] = 'other-booking'
    if case == 'closed': ledger.folios.rows[1]['status'] = 'closed'
    if case == 'stale': body.expected_source_balance += 1
    if case == 'currency': ledger.folios.rows[1]['currency'] = 'USD'
    if case == 'invoice': ledger.invoices.rows.append({'tenant_id': tenant, 'booking_id': 'booking', 'status': 'issued'})
    if case == 'pending_comp': ledger.billing_concessions.rows[0]['status'] = 'requested'
    if case == 'business_day': ledger.tenant_settings.rows[0]['business_date'] = None
    if case == 'settlement': ledger.payments.rows[0]['billing_settlement_id'] = 'sealed-operation'
    if case == 'posted_payment': ledger.payments.rows[0]['gl_journal_entry_id'] = 'sealed-journal'
    if case == 'mixed_zero':
        ledger.folio_charges.rows.extend([{'id': f'fx-{n}', 'tenant_id': tenant, 'folio_id': 'source', 'currency': 'USD', 'total': n} for n in (10, -10)])
    before = {k: deepcopy(v.rows) for k, v in vars(ledger).items()}
    with pytest.raises(HTTPException):
        await merge(ledger, body, tenant)
    assert {k: v.rows for k, v in vars(ledger).items()} == before


@pytest.mark.asyncio
async def test_settlement_in_target_retains_its_folio_and_evidence(ledger):
    payment = {**ledger.payments.rows[0], 'id': 'instrument-1', 'folio_id': 'target',
               'billing_settlement_id': 'sealed-operation', 'gl_journal_entry_id': 'sealed-journal'}
    ledger.payments.rows.append(payment)
    result = await merge(ledger, await request(ledger, expected_target_balance=10))
    assert result['success']
    assert next(row for row in ledger.payments.rows if row['id'] == 'instrument-1') == payment


@pytest.mark.asyncio
async def test_same_key_cannot_change_target_or_reason(ledger):
    body = await request(ledger)
    await merge(ledger, body)
    body.reason = 'Başka işlem'
    with pytest.raises(HTTPException) as error:
        await merge(ledger, body)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_no_transaction_no_write(ledger):
    with pytest.raises(HTTPException) as error:
        await merge_folio_windows(ledger, 'hotel-a', 'operator', await request(ledger), session=None)
    assert error.value.status_code == 503
    assert not ledger.folio_operations.rows


@pytest.mark.asyncio
async def test_router_uses_shared_booking_and_both_folio_locks(ledger, monkeypatch):
    from domains.pms import folio_window_router as api
    import core.booking_atomicity as atomicity
    import core.report_cache as cache
    body = await request(ledger)
    monkeypatch.setattr(api, 'db', ledger)
    invalidations = []
    monkeypatch.setattr(cache, 'invalidate_financial_report_caches', invalidations.append)
    async def transaction(**kwargs):
        assert kwargs['locks_collection'] == 'reservation_financial_locks'
        assert set(kwargs['resources']) == {('booking', 'booking'), ('folio', 'source'), ('folio', 'target')}
        return await kwargs['callback'](object())
    monkeypatch.setattr(atomicity, 'with_resource_locks', transaction)
    result = await api.merge_windows(body, SimpleNamespace(tenant_id='hotel-a', id='operator'), None)
    assert result['success'] and invalidations == ['hotel-a']
