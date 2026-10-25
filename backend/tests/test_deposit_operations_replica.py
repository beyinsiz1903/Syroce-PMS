"""Real local replica-set acceptance; no remote database or real payment."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from core import audit_chain
from core import database as core_database
from modules.pms_core import deposit_operations
from routers import reservation_detail as routes
from routers import webhook_retry_service

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(id="operator", name="Yetkili", role="manager", tenant_id="A")


@pytest.fixture(autouse=True)
async def wired(monkeypatch, ledger_db):
    for name in ("bookings", "folios", "deposits", "payments", "deposit_refunds", "deposit_operations",
                 "tenant_settings", "audit_logs", "audit_chain_state", "reservation_financial_locks"):
        await ledger_db.create_collection(name)
    await ledger_db.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-24"})
    await ledger_db.bookings.insert_one({"tenant_id": "A", "id": "b", "currency": "TRY", "status": "confirmed", "paid_amount": 0})
    await ledger_db.folios.insert_one({"tenant_id": "A", "booking_id": "b", "id": "f", "currency": "TRY", "status": "open"})
    monkeypatch.setattr(routes, "db", ledger_db)
    monkeypatch.setattr(core_database, "client", ledger_db.client)
    monkeypatch.setattr(audit_chain, "_system_db", lambda: ledger_db)
    monkeypatch.setattr(routes, "_enforce_perm", lambda *_: None)
    monkeypatch.setattr(routes, "_refresh_cached_folio_balance", AsyncMock())
    monkeypatch.setattr(routes, "_log_activity", AsyncMock())
    monkeypatch.setattr(routes, "claim_short_window_dedup", AsyncMock(return_value={"status": "acquired", "lock_id": "local-test"}))
    monkeypatch.setattr(routes, "release_idempotency", AsyncMock())
    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", MagicMock())
    return ledger_db


def receipt(**extra):
    return routes.DepositRecord(request_id=uuid4(), amount=100, method="cash", reference="Harici tahsilat kaydı", **extra)


def refund(deposit_id, amount=100, request_id=None):
    return routes.DepositRefund(request_id=request_id or uuid4(), deposit_id=deposit_id,
        refund_amount=amount, refund_method="cash", reason="Harici iade belgesi incelendi")


async def receive(body=None):
    return await routes.record_deposit("b", body or receipt(), USER)


async def repay(body):
    return await routes.refund_deposit("b", body, USER)


async def test_receipt_and_full_refund_are_durable_after_response_loss_and_state_change(wired):
    body = receipt()
    first = await receive(body)
    replay = await receive(body)
    assert replay["replayed"] and replay["payment"]["id"] == first["payment"]["id"]
    data = refund(first["deposit"]["id"])
    result = await repay(data)
    assert result["remaining_amount"] == 0 and result["payment"]["amount"] == -100
    await wired.bookings.update_one({"id": "b"}, {"$set": {"status": "checked_out"}})
    assert (await repay(data))["replayed"]
    assert await wired.payments.count_documents({}) == 2
    assert await wired.deposit_operations.count_documents({}) == 2
    assert (await wired.bookings.find_one({"id": "b"}))["paid_amount"] == 0
    entries = await wired.audit_logs.find({}).to_list(None)
    assert len(entries) == 2
    for entry in entries:
        assert entry["record_hash"] == audit_chain.compute_record_hash(entry, entry["seq"], entry["prev_hash"])
        assert entry["actor_id"] == USER.id and entry["after_snapshot"]["business_date"] == "2026-10-24"


async def test_concurrent_same_receipt_commits_one_payment_even_without_precreated_lock_index(wired):
    body = receipt()
    results = await asyncio.gather(receive(body), receive(body))
    assert results[0]["payment"]["id"] == results[1]["payment"]["id"]
    assert await wired.payments.count_documents({}) == 1
    assert (await wired.bookings.find_one({"id": "b"}))["paid_amount"] == 100


async def test_changed_payload_same_identity_is_conflict_not_another_deposit(wired):
    body = receipt()
    await receive(body)
    with pytest.raises(HTTPException) as error:
        await receive(body.model_copy(update={"amount": 101}))
    assert error.value.status_code == 409 and await wired.payments.count_documents({}) == 1


@pytest.mark.parametrize("failure", ["audit", "receipt"])
async def test_failure_rolls_back_deposit_payment_counter_refund_and_audit(wired, monkeypatch, failure):
    first = await receive()
    before = await wired.bookings.find_one({"id": "b"})
    if failure == "audit":
        monkeypatch.setattr(deposit_operations, "append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    else:
        original = routes._remember_deposit
        async def fail(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("lost before commit")
        monkeypatch.setattr(routes, "_remember_deposit", fail)
    with pytest.raises(RuntimeError):
        await repay(refund(first["deposit"]["id"]))
    assert await wired.bookings.find_one({"id": "b"}) == before
    assert (await wired.deposits.find_one({}))["status"] == "received"
    assert await wired.payments.count_documents({}) == 1
    assert await wired.deposit_refunds.count_documents({}) == 0
    assert await wired.deposit_operations.count_documents({}) == 1
    assert await wired.audit_logs.count_documents({}) == 1


async def test_receipt_audit_failure_rolls_back_all_three_writes(wired, monkeypatch):
    monkeypatch.setattr(deposit_operations, "append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError):
        await receive()
    for name in ("deposits", "payments", "deposit_operations", "audit_logs"):
        assert await wired[name].count_documents({}) == 0
    assert (await wired.bookings.find_one({"id": "b"}))["paid_amount"] == 0


async def test_concurrent_refunds_cannot_exceed_deposit_and_partial_refunds_accumulate(wired):
    first = await receive()
    data = refund(first["deposit"]["id"], 60)
    results = await asyncio.gather(repay(data), repay(refund(first["deposit"]["id"], 60)), return_exceptions=True)
    assert sum(isinstance(r, HTTPException) for r in results) == 1
    assert (await wired.deposits.find_one({}))["refunded_amount"] == 60
    final = await repay(refund(first["deposit"]["id"], 40))
    assert final["remaining_amount"] == 0 and await wired.payments.count_documents({}) == 3


async def test_tenant_and_multiple_folio_targets_are_not_silently_selected(wired):
    foreign = SimpleNamespace(**{**vars(USER), "tenant_id": "B"})
    with pytest.raises(HTTPException) as error:
        await routes.record_deposit("b", receipt(), foreign)
    assert error.value.status_code == 404
    await wired.folios.insert_one({"tenant_id": "A", "booking_id": "b", "id": "company", "currency": "TRY", "status": "open"})
    with pytest.raises(HTTPException) as error:
        await receive()
    assert error.value.status_code == 409 and await wired.payments.count_documents({}) == 0
    assert (await receive(receipt(folio_id="company")))["payment"]["folio_id"] == "company"


@pytest.mark.parametrize("method", ["online", "city_ledger", "comp", "wallet"])
async def test_unsupported_method_cannot_be_marked_as_real_collection(wired, method):
    with pytest.raises(HTTPException) as error:
        await receive(receipt().model_copy(update={"method": method}))
    assert error.value.status_code == 422 and await wired.payments.count_documents({}) == 0


async def test_missing_nonce_fractional_cent_and_wrong_original_folio_fail_closed(wired):
    for body in (receipt().model_copy(update={"request_id": None}), receipt().model_copy(update={"amount": 1.001})):
        with pytest.raises(HTTPException) as error:
            await receive(body)
        assert error.value.status_code == 422
    first = await receive()
    await wired.folios.update_one({"id": "f"}, {"$set": {"booking_id": "other-booking"}})
    with pytest.raises(HTTPException) as error:
        await repay(refund(first["deposit"]["id"]))
    assert error.value.status_code == 409 and await wired.deposit_refunds.count_documents({}) == 0


async def test_post_commit_refresh_failure_does_not_report_a_failed_payment(wired, monkeypatch):
    monkeypatch.setattr(routes, "_refresh_cached_folio_balance", AsyncMock(side_effect=RuntimeError("cache")))
    result = await receive()
    assert result["success"] and await wired.payments.count_documents({}) == 1


async def test_replay_retries_failed_projection_without_another_payment(wired, monkeypatch):
    body = receipt()
    projection = AsyncMock(side_effect=RuntimeError("cache"))
    monkeypatch.setattr(routes, "_refresh_cached_folio_balance", projection)
    await receive(body)
    projection.side_effect = None
    assert (await receive(body))["replayed"]
    assert projection.await_count == 2 and await wired.payments.count_documents({}) == 1


async def test_legacy_missing_folio_cannot_refund_to_arbitrary_split_window(wired):
    result = await receive()
    await wired.deposits.update_one({"id": result["deposit"]["id"]}, {"$unset": {"folio_id": ""}})
    await wired.folios.insert_one({"tenant_id": "A", "booking_id": "b", "id": "company", "currency": "TRY", "status": "open"})
    with pytest.raises(HTTPException) as error:
        await repay(refund(result["deposit"]["id"]))
    assert error.value.status_code == 409 and await wired.deposit_refunds.count_documents({}) == 0


async def test_unknown_currency_does_not_silently_become_try(wired):
    await wired.bookings.update_one({"id": "b"}, {"$unset": {"currency": ""}})
    await wired.folios.update_one({"id": "f"}, {"$unset": {"currency": ""}})
    with pytest.raises(HTTPException) as error:
        await receive()
    assert error.value.status_code == 409 and await wired.payments.count_documents({}) == 0


@pytest.mark.parametrize("action", ["receive", "refund"])
async def test_transactions_unavailable_never_fall_back_to_partial_writes(wired, monkeypatch, action):
    from pymongo.errors import OperationFailure

    first = await receive() if action == "refund" else None
    monkeypatch.setattr(routes, "_run_reservation_financial_transaction", AsyncMock(
        side_effect=OperationFailure("Transaction numbers are only allowed on a replica set")))
    with pytest.raises(HTTPException) as error:
        if action == "receive":
            await receive()
        else:
            await repay(refund(first["deposit"]["id"]))
    assert error.value.status_code == 503
    assert await wired.payments.count_documents({}) == (1 if first else 0)
    assert await wired.deposit_refunds.count_documents({}) == 0


@pytest.mark.parametrize("currency,method", [("TRY", "cash"), ("USD", "card"), ("EUR", "bank_transfer")])
async def test_native_receipt_refund_currency_is_never_converted_implicitly(wired, currency, method):
    await wired.bookings.update_one({"id": "b"}, {"$set": {"currency": currency}})
    await wired.folios.update_one({"id": "f"}, {"$set": {"currency": currency}})
    body = receipt().model_copy(update={"method": method})
    result = await receive(body)
    data = refund(result["deposit"]["id"], 25).model_copy(update={"refund_method": method})
    returned = await repay(data)
    assert result["payment"]["currency"] == returned["payment"]["currency"] == currency
    assert returned["payment"]["amount"] == -25 and returned["remaining_amount"] == 75


@pytest.mark.parametrize("changes", [{"amount": "NaN"}, {"amount": -100}, {"refunded_amount": 101}, {"amount": 100.001}])
async def test_invalid_legacy_source_balance_never_creates_refund(wired, changes):
    result = await receive()
    await wired.deposits.update_one({"id": result["deposit"]["id"]}, {"$set": changes})
    with pytest.raises(HTTPException) as error:
        await repay(refund(result["deposit"]["id"], 1))
    assert error.value.status_code == 409 and await wired.deposit_refunds.count_documents({}) == 0
