"""Real concession arithmetic and state machine against isolated storage."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from modules.pms_core import enterprise_billing as billing
from modules.pms_core.reporting_financials import effective_collection


def matches(row, query):
    for key, value in query.items():
        if key == "$or":
            if not any(matches(row, option) for option in value):
                return False
        elif isinstance(value, dict):
            actual = row.get(key)
            if "$in" in value and not (any(item in value["$in"] for item in actual) if isinstance(actual, list) else actual in value["$in"]):
                return False
            if "$nin" in value and actual in value["$nin"]:
                return False
            if "$ne" in value and actual == value["$ne"]:
                return False
        elif row.get(key) != value:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    async def to_list(self, _):
        return self.rows

    def __aiter__(self):
        async def iterator():
            for row in self.rows:
                yield row
        return iterator()


class Collection:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))
        self.fail = False

    def find(self, query, projection=None, *, session=None):
        return Cursor([row for row in self.rows if matches(row, query)])

    async def find_one(self, query, projection=None, *, session=None):
        return next(iter(await self.find(query, session=session).to_list(None)), None)

    async def insert_one(self, row, *, session):
        assert session is not None
        if self.fail:
            raise RuntimeError("injected transaction failure")
        assert not row.get("_id") or not any(old.get("_id") == row["_id"] for old in self.rows)
        self.rows.append(deepcopy(row))

    async def update_one(self, query, update, *, session):
        assert session is not None
        if self.fail:
            raise RuntimeError("injected transaction failure")
        for row in self.rows:
            if matches(row, query):
                row.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


@pytest.fixture
def ledger(monkeypatch):
    from core import audit_chain

    async def link(tenant_id, entry, session=None):
        assert session is not None
        return 1, "", audit_chain.compute_record_hash(entry, 1, "")

    monkeypatch.setattr(audit_chain, "_link_chain", link)
    return SimpleNamespace(
        bookings=Collection([{"id": "booking", "tenant_id": "A", "currency": "TRY", "status": "checked_in"}]),
        folios=Collection([{"id": "guest", "tenant_id": "A", "booking_id": "booking", "status": "open", "currency": "TRY", "balance": 999999}]),
        tenant_settings=Collection([{"tenant_id": "A", "business_date": "2026-10-24", "enterprise_billing": {"approval_limits_minor": {"TRY": 1000000}}}]),
        folio_charges=Collection([{"id": "room", "tenant_id": "A", "folio_id": "guest", "booking_id": "booking", "currency": "TRY",
            "charge_category": "room", "amount": 900, "tax_amount": 100, "total": 1000, "business_date": "2026-10-23", "voided": False}]),
        payments=Collection(), billing_concessions=Collection(), invoices=Collection(), pms_audit_trail=Collection(), audit_logs=Collection())


def body(**changes):
    return billing.ConcessionRequest(**{"request_id": uuid4(), "booking_id": "booking", "folio_id": "guest", "charge_ids": ["room"],
        "kind": "room_comp", "mode": "full", "reason": "Yönetim misafiri", **changes})


async def request(db, data):
    return await billing.request_concession(db, "A", "requester", data, session=object(), actor_name="Ayşe Yılmaz", actor_role="super_admin")


async def legacy_pending(db, data):
    """An old pre-deployment request, never a new application's durable state."""
    payload = data.model_dump(mode="json")
    payload["charge_ids"] = sorted(payload["charge_ids"])
    basis = await billing.concession_basis(db, 'A', data, session=object())
    db.billing_concessions.rows.append({'_id': f'concession:A:{data.request_id}', 'id': str(data.request_id),
        'tenant_id': 'A', **payload, **basis, 'request_payload': payload, 'fingerprint': billing.fingerprint(payload),
        'requested_by': 'requester', 'status': 'requested'})


async def decide(db, data, approve=True, actor="manager"):
    return await billing.decide_concession(db, "A", actor, data.request_id, approve, session=object())


