"""External parking never writes a room charge or PMS payment; LOCAL replica only."""
import asyncio
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException

from core.external_parking_settlement import ParkingSettlement
from domains.pms import transfer_parking_router as parking
from tests.test_department_live_folio_acceptance import actor, wired  # noqa: F401
from tests.test_pos_final_consistency_replica import db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def book(database, **changes):
    await database.transport_resources.update_one({'id': 'spot', 'tenant_id': 't'}, {'$set': {
        'id': 'spot', 'tenant_id': 't', 'name': 'External parking', 'kind': 'parking_spot',
        'price': 150, 'currency': 'TRY', 'capacity': 1, 'active': True}}, upsert=True)
    data = {'resource_id': 'spot', 'customer_type': 'external', 'guest_name': 'Selin Acar',
        'start_date': '2026-10-26', 'num_days': 1, 'vat_rate': 20, 'idempotency_key': 'external-parking-1', **changes}
    return await parking.create_booking(parking.BookingIn(**data), actor())


def receipt(method='cash', **changes):
    return ParkingSettlement(request_id=uuid4(), amount=150, currency='TRY', method=method,
        reference='Synthetic acceptance only', **changes)


@pytest.mark.parametrize('method', ['cash', 'card', 'bank_transfer'])
async def test_roomless_external_receipt_has_tax_and_no_guest_folio_side_effect(wired, method):  # noqa: F811 - imported pytest fixture
    created = await book(wired)
    source = created['booking']
    assert source['customer_type'] == 'external' and not source['folio_charged'] and not source['folio_id']
    assert await wired.transport_late_charges.count_documents({}) == 0
    assert await wired.folio_charges.count_documents({}) == await wired.payments.count_documents({}) == 0
    body = receipt(method)
    first = await parking.settle_external_parking(source['id'], body, actor())
    repeated = await parking.settle_external_parking(source['id'], body, actor())
    assert repeated['replayed']
    payment = first['payment']
    assert (payment['amount'], payment['net'], payment['vat_amount']) == (150, 125, 25)
    assert payment['business_date'] == '2026-10-26'
    assert await wired.transport_payments.count_documents({}) == 1
    assert await wired.folio_charges.count_documents({}) == await wired.payments.count_documents({}) == 0
    report = await parking.parking_analytics(actor(), business_date=date(2026, 10, 26))
    assert report['external_payments_by_currency']['TRY'] == {'receipts': 150, 'refunds': 0, 'net_receipts': 150, 'net_revenue': 125, 'vat': 25}
    assert (await wired.folios.find_one({'id': 'actual-folio'}))['balance'] == 0
    assert (await wired.audit_logs.find_one({'action': 'external_parking_receipt'}))['record_hash']


async def test_double_receipt_with_different_keys_cannot_double_collection(wired):  # noqa: F811 - imported pytest fixture
    source = (await book(wired))['booking']
    results = await asyncio.gather(parking.settle_external_parking(source['id'], receipt(), actor()),
        parking.settle_external_parking(source['id'], receipt(), actor()), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert all(isinstance(r, dict) or isinstance(r, HTTPException) and r.status_code == 409 for r in results)
    assert await wired.transport_payments.count_documents({}) == 1


async def test_full_refund_preserves_original_receipt_and_then_allows_cancellation(wired):  # noqa: F811 - imported pytest fixture
    source = (await book(wired))['booking']
    first = await parking.settle_external_parking(source['id'], receipt(), actor())
    with pytest.raises(HTTPException) as blocked:
        await parking.cancel_booking(source['id'], actor())
    assert blocked.value.status_code == 409
    assert await wired.transport_slot_locks.count_documents({}) == 1
    original = await wired.transport_payments.find_one({'id': first['payment']['id']})
    body = receipt()
    refunded = await parking.refund_external_parking(source['id'], body, actor())
    assert (await parking.refund_external_parking(source['id'], body, actor()))['replayed']
    assert refunded['payment']['original_receipt_id'] == original['id']
    assert await wired.transport_payments.find_one({'id': original['id']}) == original
    with pytest.raises(HTTPException):
        await parking.refund_external_parking(source['id'], receipt(), actor())
    report = await parking.parking_analytics(actor(), business_date=date(2026, 10, 26))
    assert report['external_payments_by_currency']['TRY'] == {'receipts': 150, 'refunds': 150, 'net_receipts': 0, 'net_revenue': 0, 'vat': 0}
    assert (await parking.cancel_booking(source['id'], actor()))['status'] == 'cancelled'
    assert await wired.transport_slot_locks.count_documents({}) == 0
    assert await wired.folio_charges.count_documents({}) == await wired.payments.count_documents({}) == 0


@pytest.mark.parametrize('fields', [{'room_number': '101'}, {'booking_id': 'b'}, {'folio_id': 'actual-folio'}, {'vat_rate': None}, {'guest_name': ''}])
async def test_external_customer_cannot_be_attached_to_room_or_missing_tax(wired, fields):  # noqa: F811 - imported pytest fixture
    with pytest.raises(HTTPException) as error:
        await book(wired, **fields)
    assert error.value.status_code == 422
    assert await wired.transport_slot_locks.count_documents({}) == 0
    assert await wired.transport_bookings.count_documents({}) == 0


async def test_external_booking_replay_payload_cannot_change(wired):  # noqa: F811 - imported pytest fixture
    first = await book(wired)
    assert (await book(wired))['idempotent']
    with pytest.raises(HTTPException):
        await book(wired, num_days=2)
    assert await wired.transport_bookings.count_documents({}) == 1
    assert (await wired.transport_bookings.find_one({}))['id'] == first['booking']['id']


async def test_bad_currency_wrong_tenant_and_cancelled_source_reject(wired):  # noqa: F811 - imported pytest fixture
    source = (await book(wired))['booking']
    body = receipt().model_copy(update={'currency': 'USD'})
    with pytest.raises(HTTPException):
        await parking.settle_external_parking(source['id'], body, actor())
    other = actor(); other.tenant_id = 'other'
    with pytest.raises(HTTPException):
        await parking.settle_external_parking(source['id'], receipt(), other)
    await parking.cancel_booking(source['id'], actor())
    with pytest.raises(HTTPException):
        await parking.settle_external_parking(source['id'], receipt(), actor())
    assert await wired.transport_payments.count_documents({}) == 0


async def test_audit_failure_rolls_back_receipt_and_paid_status(wired, monkeypatch):  # noqa: F811 - imported pytest fixture
    from unittest.mock import AsyncMock
    source = (await book(wired))['booking']
    monkeypatch.setattr('core.external_parking_settlement.append_audit_log', AsyncMock(side_effect=RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError):
        await parking.settle_external_parking(source['id'], receipt(), actor())
    assert await wired.transport_payments.count_documents({}) == 0
    assert (await wired.transport_bookings.find_one({'id': source['id']}))['payment_status'] == 'unpaid'
