"""Group guest-card parity, using only disposable LOCAL Mongo."""
from types import SimpleNamespace

import pytest

from routers.hotel_services_pkg import group_folio as route
from tests import test_pos_final_consistency_replica as replica_fixtures

db = replica_fixtures.db


async def seed(database, monkeypatch):
    monkeypatch.setattr(route, 'db', database)
    await database.group_bookings.insert_one({'id': 'g', 'tenant_id': 't', 'status': 'active', 'booking_ids': ['b1', 'b2']})
    await database.bookings.insert_many([
        {'id': 'b1', 'tenant_id': 't', 'guest_name': 'Eren Aydın', 'room_number': '118', 'currency': 'TRY', 'total_amount': 2400},
        {'id': 'b2', 'tenant_id': 't', 'guest_name': 'Derya Şen', 'room_number': '119', 'currency': 'TRY', 'total_amount': 2400, 'paid_amount': 9999},
    ])
    await database.folios.insert_one({'id': 'f', 'tenant_id': 't', 'booking_id': 'b2', 'status': 'open', 'currency': 'TRY', 'balance': 0})
    await database.folio_charges.insert_many([{'id': f'laundry{i}', 'tenant_id': 't', 'folio_id': 'f', 'total': 25, 'charge_category': 'laundry'} for i in range(3)])
    await database.extra_charges.insert_many([{'id': f'extra{i}', 'tenant_id': 't', 'booking_id': 'b2', 'charge_amount': amount} for i, amount in enumerate([120, 80, 60])])
    return SimpleNamespace(tenant_id='t', name='Operator')


@pytest.mark.asyncio
async def test_group_booking_balance_includes_folio_only_services_and_booking_extras(db, monkeypatch):
    actor = await seed(db, monkeypatch)
    result = await route.get_group_folio_status('g', actor)
    second = next(row for row in result['bookings'] if row['booking_id'] == 'b2')
    assert second['balance'] == 2735
    assert sum(row['balance'] for row in result['bookings']) == 5135
    assert second['folio_charges'] == 335 and second['payments'] == 0


@pytest.mark.asyncio
async def test_summary_deduplicates_membership_and_separates_currencies(db, monkeypatch):
    actor = await seed(db, monkeypatch)
    await db.group_bookings.insert_one({'id': 'g2', 'tenant_id': 't', 'booking_ids': ['b2']})
    result = await route.get_group_folio_summary(actor)
    assert result['total_balance'] == 5135
    assert result['total_bookings'] == 2
    await db.bookings.update_one({'id': 'b1'}, {'$set': {'currency': 'USD'}})
    result = await route.get_group_folio_summary(actor)
    assert result['total_balance'] is None
    assert result['totals_by_currency'] == {'USD': 2400, 'TRY': 2735}


@pytest.mark.asyncio
async def test_detail_requires_membership_and_never_returns_account_headers(db, monkeypatch):
    from fastapi import HTTPException
    actor = await seed(db, monkeypatch)
    result = await route.get_group_booking_folio_detail('g', 'b2', actor)
    assert len(result['charges']) == 3
    assert len(result['extra_charges']) == 3
    assert result['folios'] == []
    with pytest.raises(HTTPException) as error:
        await route.get_group_booking_folio_detail('other', 'b2', actor)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_posted_room_and_mirrored_extra_not_counted_twice(db, monkeypatch):
    await seed(db, monkeypatch)
    await db.folio_charges.insert_many([
        {'id': 'room', 'tenant_id': 't', 'folio_id': 'f', 'total': 1200, 'charge_category': 'room'},
        {'id': 'mirror', 'tenant_id': 't', 'folio_id': 'f', 'total': 120, 'charge_category': 'minibar', 'source_extra_charge_id': 'extra0'},
    ])
    rows = await route._load_group_booking_rows('t', ['b2'])
    assert rows[0]['balance'] == 2735
    assert rows[0]['unposted_room_amount'] == 1200


@pytest.mark.asyncio
async def test_mixed_currency_inside_one_booking_rejected(db, monkeypatch):
    from fastapi import HTTPException
    await seed(db, monkeypatch)
    await db.folio_charges.insert_one({'id': 'foreign', 'tenant_id': 't', 'folio_id': 'f', 'total': 5, 'currency': 'USD'})
    with pytest.raises(HTTPException) as error:
        await route._load_group_booking_rows('t', ['b2'])
    assert error.value.status_code == 409
