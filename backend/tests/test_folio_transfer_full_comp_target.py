"""A normal service transfer must not silently defeat full-stay comp."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

from routers.finance import folio as route
from tests.test_department_live_folio_acceptance import actor, db, wired  # noqa: F401
from tests.test_folio_cross_room_transfer_replica import body
from tests.test_folio_cross_room_transfer_replica import transfer_db as isolated_transfer_db

transfer_db = isolated_transfer_db


async def test_full_comp_target_rejects_positive_transfer_without_partial_writes(transfer_db):
    await transfer_db.bookings.update_one({"id": "b2"}, {"$set": {"is_complimentary": True, "complimentary_scope": "full"}})
    before = deepcopy(await transfer_db.folio_charges.find_one({"id": "service"}))
    with pytest.raises(HTTPException) as error:
        await route.transfer_charges(body(), actor())
    assert error.value.status_code == 409
    assert await transfer_db.folio_charges.find_one({"id": "service"}) == before
    assert (await transfer_db.folios.find_one({"id": "actual-folio"}))["balance"] == 150
    assert (await transfer_db.folios.find_one({"id": "target"}))["balance"] == 0
    assert await transfer_db.folio_operations.count_documents({}) == 0
    assert await transfer_db.payments.count_documents({}) == 0


async def test_room_only_comp_does_not_block_an_unrelated_parking_transfer(transfer_db):
    await transfer_db.bookings.update_one({"id": "b2"}, {"$set": {"is_complimentary": True, "complimentary_scope": "room"}})
    await route.transfer_charges(body(), actor())
    assert (await transfer_db.folio_charges.find_one({"id": "service"}))["folio_id"] == "target"
    assert (await transfer_db.folios.find_one({"id": "target"}))["balance"] == 150