@pytest.mark.asyncio
async def test_full_room_comp_is_immediate_with_explanation_and_is_not_collection(ledger):
    original = deepcopy(ledger.folio_charges.rows)
    data = body()
    result = await request(ledger, data)
    assert result['status'] == 'applied'
    assert ledger.folio_charges.rows == original  # no rewrite of closed-day revenue or tax
    assert ledger.folios.rows[0]['balance'] == 0
    assert len(ledger.payments.rows) == 1 and effective_collection(ledger.payments.rows[0]) == 0
    assert ledger.payments.rows[0]['business_date'] == '2026-10-24'
    assert ledger.pms_audit_trail.rows[0]['metadata']['requested_by'] == 'requester'
    audit = ledger.audit_logs.rows[0]
    assert audit['entity_type'] == 'reservation' and audit['entity_id'] == 'booking'
    assert audit['actor_id'] == 'requester' and audit['actor_name'] == 'Ayşe Yılmaz'
    assert audit['override_reason'] == data.reason and data.reason in audit['details']
    assert audit['after_snapshot']['allocated_charge_minor'] == {'room': 100000}
    assert audit['after_snapshot']['balance_before_minor'] == 100000
    assert audit['after_snapshot']['balance_after_minor'] == 0
    assert result['execution_mode'] == 'direct_with_reason'
    await decide(ledger, data, actor='requester')
    await request(ledger, data)
    assert len(ledger.payments.rows) == 1  # decision retry never posts twice
    assert len(ledger.audit_logs.rows) == len(ledger.pms_audit_trail.rows) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(('mode', 'fields', 'expected'), [('percentage', {'percentage': '33.33'}, 33330), ('amount', {'amount_minor': 1}, 1)])
async def test_partial_comp_exact_minor_units(ledger, mode, fields, expected):
    data = body(mode=mode, **fields)
    assert (await request(ledger, data))['amount_minor'] == expected
    await decide(ledger, data)
    assert round(ledger.folios.rows[0]['balance'] * 100) == 100000 - expected


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['room_comp', 'selected_services_comp', 'service_recovery', 'discount'])
@pytest.mark.parametrize('code', ['TRY', 'USD', 'EUR', 'GBP', 'CHF'])
@pytest.mark.parametrize('mode,fields,expected', [('full', {}, 100000), ('percentage', {'percentage': '33.33'}, 33330),
    ('amount', {'amount_minor': 12345}, 12345)])
async def test_all_concession_kinds_and_scopes_preserve_native_currency(ledger, kind, code, mode, fields, expected):
    for collection in (ledger.bookings, ledger.folios, ledger.folio_charges):
        collection.rows[0]['currency'] = code
    result = await request(ledger, body(kind=kind, mode=mode, **fields))
    assert result['status'] == 'applied' and result['currency'] == code and result['amount_minor'] == expected
    assert round(ledger.payments.rows[0]['amount'] * 100) == expected
    assert ledger.payments.rows[0]['currency'] == ledger.audit_logs.rows[0]['after_snapshot']['currency'] == code
    assert effective_collection(ledger.payments.rows[0]) == 0


@pytest.mark.asyncio
async def test_request_replay_payload_binding_and_no_reversal(ledger):
    data = body()
    assert await request(ledger, data) == await request(ledger, data)
    with pytest.raises(HTTPException) as exc:
        await request(ledger, data.model_copy(update={'reason': 'başka gerekçe'}))
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException):
        await decide(ledger, data, False)
    assert len(ledger.payments.rows) == 1


