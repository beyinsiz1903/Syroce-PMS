"""Legacy booking extras must retain the same debt in every settlement flow."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from domains.pms import cashier_service
from modules.pms_core import enterprise_billing as billing
from modules.pms_core import security_funds
from modules.pms_core import settlement_instruments as s
from modules.pms_core.folio_selection import ensure_folio_transfer_amount
from modules.pms_core.reporting_financials import effective_collection
from tests.test_settlement_instruments import application, apply, atomic, funded_issue, reverse
from tests.test_settlement_instruments import store as isolated_store

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
store = isolated_store


@pytest.mark.parametrize("kind", ["gift_card_redemption", "wallet"])
async def test_partial_funded_settlements_include_booking_extra_and_reverse_each_source(store, kind):
    db = store
    await db.folio_charges.delete_many({"tenant_id": "A"})
    await db.extra_charges.insert_one({"tenant_id": "A", "id": "extra", "booking_id": "b", "folio_id": "f",
        "currency": "TRY", "amount": 120, "total": 120, "quantity": 1, "vat_amount": 20, "tax_amount": 0})
    item, _, _ = await funded_issue(db, kind, amount=5000, base=5000)
    first = await apply(db, item, application(amount_minor=1000))
    second = await apply(db, item, application(amount_minor=2000))
    assert (await db.folios.find_one({"id": "f"}))["balance"] == 90
    assert (await db.billing_instruments.find_one({"id": item["id"]}))["remaining_minor"] == 2000
    for result, expected in ((first, 100), (second, 120)):
        back = s.Reverse(request_id=uuid4(), booking_id="b", reference=str(uuid4()), reason="Kısmi kullanımın özgün ters kaydı")
        await reverse(db, result, back)
        assert (await db.folios.find_one({"id": "f"}))["balance"] == expected
    assert (await db.billing_instruments.find_one({"id": item["id"]}))["remaining_minor"] == 5000
    assert (await s.reconcile(db, "A"))["healthy"]
    assert all(effective_collection(row) == 0 for row in await db.payments.find({}).to_list(None))


async def test_unbound_extra_with_two_windows_cannot_fund_a_settlement(store):
    db = store
    await db.folio_charges.delete_many({"tenant_id": "A"})
    await db.folios.insert_one({"tenant_id": "A", "id": "f2", "booking_id": "b", "status": "open", "currency": "TRY"})
    await db.extra_charges.insert_one({"tenant_id": "A", "id": "extra", "booking_id": "b", "currency": "TRY", "amount": 120, "total": 120})
    item, _, _ = await funded_issue(db, "wallet", amount=5000, base=5000)
    with pytest.raises(HTTPException) as error:
        await apply(db, item, application(amount_minor=1000))
    assert error.value.status_code == 409
    assert await db.payments.count_documents({}) == 0
    assert (await db.billing_instruments.find_one({"id": item["id"]}))["remaining_minor"] == 5000


async def extra_only(db):
    await db.folio_charges.delete_many({"tenant_id": "A"})
    await db.extra_charges.insert_one({"tenant_id": "A", "id": "extra", "booking_id": "b", "folio_id": "f",
        "currency": "TRY", "amount": 120, "total": 120, "quantity": 1, "vat_amount": 20,
        "tax_amount": 0, "category": "minibar"})


async def test_security_application_recognizes_extra_debt_without_new_collection(store):
    db = store
    await extra_only(db)
    receipt = security_funds.Receipt(request_id=uuid4(), booking_id="b", amount_minor=5000, currency="TRY",
        method="bank_transfer", reference="Synthetic source", reason="Isolated existing deposit")
    cash = cashier_service.record_cash_transaction
    fund = await atomic(db, lambda session: security_funds.receive(db, "A", "finance", receipt, session=session, record_cash=cash))
    move = security_funds.Movement(request_id=uuid4(), action="apply", amount_minor=1000, folio_id="f",
        reference="Extra deposit application", reason="Use existing deposit against extra")
    await atomic(db, lambda session: security_funds.move(db, "A", "finance", fund["id"], move, session=session, record_cash=cash))
    assert (await db.folios.find_one({"id": "f"}))["balance"] == 110
    assert await db.cashier_transactions.count_documents({}) == 0


async def test_concession_applies_only_selected_extra_and_projects_remaining_debt(store):
    db = store
    await extra_only(db)
    body = billing.ConcessionRequest(request_id=uuid4(), booking_id="b", folio_id="f",
        kind="discount", mode="amount", amount_minor=2000, charge_ids=["extra"], reason="Partial selected-extra concession")
    result = await atomic(db, lambda session: billing.request_concession(db, "A", "finance", body, session=session))
    assert result["status"] == "applied"
    assert (await db.folios.find_one({"id": "f"}))["balance"] == 100
    assert await db.payments.count_documents({}) == 1
    assert effective_collection(await db.payments.find_one({})) == 0


async def test_cari_transfer_guard_uses_extra_debt_and_still_rejects_overpayment(store):
    db = store
    await extra_only(db)
    folio = await db.folios.find_one({"id": "f"})
    await atomic(db, lambda session: ensure_folio_transfer_amount(db, "A", folio, 120, "TRY", session=session))
    with pytest.raises(HTTPException):
        await atomic(db, lambda session: ensure_folio_transfer_amount(db, "A", folio, 120.01, "TRY", session=session))
    assert await db.payments.count_documents({}) == 0
