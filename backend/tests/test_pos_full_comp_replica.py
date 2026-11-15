"""Full-comp room charges: real local sale/outbox/folio and report reconciliation."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import pos_folio_consumer
from domains.pms.pos_fnb.checkout_benefits import quote_checkout
from domains.pms.pos_router import pos_core
from tests import test_pos_final_consistency_replica as fixtures
from tests.test_pos_presentation_replica import menu_and_booking

ctx = fixtures.ctx
db = fixtures.db
service = fixtures.service

async def prepare(db, service, scope="full"):
    await menu_and_booking(db)
    await db.bookings.update_one({"id": "booking"}, {"$set": {
        "is_complimentary": True, "complimentary_scope": scope,
    }})
    made = await service.create_order(ctx(), "bar", items=[{"item_id": "tea", "quantity": 1}])
    oid = made.data["order_id"]
    await service.apply_order_adjustment(ctx(), oid, "discount", "percentage", 10, "İndirim")
    await service.apply_order_adjustment(ctx(), oid, "service_charge", "fixed", 5, "Servis")
    order = await db.pos_orders.find_one({"id": oid})
    quote = await quote_checkout(db, "t", order, {"post_to_folio": True, "booking_id": "booking"})
    return order, quote


async def test_full_comp_sale_folio_and_z_are_zero_and_replay_preserves_original(service, db, monkeypatch):
    order, quote = await prepare(db, service)
    assert quote["gross"] == 104
    assert quote["complimentary_discount"] == 104
    assert quote["payable"] == quote["tax_amount"] == 0
    args = {"payment_method": "room_charge", "post_to_folio": True, "booking_id": "booking",
            "checkout_options": {"quote_id": quote["quote_id"]}, "idempotency_key": "full-comp-room"}
    assert (await service.close_order(ctx(), order["id"], **args)).ok
    assert (await service.close_order(ctx(), order["id"], **args)).data["idempotent"]
    sale = await db.pos_transactions.find_one({})
    assert sale["gl_bridge_status"] == "folio_path"  # no second direct POS posting
    assert sale["amount"] == sale["total_amount"] == sale["tax_amount"] == sale["service_charge_amount"] == 0
    assert sale["discount_amount"] == 115  # prior 11 discount + remaining 104 comp
    assert sale["complimentary_original_amount"] == 104
    assert await db.pos_transactions.count_documents({}) == 1
    event = await db.outbox_events.find_one({"event_type": "pos.charge.posted.v1"})
    assert len(event["payload"]["charges"]) == 2  # item and service stay traceable
    assert sum(line["complimentary_original_amount"] for line in event["payload"]["charges"]) == 104
    assert all(line["is_complimentary"] and line["total"] == line["vat_amount"] == 0 for line in event["payload"]["charges"])
    monkeypatch.setattr(pos_folio_consumer, "get_system_db", lambda: db)
    for _ in range(2):
        assert (await pos_folio_consumer.handle_ic_pos_event(event))[0]
    assert await db.folio_charges.count_documents({}) == 2
    assert (await db.folios.find_one({"id": "folio"}))["balance"] == 0
    monkeypatch.setattr(pos_core, "db", db)
    z = await pos_core.get_z_report(date="2026-10-18", outlet_id=None, current_user=ctx())
    assert z["net_sales"] == 0


async def test_accommodation_only_does_not_comp_food(service, db, monkeypatch):
    order, quote = await prepare(db, service, "accommodation_only")
    assert not quote["is_complimentary"]
    assert quote["payable"] == 104
    monkeypatch.setattr("core.integrations.operational_gl_bridge.post_direct_pos_to_gl", AsyncMock())
    result = await service.close_order(ctx(), order["id"], "room_charge", post_to_folio=True,
        booking_id="booking", checkout_options={"quote_id": quote["quote_id"]})
    assert result.ok
    assert (await db.pos_transactions.find_one({}))["total_amount"] == 104
    event = await db.outbox_events.find_one({"event_type": "pos.charge.posted.v1"})
    assert sum(row["total"] for row in event["payload"]["charges"]) == 104


@pytest.mark.parametrize("change", ["scope", "status", "tenant", "booking", "cash", "mixed"])
async def test_stale_or_wrong_room_quote_writes_nothing(service, db, change):
    order, quote = await prepare(db, service)
    args = {"payment_method": "room_charge", "post_to_folio": True, "booking_id": "booking",
            "checkout_options": {"quote_id": quote["quote_id"]}}
    if change in {"scope", "status", "tenant"}:
        field, value = {"scope": ("complimentary_scope", "accommodation_only"),
                        "status": ("status", "checked_out"), "tenant": ("tenant_id", "other")}[change]
        await db.bookings.update_one({"id": "booking"}, {"$set": {field: value}})
    elif change == "booking":
        args["booking_id"] = "another"
    elif change == "cash":
        args.update(payment_method="cash", post_to_folio=False)
    else:
        args["payments"] = [{"method": "cash", "amount": 104}]
    if change in {"status", "tenant", "booking"}:
        result = await service.close_order(ctx(), order["id"], **args)
        assert not result.ok and result.code == "BOOKING_NOT_IN_HOUSE"
    else:
        with pytest.raises(HTTPException):
            await service.close_order(ctx(), order["id"], **args)
    assert await db.pos_transactions.count_documents({}) == 0
    assert await db.outbox_events.count_documents({"event_type": "pos.charge.posted.v1"}) == 0
    assert (await db.pos_orders.find_one({"id": order["id"]}))["payment_status"] == "unpaid"


async def test_comp_edit_between_quote_and_transaction_aborts_sale(service, db, monkeypatch):
    order, quote = await prepare(db, service)
    persist = service._persist_txn_and_intent
    async def race(*args, **kwargs):
        await db.bookings.update_one({"id": "booking"}, {"$set": {"is_complimentary": False}})
        return await persist(*args, **kwargs)
    monkeypatch.setattr(service, "_persist_txn_and_intent", race)
    with pytest.raises(HTTPException):
        await service.close_order(ctx(), order["id"], "room_charge", post_to_folio=True,
            booking_id="booking", checkout_options={"quote_id": quote["quote_id"]})
    assert await db.pos_transactions.count_documents({}) == 0
    assert await db.outbox_events.count_documents({"event_type": "pos.charge.posted.v1"}) == 0


@pytest.mark.parametrize("options", [{"tip_amount": 1}, {"coupon_code": "SAVE"}, {"loyalty_points": 10}])
async def test_full_comp_never_consumes_other_benefits(service, db, options):
    order, _ = await prepare(db, service)
    with pytest.raises(HTTPException):
        await quote_checkout(db, "t", order, {"post_to_folio": True, "booking_id": "booking", **options})
    assert await db.loyalty_pos_ledger.count_documents({}) == 0
    assert await db.pos_coupon_redemptions.count_documents({}) == 0


async def test_old_client_must_confirm_comp_quote_before_closing(service, db):
    order, _ = await prepare(db, service)
    with pytest.raises(HTTPException):
        await service.close_order(ctx(), order["id"], "room_charge", post_to_folio=True, booking_id="booking")
    assert await db.pos_transactions.count_documents({}) == 0
