"""The legacy group-copy endpoint must never clone modern folio account headers."""
import pytest
from fastapi import HTTPException

from routers.hotel_services_pkg import group_folio as route
from routers.hotel_services_pkg._common import GroupFolioMerge
from tests import test_group_folio_ledger_replica as fixtures

db = fixtures.db


@pytest.mark.asyncio
@pytest.mark.parametrize('owner', ['b1', 'b2'])
async def test_modern_account_anywhere_in_merge_rejected_before_claim_or_copy(db, monkeypatch, owner):
    actor = await fixtures.seed(db, monkeypatch)
    await db.folios.delete_many({})
    await db.folios.insert_one({'id': 'modern', 'tenant_id': 't', 'booking_id': owner, 'status': 'open', 'balance': 335, 'currency': 'TRY'})
    before = await db.folios.count_documents({})
    with pytest.raises(HTTPException) as error:
        await route.merge_group_folios(GroupFolioMerge(group_id='g', master_booking_id='b1', merge_booking_ids=['b2']), actor, None)
    assert error.value.status_code == 409
    assert 'misafir kart' in error.value.detail
    assert await db.folios.count_documents({}) == before
    assert await db.payments.count_documents({}) == 0
    assert await db.bookings.count_documents({'folio_merge_claim': {'$exists': True}}) == 0
    assert await db.bookings.count_documents({'folio_merged_to': {'$exists': True}}) == 0
    assert await db.folio_merge_logs.count_documents({}) == 0
