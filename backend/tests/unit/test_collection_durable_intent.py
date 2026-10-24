from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.payments import collection
from core.payments.contracts import PaymentOperation, PaymentResult, PaymentStatus


class Intents:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        return next((dict(row) for row in self.rows if row['tenant_id'] == query['tenant_id'] and row['booking_id'] == query['booking_id']
                     and row['idempotency_key'] == query['idempotency_key'] and row['status'] != 'failed'), None)

    async def insert_one(self, document):
        self.rows.append(dict(document))

    async def update_one(self, query, update):
        for row in self.rows:
            if row['id'] == query['id'] and row['tenant_id'] == query['tenant_id']:
                row.update(update['$set'])


@pytest.fixture
def setup(monkeypatch):
    db = SimpleNamespace(payment_intents=Intents())
    provider = SimpleNamespace(name='fake-test-provider', charge=AsyncMock())
    claim = AsyncMock(return_value={'status': 'claimed', 'lock_id': 'lock'})
    release = AsyncMock()
    monkeypatch.setattr(collection, 'claim_idempotency', claim)
    monkeypatch.setattr(collection, 'release_idempotency', release)
    return db, provider, claim, release


async def collect(setup, **changes):
    db, provider, *_ = setup
    return await collection.collect_booking_payment(db, **{'tenant_id': 'A', 'booking_id': 'booking', 'folio': {'id': 'guest'},
        'amount_minor': 10000, 'currency': 'TRY', 'vault_ref': 'vault_v1:test-card', 'idempotency_key': 'request',
        'scope': 'manual', 'payment_type': 'interim', 'processed_by': 'operator', 'provider': provider, **changes})


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION])
async def test_pending_and_3ds_do_not_call_provider_twice(setup, status):
    db, provider, claim, release = setup
    provider.charge.return_value = PaymentResult(status=status, operation=PaymentOperation.CHARGE, provider=provider.name,
        tenant_id='A', idempotency_key='request', requires_action_url='https://payment.example.test/3ds')
    first = await collect(setup)
    second = await collect(setup)
    assert first.status == second.status == ('requires_action' if status == PaymentStatus.REQUIRES_ACTION else 'in_flight')
    assert provider.charge.await_count == claim.await_count == 1
    release.assert_not_awaited()
    assert len(db.payment_intents.rows) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'folio': {'id': 'company'}}, {'amount_minor': 10001}, {'currency': 'EUR'}, {'vault_ref': 'vault_v1:other'}])
async def test_same_key_different_payload_is_rejected_before_provider(setup, changes):
    setup[1].charge.return_value = PaymentResult(status=PaymentStatus.PENDING, operation=PaymentOperation.CHARGE,
        provider='fake', tenant_id='A', idempotency_key='request')
    await collect(setup)
    result = await collect(setup, **changes)
    assert result.status == 'failed' and result.http_status == 409
    assert setup[1].charge.await_count == 1


@pytest.mark.asyncio
async def test_completed_intent_replays_even_after_cache_is_gone(setup):
    setup[0].payment_intents.rows.append({'id': 'intent', 'tenant_id': 'A', 'booking_id': 'booking', 'idempotency_key': 'request',
        'status': 'completed', 'folio_id': 'guest', 'amount_minor': 10000, 'currency': 'TRY', 'result': {'id': 'payment', 'status': 'paid'}})
    result = await collect(setup)
    assert result.status == 'replay' and result.response['id'] == 'payment'
    setup[1].charge.assert_not_awaited()
    setup[2].assert_not_awaited()


@pytest.mark.asyncio
async def test_unrecorded_collection_replays_warning_without_another_charge(setup):
    result = {'status': 'paid_unrecorded', 'ledger_recorded': False, 'warning': 'Reconciliation required'}
    setup[0].payment_intents.rows.append({'id': 'intent', 'tenant_id': 'A', 'booking_id': 'booking', 'idempotency_key': 'request',
        'status': 'completed_unrecorded', 'folio_id': 'guest', 'amount_minor': 10000, 'currency': 'TRY', 'result': result})
    replay = await collect(setup)
    assert replay.status == 'replay' and replay.response == result
    setup[1].charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_completed_intent_reconstructs_posted_result_without_recharge(setup):
    setup[0].payments = SimpleNamespace(find_one=AsyncMock(return_value={'id': 'payment', 'masked_card': '****0000'}))
    setup[0].payment_intents.rows.append({'id': 'intent', 'tenant_id': 'A', 'booking_id': 'booking', 'idempotency_key': 'request',
        'status': 'completed', 'folio_id': 'guest', 'amount_minor': 10000, 'currency': 'TRY', 'payment_id': 'payment'})
    replay = await collect(setup)
    assert replay.status == 'replay' and replay.response['id'] == 'payment'
    assert replay.response['folio_id'] == 'guest' and replay.response['currency'] == 'TRY'
    setup[0].payments.find_one.assert_awaited_once_with({'tenant_id': 'A', 'id': 'payment', 'voided': {'$ne': True}}, {'_id': 0})
    setup[1].charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_exception_keeps_durable_intent_and_never_recharges(setup):
    setup[1].charge.side_effect = TimeoutError('provider response lost')
    assert (await collect(setup)).status == 'unknown'
    assert (await collect(setup)).status == 'in_flight'
    assert setup[1].charge.await_count == 1
    setup[3].assert_not_awaited()
