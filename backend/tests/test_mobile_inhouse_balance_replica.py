"""Real isolated Mongo: native room card and reservation account agree."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms.frontdesk_service import FrontdeskService
from routers.reservation_detail import _reservation_financial_snapshot

pytest_plugins = ('tests.test_report_ledger_mongo_acceptance',)


@pytest.mark.asyncio
async def test_partial_night_posting_and_refunded_receipt_use_durable_reservation_balance(ledger_db):
    db = ledger_db
    booking = {'id': 'stay', 'tenant_id': 'hotel', 'status': 'checked_in', 'total_amount': 2400,
               'currency': 'TRY', 'balance': 1479.39, 'room_number': '119'}
    await db.bookings.insert_one(deepcopy(booking))
    await db.folios.insert_one({'id': 'folio', 'tenant_id': 'hotel', 'booking_id': 'stay'})
    await db.folio_charges.insert_one({'id': 'night1', 'tenant_id': 'hotel', 'folio_id': 'folio',
        'charge_category': 'room', 'total': 1200, 'currency': 'TRY', 'posted_by': 'night_audit'})
    await db.extra_charges.insert_one({'id': 'extra', 'tenant_id': 'hotel', 'booking_id': 'stay', 'total': 315})
    await db.payments.insert_many([
        {'id': 'paid', 'tenant_id': 'hotel', 'folio_id': 'folio', 'amount': 35.61, 'method': 'cash'},
        {'id': 'refunded', 'tenant_id': 'hotel', 'booking_id': 'stay', 'amount': 20, 'method': 'cash', 'voided': True},
        {'id': 'foreign', 'tenant_id': 'other', 'booking_id': 'stay', 'folio_id': 'folio', 'amount': 9999, 'method': 'cash'},
    ])
    service = FrontdeskService.__new__(FrontdeskService)
    service._db = db
    service._enrich_bookings = AsyncMock(side_effect=lambda rows, tenant: rows)
    result = await service.get_unified_inhouse(SimpleNamespace(tenant_id='hotel'))
    card = result.data['in_house'][0]
    detail = await _reservation_financial_snapshot('hotel', booking, database=db)
    assert card['balance'] == detail['reservation_total_due'] == 2679.39
    assert card['balance_basis'] == 'reservation_total_due'
    assert card['currency'] == 'TRY'
    assert (await db.bookings.find_one({'id': 'stay'}))['balance'] == 1479.39
    assert await db.payments.count_documents({}) == 3
    await db.folio_charges.insert_one({'id': 'night2', 'tenant_id': 'hotel', 'booking_id': 'stay',
        'charge_category': 'room', 'total': 1200, 'currency': 'TRY', 'posted_by': 'night_audit'})
    result = await service.get_unified_inhouse(SimpleNamespace(tenant_id='hotel'))
    assert result.data['in_house'][0]['balance'] == 2679.39


@pytest.mark.asyncio
async def test_batch_keeps_currencies_and_stays_separate_with_folio_only_sources(ledger_db):
    from domains.pms.reservation_balance_projection import reservation_balances

    db = ledger_db
    bookings = [{'id': 'try', 'total_amount': 100, 'currency': 'TRY'},
                {'id': 'usd', 'total_amount': 10, 'currency': 'USD'}]
    await db.folios.insert_many([{'tenant_id': 'hotel', 'id': 'ft', 'booking_id': 'try'},
                                {'tenant_id': 'hotel', 'id': 'fu', 'booking_id': 'usd'}])
    await db.payments.insert_many([{'id': 't', 'tenant_id': 'hotel', 'folio_id': 'ft', 'amount': 20, 'method': 'cash'},
                                  {'id': 'u', 'tenant_id': 'hotel', 'folio_id': 'fu', 'amount': 2, 'method': 'cash'}])
    assert await reservation_balances(db, 'hotel', bookings) == {'try': 80, 'usd': 8}
    assert await reservation_balances(db, 'hotel', []) == {}