@pytest.mark.asyncio
async def test_legacy_pending_can_be_applied_or_cancelled_by_creator(ledger):
    cancelled = body()
    await legacy_pending(ledger, cancelled)
    assert (await decide(ledger, cancelled, False, actor='requester'))['status'] == 'rejected'
    with pytest.raises(HTTPException):
        await request(ledger, cancelled)
    assert not ledger.payments.rows
    data = body()
    await legacy_pending(ledger, data)
    applied = await billing.decide_concession(ledger, 'A', 'requester', data.request_id, True,
        reason='Sunum için oda ikramı', session=object(), actor_name='Ayşe Yılmaz')
    assert applied['status'] == 'applied' and applied['reason'] == 'Sunum için oda ikramı'
    assert applied['original_reason'] == data.reason
    assert ledger.payments.rows[0]['notes'] == 'Sunum için oda ikramı'
    with pytest.raises(HTTPException):
        await billing.decide_concession(ledger, 'A', 'requester', data.request_id, True,
            reason='Farklı açıklama', session=object())


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['charge', 'payment', 'invoice', 'folio_closed', 'other_comp'])
async def test_legacy_application_rechecks_service_and_fiscal_state(ledger, change):
    data = body(mode='percentage', percentage=50)
    await legacy_pending(ledger, data)
    if change == 'charge':
        ledger.folio_charges.rows[0]['total'] = 900
    elif change == 'payment':
        ledger.payments.rows.append({'tenant_id': 'A', 'folio_id': 'guest', 'currency': 'TRY', 'amount': 600, 'method': 'card'})
    elif change == 'invoice':
        ledger.invoices.rows.append({'tenant_id': 'A', 'booking_id': 'booking', 'status': 'draft'})
    elif change == 'folio_closed':
        ledger.folios.rows[0]['status'] = 'closed'
    else:
        ledger.billing_concessions.rows.append({'_id': 'other', 'tenant_id': 'A', 'booking_id': 'booking', 'folio_id': 'guest',
            'status': 'applied', 'amount_minor': 1, 'charge_ids': ['room'], 'allocated_charge_minor': {'room': 1}})
    with pytest.raises(HTTPException) as exc:
        await decide(ledger, data)
    assert exc.value.status_code in {409, 404}
    assert not any(row.get('concession_id') for row in ledger.payments.rows)


@pytest.mark.asyncio
@pytest.mark.parametrize('limits', [{}, {'EUR': 999999}, {'TRY': 99999}])
async def test_direct_concessions_do_not_require_approval_limits(ledger, limits):
    data = body()
    ledger.tenant_settings.rows[0]['enterprise_billing']['approval_limits_minor'] = limits
    assert (await request(ledger, data))['status'] == 'applied'


@pytest.mark.asyncio
async def test_legacy_distinct_services_allow_unrelated_balance_changes(ledger):
    ledger.folio_charges.rows.append({**ledger.folio_charges.rows[0], 'id': 'spa', 'charge_category': 'spa', 'total': 100})
    room, spa = body(mode='percentage', percentage=50), body(kind='selected_services_comp', charge_ids=['spa'])
    await legacy_pending(ledger, room)
    await legacy_pending(ledger, spa)
    ledger.payments.rows.append({'tenant_id': 'A', 'folio_id': 'guest', 'currency': 'TRY', 'amount': 100, 'method': 'card'})
    assert (await decide(ledger, room, actor='requester'))['status'] == 'applied'
    assert (await decide(ledger, spa, actor='requester'))['status'] == 'applied'
    assert ledger.folios.rows[0]['balance'] == 400


@pytest.mark.asyncio
async def test_other_tenant_cannot_request_or_approve(ledger):
    data = body()
    await request(ledger, data)
    with pytest.raises(HTTPException) as exc:
        await billing.decide_concession(ledger, 'B', 'manager', data.request_id, True, session=object())
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        await billing.request_concession(ledger, 'B', 'requester', body(), session=object())


