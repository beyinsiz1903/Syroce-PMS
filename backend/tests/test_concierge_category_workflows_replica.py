"""Concierge category and real-DB binding regressions; explicit LOCAL replica only."""
# ruff: noqa: F811
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.pms import operations_router as ops
from tests.test_pos_final_consistency_replica import db  # noqa: F401

USER = SimpleNamespace(id="concierge-operator", tenant_id="t", role="admin", email="staff@example.invalid", is_super_admin=False)


@pytest_asyncio.fixture
async def wired(db, monkeypatch):
    monkeypatch.setattr(ops, "db", db)
    monkeypatch.setattr(ops, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await db.rooms.insert_one({"id": "r", "tenant_id": "t", "room_number": "105", "is_active": True})
    await db.guests.insert_one({"id": "g", "tenant_id": "t", "name": "Elif Yıldız"})
    await db.bookings.insert_one({"id": "b", "tenant_id": "t", "room_id": "r", "guest_id": "g", "guest_name": "Eski isim", "status": "checked_in"})
    await db.folios.insert_one({"id": "f", "tenant_id": "t", "booking_id": "b", "status": "open", "currency": "TRY"})
    return db


async def test_legacy_room_id_binding_uses_same_tenant_guest_and_open_folio(wired):
    result = await ops.concierge_active_room_lookup("105", USER)
    assert result["found"] is True
    assert (result["booking_id"], result["folio_id"], result["guest_id"], result["guest_name"]) == ("b", "f", "g", "Elif Yıldız")
    assert result["room_number"] == "105"
    assert "room_number" not in await wired.bookings.find_one({"id": "b"})


async def test_legacy_number_fallback_is_not_a_stale_number_on_another_room(wired):
    await wired.bookings.update_one({"id": "b"}, {"$set": {"room_id": "different", "room_number": "105"}})
    assert not (await ops.concierge_active_room_lookup("105", USER))["found"]
    await wired.bookings.update_one({"id": "b"}, {"$unset": {"room_id": ""}})
    assert (await ops.concierge_active_room_lookup("105", USER))["booking_id"] == "b"


@pytest.mark.parametrize("room_change", [{"tenant_id": "other"}, {"is_active": False}, {"is_virtual": True}])
async def test_foreign_inactive_or_virtual_rooms_are_not_autofilled(wired, room_change):
    await wired.rooms.update_one({"id": "r"}, {"$set": room_change})
    assert not (await ops.concierge_active_room_lookup("105", USER))["found"]


async def test_two_active_stays_never_choose_an_arbitrary_guest(wired):
    await wired.bookings.insert_one({"id": "b2", "tenant_id": "t", "room_id": "r", "status": "checked_in"})
    with pytest.raises(HTTPException) as exc:
        await ops.concierge_active_room_lookup("105", USER)
    assert exc.value.status_code == 409


async def test_two_open_folios_require_explicit_selection_instead_of_first_match(wired):
    await wired.folios.insert_one({"id": "f2", "tenant_id": "t", "booking_id": "b", "status": "open", "currency": "TRY"})
    result = await ops.concierge_active_room_lookup("105", USER)
    assert result["found"] and result["folio_id"] == "" and result["folio_selection_required"] is True


@pytest.mark.parametrize("amount", [True, "NaN", "Infinity", "-Infinity", 1.001, -1, 1_000_000_001])
async def test_invalid_money_is_rejected_before_creating_a_source(wired, amount):
    with pytest.raises(HTTPException) as exc:
        await ops.create_concierge_request({"type": "spa", "room_number": "105", "amount": amount}, USER, None)
    assert exc.value.status_code == 400
    assert await wired.concierge_requests.count_documents({}) == 0


@pytest.mark.parametrize("pax", [True, 0, -1, 1.5, "NaN", 100])
async def test_invalid_party_size_is_not_silently_coerced(wired, pax):
    with pytest.raises(HTTPException) as exc:
        await ops.create_concierge_request({"type": "tour", "room_number": "105", "pax": pax}, USER, None)
    assert exc.value.status_code == 400
    assert await wired.concierge_requests.count_documents({}) == 0


@pytest.mark.parametrize("kind", sorted(ops._VALID_CONCIERGE_TYPES))
async def test_each_visible_category_persists_the_verified_guest_binding_without_payment(wired, kind):
    created = await ops.create_concierge_request({"type": kind, "room_number": "105", "details": "Hizmet planı", "pax": 2, "amount": 0, "charge_to_folio": False}, USER, None)
    assert (created["booking_id"], created["folio_id"], created["guest_name"]) == ("b", "f", "Elif Yıldız")
    assert created["room_match_found"] and created["created_by"] == USER.email
    await ops.update_concierge_request(created["id"], {"status": "in_progress"}, USER, None)
    await ops.update_concierge_request(created["id"], {"status": "completed"}, USER, None)
    listing = await ops.get_concierge_requests(current_user=USER)
    assert listing["total"] == 1 and listing["requests"][0]["type"] == kind
    assert listing["counts"]["completed"] == 1
    assert await wired.folio_charges.count_documents({}) == await wired.payments.count_documents({}) == 0


@pytest.mark.parametrize("body", [{"booking_id": "foreign-booking"}, {"folio_id": "foreign-folio"}])
async def test_client_cannot_override_the_room_with_a_different_guest_account(wired, body):
    with pytest.raises(HTTPException) as exc:
        await ops.create_concierge_request({"type": "tour", "room_number": "105", **body}, USER, None)
    assert exc.value.status_code == 409
    assert await wired.concierge_requests.count_documents({}) == 0


async def test_cross_tenant_guest_and_folio_are_never_loaded(wired):
    await wired.guests.update_one({"id": "g"}, {"$set": {"tenant_id": "other"}})
    await wired.folios.update_one({"id": "f"}, {"$set": {"tenant_id": "other"}})
    result = await ops.concierge_active_room_lookup("105", USER)
    assert result["guest_name"] == "Eski isim" and result["folio_id"] == ""


async def test_ambiguous_folios_prevent_automatic_fee_selection_but_allow_verified_explicit_folio(wired):
    await wired.folios.insert_one({"id": "f2", "tenant_id": "t", "booking_id": "b", "status": "open"})
    body = {"type": "spa", "room_number": "105", "amount": "12.34", "charge_to_folio": True}
    with pytest.raises(HTTPException) as exc:
        await ops.create_concierge_request(body, USER, None)
    assert exc.value.status_code == 409
    created = await ops.create_concierge_request({**body, "folio_id": "f2"}, USER, None)
    assert created["folio_id"] == "f2" and created["amount"] == 12.34 and not created["folio_charge_id"]


@pytest.mark.parametrize("change", [{"amount": "NaN"}, {"amount": 1.001}, {"pax": True}, {"pax": 1.5}, {"booking_id": "wrong"}, {"folio_id": "wrong"}])
async def test_edit_rejects_invalid_money_party_or_guest_link_without_source_change(wired, change):
    created = await ops.create_concierge_request({"type": "tour", "room_number": "105"}, USER, None)
    before = await wired.concierge_requests.find_one({"_id": created["id"]})
    with pytest.raises(HTTPException) as exc:
        await ops.update_concierge_request(created["id"], change, USER, None)
    assert exc.value.status_code in {400, 409}
    assert await wired.concierge_requests.find_one({"_id": created["id"]}) == before


async def test_changed_room_rebinds_to_current_guest_and_drops_previous_account(wired):
    created = await ops.create_concierge_request({"type": "tour", "room_number": "105"}, USER, None)
    await wired.rooms.insert_one({"id": "r2", "tenant_id": "t", "room_number": "106"})
    await wired.bookings.insert_one({"id": "b2", "tenant_id": "t", "room_id": "r2", "guest_name": "Yeni misafir", "status": "checked_in"})
    await wired.folios.insert_one({"id": "f2", "tenant_id": "t", "booking_id": "b2", "status": "open"})
    changed = await ops.update_concierge_request(created["id"], {"room_number": "106"}, USER, None)
    assert (changed["guest_name"], changed["booking_id"], changed["folio_id"]) == ("Yeni misafir", "b2", "f2")


async def test_confirmed_and_cancelled_records_are_retained_in_total(wired):
    created = await ops.create_concierge_request({"type": "ticket", "room_number": "105"}, USER, None)
    await ops.update_concierge_request(created["id"], {"status": "confirmed"}, USER, None)
    listing = await ops.get_concierge_requests(status="pending", current_user=USER)
    assert listing["total"] == 0 and listing["counts"]["total"] == listing["counts"]["confirmed"] == 1
    await ops.update_concierge_request(created["id"], {"status": "cancelled"}, USER, None)
    listing = await ops.get_concierge_requests(current_user=USER)
    assert listing["total"] == listing["counts"]["cancelled"] == 1 and listing["requests"][0]["id"] == created["id"]
