"""Cross-room folio acceptance against a disposable LOCAL transaction database."""
from copy import deepcopy
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException

from models.schemas import FolioOperationCreate
from routers.finance import folio as route
from tests.test_department_live_folio_acceptance import actor, db, wired  # noqa: F401


@pytest_asyncio.fixture
async def transfer_db(wired, monkeypatch):  # noqa: F811
    for name in ("folio_operations", "reservation_financial_locks", "pms_audit_trail", "invoices", "extra_charges"):
        await wired.create_collection(name)
    monkeypatch.setattr(route, "db", wired)
    monkeypatch.setattr("core.utils.db", wired)
    await wired.bookings.insert_one({"id": "b2", "tenant_id": "t", "status": "checked_in", "currency": "TRY"})
    await wired.folios.insert_one({"id": "target", "tenant_id": "t", "booking_id": "b2", "status": "open", "currency": "TRY", "balance": 0})
    await wired.folios.update_one({"id": "actual-folio"}, {"$set": {"balance": 150}})
    await wired.folio_charges.insert_one({"id": "service", "tenant_id": "t", "folio_id": "actual-folio", "booking_id": "b",
        "charge_category": "parking", "currency": "TRY", "amount": 125, "total": 150,
        "vat_amount": 25, "vat_rate": 20, "business_date": "2026-10-26", "service_date": "2026-10-26", "voided": False})
    await wired.folio_postings.insert_one({"id": "posting", "tenant_id": "t", "folio_charge_id": "service", "folio_id": "actual-folio", "booking_id": "b", "reservation_id": "b", "amount": 150})
    return wired


def body(**values):
    return FolioOperationCreate.model_validate({"operation_type": "transfer", "from_folio_id": "actual-folio",
        "to_folio_id": "target", "charge_ids": ["service"], "reason": "Oda hesabının ayrılması", "request_id": str(uuid4()), **values})


async def test_cross_room_transfer_retains_one_source_tax_and_updates_both_account_links(transfer_db):
    await route.transfer_charges(body(), actor())
    row = await transfer_db.folio_charges.find_one({"id": "service"})
    assert row["folio_id"] == "target" and row["booking_id"] == "b2"
    assert row["original_booking_id"] == "b"
    assert (row["total"], row["amount"], row["vat_amount"], row["service_date"], row["business_date"]) == (150, 125, 25, "2026-10-26", "2026-10-26")
    assert await transfer_db.folio_charges.count_documents({}) == 1
    assert (await transfer_db.folio_postings.find_one({"id": "posting"}))["booking_id"] == "b2"
    assert (await transfer_db.folio_postings.find_one({"id": "posting"}))["reservation_id"] == "b2"
    assert (await transfer_db.folios.find_one({"id": "actual-folio"}))["balance"] == 0
    assert (await transfer_db.folios.find_one({"id": "target"}))["balance"] == 150
    assert await transfer_db.payments.count_documents({}) == 0
    assert (await transfer_db.bookings.find_one({"id": "b"}))["balance"] == 0
    assert (await transfer_db.bookings.find_one({"id": "b2"}))["balance"] == 150


@pytest.mark.parametrize("kind", ["source_closed", "target_currency", "invoice", "foreign_target", "same_folio", "duplicate_charge",
                                  "room_night", "stay_tax", "legacy_extra_mirror", "sub_cent", "concession"])
async def test_invalid_target_or_ambiguous_request_cannot_partially_move_debt(transfer_db, kind):
    changes = {}
    if kind == "source_closed":
        await transfer_db.folios.update_one({"id": "actual-folio"}, {"$set": {"status": "closed"}})
    elif kind == "target_currency":
        await transfer_db.folios.update_one({"id": "target"}, {"$set": {"currency": "USD"}})
    elif kind == "invoice":
        await transfer_db.invoices.insert_one({"id": "invoice", "tenant_id": "t", "booking_id": "b2", "status": "draft"})
    elif kind == "foreign_target":
        await transfer_db.folios.update_one({"id": "target"}, {"$set": {"tenant_id": "other"}})
    elif kind == "same_folio":
        changes["to_folio_id"] = "actual-folio"
    elif kind == "duplicate_charge":
        changes["charge_ids"] = ["service", "service"]
    elif kind == "concession":
        await transfer_db.payments.insert_one({"id": "comp", "tenant_id": "t", "booking_id": "b", "folio_id": "actual-folio",
            "amount": 25, "method": "discount", "payment_type": "comp_adjustment", "charge_ids": ["service"], "currency": "TRY"})
    else:
        field, value = {"room_night": ("charge_category", "room"), "stay_tax": ("charge_category", "city_tax"),
            "legacy_extra_mirror": ("source_extra_charge_id", "legacy-extra"), "sub_cent": ("total", 150.001)}[kind]
        await transfer_db.folio_charges.update_one({"id": "service"}, {"$set": {field: value}})
    before = deepcopy(await transfer_db.folio_charges.find_one({"id": "service"}))
    with pytest.raises(HTTPException):
        await route.transfer_charges(body(**changes), actor())
    assert await transfer_db.folio_charges.find_one({"id": "service"}) == before
    assert await transfer_db.folio_operations.count_documents({}) == 0


async def test_failed_operation_record_rolls_back_the_original_charge_and_projection(transfer_db, monkeypatch):
    collection_type = type(transfer_db.folio_operations)
    original = collection_type.insert_one

    async def insert(collection, *args, **kwargs):
        if collection.name == "folio_operations":
            raise RuntimeError("operation log unavailable")
        return await original(collection, *args, **kwargs)

    monkeypatch.setattr(collection_type, "insert_one", insert)
    with pytest.raises(RuntimeError):
        await route.transfer_charges(body(), actor())
    row = await transfer_db.folio_charges.find_one({"id": "service"})
    assert row["folio_id"] == "actual-folio"
    assert (await transfer_db.folios.find_one({"id": "actual-folio"}))["balance"] == 150
    assert (await transfer_db.folios.find_one({"id": "target"}))["balance"] == 0


async def test_concurrent_repeat_and_reused_key_do_not_repost(transfer_db):
    import asyncio

    request = body()
    first, second = await asyncio.gather(route.transfer_charges(request, actor()), route.transfer_charges(request, actor()))
    assert first["id"] == second["id"]
    assert await transfer_db.folio_operations.count_documents({}) == 1
    assert await transfer_db.folio_charges.count_documents({}) == 1
    changed = request.model_copy(update={"reason": "Different instruction"})
    with pytest.raises(HTTPException) as error:
        await route.transfer_charges(changed, actor())
    assert error.value.status_code == 409


async def test_failed_reservation_readback_rolls_back_transfer_instead_of_acknowledging_stale_debt(transfer_db, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise RuntimeError("reservation projection unavailable")

    monkeypatch.setattr("core.booking_payment_state.refresh_booking_payment_state", unavailable)
    with pytest.raises(RuntimeError):
        await route.transfer_charges(body(), actor())
    assert (await transfer_db.folio_charges.find_one({"id": "service"}))["booking_id"] == "b"
    assert (await transfer_db.folios.find_one({"id": "actual-folio"}))["balance"] == 150
    assert await transfer_db.folio_operations.count_documents({}) == 0