@pytest.mark.asyncio
async def test_non_transactional_calls_rejected(ledger):
    with pytest.raises(HTTPException) as exc:
        await billing.request_concession(ledger, 'A', 'requester', body(), session=None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize('failed_collection', ['pms_audit_trail', 'audit_logs', 'folios', 'billing_concessions'])
async def test_injected_failure_rolls_back_entire_direct_operation(ledger, failed_collection):
    data = body()
    getattr(ledger, failed_collection).fail = True
    before = {key: deepcopy(coll.rows) for key, coll in vars(ledger).items()}
    try:
        with pytest.raises(RuntimeError):
            await request(ledger, data)
    finally:
        # Fake transaction's rollback. Production wrapper uses Mongo transaction.
        for key, rows in before.items():
            getattr(ledger, key).rows = rows
    assert not ledger.payments.rows and not ledger.billing_concessions.rows and not ledger.audit_logs.rows


@pytest.mark.parametrize('changes', [{'mode': 'full', 'amount_minor': 10}, {'mode': 'percentage', 'percentage': 101},
    {'mode': 'amount', 'amount_minor': True}, {'charge_ids': ['room', 'room']}, {'reason': ' x '}, {'mode': 'percentage', 'percentage': 'NaN'}])
def test_request_validation(changes):
    with pytest.raises(ValidationError):
        body(**changes)


@pytest.mark.parametrize('account,code,amount,balance', [({'is_active': False}, 'TRY', 1, 0),
    ({'credit_limit': 100, 'currency': 'TRY'}, 'TRY', 1, 100), ({'credit_limit': 100}, 'TRY', 1, 0),
    ({'currency': 'EUR'}, 'TRY', 1, 0), ({'credit_limit': -1}, 'TRY', 1, 0), ({}, 'TRY', 1, float('nan'))])
def test_direct_bill_guards(account, code, amount, balance):
    with pytest.raises(HTTPException):
        billing.assert_direct_bill_capacity(account, code, amount, balance)


def test_direct_bill_exact_limit_and_legacy_zero_limit():
    billing.assert_direct_bill_capacity({'credit_limit': 100, 'currency': 'TRY'}, 'TRY', 1, 99)
    billing.assert_direct_bill_capacity({'credit_limit': 0}, 'TRY', 1000, 9999)


@pytest.mark.asyncio
async def test_same_service_cannot_be_comped_twice_after_other_charges_added(ledger):
    data = body()
    await request(ledger, data)
    await decide(ledger, data)
    ledger.folio_charges.rows.append({**ledger.folio_charges.rows[0], 'id': 'new', 'total': 10000})
    with pytest.raises(HTTPException):
        await request(ledger, body())


@pytest.mark.asyncio
async def test_comp_capacity_follows_service_identity_after_folio_move(ledger):
    data = body()
    await request(ledger, data)
    await decide(ledger, data)
    ledger.folios.rows.append({**ledger.folios.rows[0], 'id': 'company', 'balance': 1000})
    ledger.folio_charges.rows[0]['folio_id'] = 'company'
    with pytest.raises(HTTPException) as exc:
        await request(ledger, body(folio_id='company'))
    assert exc.value.status_code == 409
    assert len(ledger.payments.rows) == 1


@pytest.mark.parametrize('limits', [{'TRY': True}, {'TRY': '100'}, {'try': 100}, {'TRY': -1}])
def test_policy_rejects_coercion_or_invalid_limits(limits):
    with pytest.raises((ValidationError, HTTPException)):
        billing.BillingPolicy(approval_limits_minor=limits)


@pytest.fixture
def funds(ledger):
    from unittest.mock import AsyncMock

    ledger.security_funds = Collection()
    ledger.security_fund_operations = Collection()
    return ledger, AsyncMock(return_value={'id': 'cash-entry'})


async def receive_fund(funds, **changes):
    from modules.pms_core import security_funds as security

    body = security.Receipt(**{'request_id': uuid4(), 'booking_id': 'booking', 'amount_minor': 100000, 'currency': 'TRY',
        'method': 'bank_transfer', 'reference': 'bank-001', 'reason': 'Hasar güvencesi', **changes})
    result = await security.receive(funds[0], 'A', 'operator', body, session=object(), record_cash=funds[1])
    return result, body


async def move_fund(funds, fund_id, **changes):
    from modules.pms_core import security_funds as security

    body = security.Movement(**{'request_id': uuid4(), 'action': 'apply', 'amount_minor': 60000, 'folio_id': 'guest',
        'reference': 'application-001', 'reason': 'Misafirin talebiyle mahsup', **changes})
    return await security.move(funds[0], 'A', 'operator', fund_id, body, session=object(), record_cash=funds[1])


@pytest.mark.asyncio
async def test_security_receive_apply_refund_does_not_collect_twice(funds):
    from core.booking_payment_state import collected_amount
    from modules.pms_core.reporting_financials import effective_folio_payment

    db, cash = funds
    initial = deepcopy(db.folios.rows)
    fund, _ = await receive_fund(funds)
    assert fund['remaining_minor'] == 100000
    assert not db.payments.rows and db.folios.rows == initial
    cash.assert_not_awaited()
    applied = await move_fund(funds, fund['id'])
    assert applied['remaining_minor'] == 40000 and applied['applied_minor'] == 60000
    assert db.folios.rows[0]['balance'] == 400
    assert effective_folio_payment(db.payments.rows[0]) == 600
    assert effective_collection(db.payments.rows[0]) == collected_amount(db.payments.rows) == 0
    refunded = await move_fund(funds, fund['id'], action='refund', amount_minor=40000, folio_id=None, reference='refund-001')
    assert refunded['status'] == 'closed' and refunded['refunded_minor'] == 40000
    assert len(db.payments.rows) == 1 and db.folios.rows[0]['balance'] == 400
    cash.assert_not_awaited()


@pytest.mark.asyncio
async def test_security_reference_replay_and_excess_movement(funds):
    fund, _ = await receive_fund(funds)
    assert (await receive_fund(funds))[0]['id'] == fund['id']
    assert len(funds[0].security_funds.rows) == 1
    await move_fund(funds, fund['id'])
    await move_fund(funds, fund['id'])  # same external ref, different UUID
    assert len(funds[0].payments.rows) == 1
    with pytest.raises(HTTPException):
        await move_fund(funds, fund['id'], amount_minor=60000, reference='different-application')


@pytest.mark.asyncio
async def test_security_reference_cannot_be_replayed_against_different_folio(funds):
    fund, _ = await receive_fund(funds)
    await move_fund(funds, fund['id'])
    with pytest.raises(HTTPException) as exc:
        await move_fund(funds, fund['id'], folio_id='company')
    assert exc.value.status_code == 409
    assert len(funds[0].payments.rows) == 1
    assert funds[0].security_funds.rows[0]['applied_minor'] == 60000


@pytest.mark.parametrize('code', ['JPY', 'KWD', 'BHD'])
def test_unverified_currency_scale_rejected(code):
    with pytest.raises(HTTPException) as exc:
        billing.require_cent_currency(code)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_security_cash_requires_atomic_cashier_entry(funds):
    await receive_fund(funds, method='cash')
    assert funds[1].await_args.kwargs['session'] is not None
    assert funds[1].await_args.kwargs['require_open_shift'] is True
    assert funds[1].await_args.kwargs['direction'] == 'in'
    funds[1].return_value = None
    with pytest.raises(HTTPException) as exc:
        await receive_fund(funds, method='cash', reference='cash-002')
    assert exc.value.status_code == 503 and len(funds[0].security_funds.rows) == 1


@pytest.mark.asyncio
async def test_cashier_storage_failure_propagates_to_financial_transaction(monkeypatch):
    from unittest.mock import AsyncMock

    from domains.pms import cashier_service

    shifts = SimpleNamespace(find_one=AsyncMock(return_value={'_id': 'shift', 'status': 'open'}),
        update_one=AsyncMock(side_effect=RuntimeError('synthetic storage failure')))
    monkeypatch.setattr(cashier_service, 'db', SimpleNamespace(cashier_shifts=shifts))
    monkeypatch.setattr(cashier_service, 'stamp_open_business_date', AsyncMock(return_value='2026-10-24'))
    session = object()
    with pytest.raises(RuntimeError, match='synthetic storage failure'):
        await cashier_service.record_cash_transaction(tenant_id='A', amount=100, method='cash', direction='in',
            description='Synthetic security receipt', require_open_shift=True, session=session)
    assert shifts.find_one.await_args.kwargs['session'] is session
    assert shifts.update_one.await_args.kwargs['session'] is session


@pytest.mark.asyncio
async def test_security_foreign_or_wrong_booking_target_rejected(funds):
    with pytest.raises(HTTPException):
        await receive_fund(funds, currency='EUR')
    fund, _ = await receive_fund(funds)
    funds[0].folios.rows[0]['booking_id'] = 'other-booking'
    with pytest.raises(HTTPException):
        await move_fund(funds, fund['id'])
    assert not funds[0].payments.rows


@pytest.mark.asyncio
async def test_security_other_tenant_cannot_use_fund(funds):
    from modules.pms_core import security_funds as security

    fund, _ = await receive_fund(funds)
    with pytest.raises(HTTPException) as exc:
        await security.move(funds[0], 'B', 'operator', fund['id'], security.Movement(request_id=uuid4(), action='refund',
            amount_minor=1, reference='test-ref', reason='Test refund'), session=object(), record_cash=funds[1])
    assert exc.value.status_code == 404


@pytest.fixture
def routing(ledger, monkeypatch):
    from core import booking_atomicity
    from domains.pms import folio_routing_router as router

    ledger.folios.rows.append({**ledger.folios.rows[0], 'id': 'company', 'balance': 0})
    ledger.folio_operations = Collection()
    ledger.folio_routing = Collection([{'id': 'rule', 'tenant_id': 'A', 'source_folio_id': 'guest', 'dest_folio_id': 'company',
        'active': True, 'charge_codes': ['ROOM'], 'from_date': '2026-10-23', 'to_date': '2026-10-23'}])
    monkeypatch.setattr(router, 'get_system_db', lambda: ledger)

    async def transaction(**kwargs):
        before = {key: deepcopy(value.rows) for key, value in vars(ledger).items()}
        try:
            return await kwargs['callback'](object())
        except Exception:
            for key, rows in before.items():
                getattr(ledger, key).rows = rows
            raise

    monkeypatch.setattr(booking_atomicity, 'with_resource_locks', transaction)
    return ledger, router


@pytest.mark.asyncio
async def test_routing_moves_real_items_and_tax_not_just_a_marker(routing):
    db, router = routing
    result = await router.apply_routing('guest', user=SimpleNamespace(tenant_id='A', id='operator'), _perm=None)
    assert result['moved'] == 1 and result['execution'] == 'manual_posted_items'
    assert db.folio_charges.rows[0]['folio_id'] == 'company'
    assert db.folio_charges.rows[0]['tax_amount'] == 100
    assert db.folios.rows[0]['balance'] == 0 and db.folios.rows[1]['balance'] == 1000
    assert not db.payments.rows
    result = await router.apply_routing('guest', user=SimpleNamespace(tenant_id='A', id='operator'), _perm=None)
    assert result['moved'] == 0


@pytest.mark.asyncio
async def test_overlapping_or_closed_destination_routing_fails_closed(routing):
    db, router = routing
    db.folio_routing.rows.append({**db.folio_routing.rows[0], 'id': 'overlap'})
    with pytest.raises(HTTPException) as exc:
        await router.apply_routing('guest', user=SimpleNamespace(tenant_id='A', id='operator'), _perm=None)
    assert exc.value.status_code == 409
    assert db.folio_charges.rows[0]['folio_id'] == 'guest'
    db.folio_routing.rows.pop()
    db.folios.rows[1]['status'] = 'closed'
    with pytest.raises(HTTPException):
        await router.apply_routing('guest', user=SimpleNamespace(tenant_id='A', id='operator'), _perm=None)
    assert not db.folio_operations.rows


@pytest.mark.parametrize('method', ['discount', 'complimentary', 'full_comp', 'city_ledger', 'security_deposit_application', 'authorization', 'wallet', 'gift_card', 'barter', 'check'])
def test_non_collection_cannot_be_posted_as_manual_collection(method):
    with pytest.raises(HTTPException) as exc:
        billing.manual_collection_method(method)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('target,code,status', [(None, 'TRY', 409), ('foreign', 'TRY', 404), ('company', 'EUR', 409), ('company', 'TRY', None)])
async def test_psp_endpoint_selects_only_explicit_window_and_currency(monkeypatch, target, code, status):
    from unittest.mock import AsyncMock

    from core.payments.collection import CollectionOutcome
    from routers import payments_router as router

    db = SimpleNamespace(bookings=Collection([{'tenant_id': 'A', 'id': 'booking', 'currency': 'TRY'}]),
        folios=Collection([{'tenant_id': 'A', 'id': key, 'booking_id': 'booking', 'status': 'open', 'currency': 'TRY'} for key in ['guest', 'company']]))
    collect = AsyncMock(return_value=CollectionOutcome(status='paid', response={'id': 'payment'}))
    monkeypatch.setattr(router, 'db', db)
    monkeypatch.setattr(router, 'get_provider_for_tenant', AsyncMock(return_value=SimpleNamespace(name='test')))
    monkeypatch.setattr(router, 'ensure_idempotent_request', lambda *_args, **_kwargs: 'test-key')
    monkeypatch.setattr(router, 'collect_booking_payment', collect)
    request = router.CollectPaymentRequest(amount=10, currency=code, folio_id=target, vault_card_ref='vault_v1:test')
    if status:
        with pytest.raises(HTTPException) as exc:
            await router.collect_payment('booking', request, object(), current_user=SimpleNamespace(tenant_id='A', name='operator'), _perm=None)
        assert exc.value.status_code == status
        collect.assert_not_awaited()
    else:
        assert (await router.collect_payment('booking', request, object(), current_user=SimpleNamespace(tenant_id='A', name='operator'), _perm=None))['id'] == 'payment'
        assert collect.await_args.kwargs['folio']['id'] == 'company'


@pytest.mark.asyncio
async def test_legacy_mock_intents_fail_without_writes():
    from domains.pms.misc import payments_folio

    for handler in [payments_folio.payment_intent, payments_folio.create_payment_intent]:
        with pytest.raises(HTTPException) as exc:
            await handler({'amount': 100}, current_user=SimpleNamespace(tenant_id='A'), _perm=None)
        assert exc.value.status_code == 501


@pytest.mark.asyncio
@pytest.mark.parametrize('link', ['security_fund_id', 'concession_id', 'provider_ref'])
async def test_linked_financial_payment_cannot_be_voided_as_manual_cash(monkeypatch, link):
    from modules.pms_core import folio_hardening_service

    payments = Collection([{'id': 'linked-payment', 'tenant_id': 'A', 'amount': 100, link: 'protected-reference'}])
    monkeypatch.setattr(folio_hardening_service, 'db', SimpleNamespace(payments=payments))
    result = await folio_hardening_service.FolioHardeningService().void_payment('A', 'linked-payment', 'Synthetic void', 'operator')
    assert result['success'] is False
    assert not payments.rows[0].get('voided')


@pytest.mark.asyncio
async def test_catalog_not_configured_is_explicit_and_never_calls_provider(monkeypatch):
    from core.payments import registry
    from core.payments.contracts import ProviderNotConfigured

    async def absent(*_):
        raise ProviderNotConfigured()

    monkeypatch.setattr(registry, 'get_provider_for_tenant', absent)
    catalog = await billing.payment_catalog(None, 'A')
    assert catalog['provider_readiness'] == 'not_configured'
    assert not catalog['not_enabled'] and 'authorization' in catalog['non_collection_operations']
    assert {row['code'] for row in catalog['instrument_methods']} == {'wallet', 'gift_card_redemption', 'loyalty_redemption', 'barter', 'write_off', 'cheque_pending_clearance'}
    assert all(row['requires_explicit_account_and_evidence'] for row in catalog['instrument_methods'])
