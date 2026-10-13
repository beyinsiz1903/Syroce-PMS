from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import marketplace_b2b as marketplace


@pytest.mark.asyncio
async def test_modification_lock_evidence_resolves_proposal_to_its_booking():
    negotiations = SimpleNamespace(find_one=AsyncMock(return_value={
        "id": "proposal-1", "reservation_id": "booking-1", "status": "awaiting_hotel",
    }))
    bookings = SimpleNamespace(find_one=AsyncMock(return_value={"id": "booking-1", "status": "confirmed"}))
    database = SimpleNamespace(marketplace_negotiations=negotiations, bookings=bookings)

    evidence = await marketplace._sales_lock_evidence(database, {
        "tenant_id": "hotel-1", "agency_id": "agency-1", "operation": "marketplace_modification",
        "reference_id": "proposal-1", "idempotency_key": None,
    })

    assert evidence["proposal"]["reservation_id"] == "booking-1"
    assert evidence["booking"]["id"] == "booking-1"
    assert bookings.find_one.call_args.args[0]["id"] == "booking-1"


@pytest.mark.asyncio
async def test_recovery_never_deletes_lock_when_audit_record_cannot_be_saved(monkeypatch):
    lock = {"_id": "lock-1", "owner": "owner-123", "tenant_id": "hotel-1", "agency_id": "agency-1"}
    mutexes = SimpleNamespace(
        find_one=AsyncMock(return_value=lock),
        delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
    )
    database = SimpleNamespace(
        agency_sale_mutexes=mutexes,
        agency_sales_lock_recoveries=SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock(side_effect=RuntimeError("storage unavailable"))),
    )
    monkeypatch.setattr(marketplace, "get_system_db", lambda: database)
    monkeypatch.setattr(marketplace, "_sales_lock_evidence", AsyncMock(return_value={"booking": None, "idempotency": None, "proposal": None}))

    data = marketplace.AgencySalesLockReconcile(
        owner="owner-123", resolution="no_booking_committed", reason="Original writer was stopped safely", writer_stopped_confirmed=True,
    )
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await marketplace.admin_reconcile_agency_sales_lock("lock-1", data, True)
    mutexes.delete_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,ledger_value,expected', [('awaiting_hotel', 117, False), ('accepted', 90, False), ('accepted', 117, True)])
async def test_modification_requires_completed_matching_snapshot(status, ledger_value, expected):
    database = SimpleNamespace(
        marketplace_negotiations=SimpleNamespace(find_one=AsyncMock(return_value={
            'id': 'p', 'reservation_id': 'b', 'status': status, 'applied_snapshot': {'net_to_hotel': 117},
        })),
        bookings=SimpleNamespace(find_one=AsyncMock(return_value={'id': 'b', 'net_to_hotel': 117})),
        marketplace_bookings=SimpleNamespace(find_one=AsyncMock(return_value={'net_to_hotel': ledger_value})),
    )
    evidence = await marketplace._sales_lock_evidence(database, {
        'tenant_id': 't', 'agency_id': 'a', 'operation': 'marketplace_modification', 'reference_id': 'p',
    })
    assert evidence['modification_verified'] is expected


@pytest.mark.asyncio
async def test_partial_modification_cannot_release_existing_booking(monkeypatch):
    locks = SimpleNamespace(find_one=AsyncMock(return_value={'operation': 'marketplace_modification'}), delete_one=AsyncMock())
    monkeypatch.setattr(marketplace, 'get_system_db', lambda: SimpleNamespace(agency_sale_mutexes=locks))
    monkeypatch.setattr(marketplace, '_sales_lock_evidence', AsyncMock(return_value={'booking': {'id': 'b'}, 'modification_verified': False}))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await marketplace.admin_reconcile_agency_sales_lock('l', marketplace.AgencySalesLockReconcile(
            owner='owner-123', resolution='booking_committed', reason='Original writer stopped safely', writer_stopped_confirmed=True,
        ), True)
    assert exc.value.status_code == 409
    locks.delete_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_receipt_finishes_after_delete_response_or_final_update_loss(monkeypatch):
    lock = {'_id': 'l', 'owner': 'owner-123', 'tenant_id': 't', 'agency_id': 'a'}
    locks = SimpleNamespace(find_one=AsyncMock(return_value=lock), delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)))
    records = []
    async def insert(record):
        records.append(dict(record))
    receipts = SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock(side_effect=insert), update_one=AsyncMock(side_effect=RuntimeError('lost')))
    monkeypatch.setattr(marketplace, 'get_system_db', lambda: SimpleNamespace(agency_sale_mutexes=locks, agency_sales_lock_recoveries=receipts))
    monkeypatch.setattr(marketplace, '_sales_lock_evidence', AsyncMock(return_value={'booking': None, 'idempotency': None}))
    data = marketplace.AgencySalesLockReconcile(owner='owner-123', resolution='no_booking_committed', reason='Original writer stopped safely', writer_stopped_confirmed=True)
    with pytest.raises(RuntimeError):
        await marketplace.admin_reconcile_agency_sales_lock('l', data, True)
    assert records[0]['status'] == 'pending_release'
    locks.find_one.return_value = None  # Original owner absent; a replacement owner must not be deleted.
    receipts.find_one.return_value = records[0]
    receipts.update_one.side_effect = None
    assert (await marketplace.admin_reconcile_agency_sales_lock('l', data, True))['idempotent_replay']
    assert locks.delete_one.await_count == 1
