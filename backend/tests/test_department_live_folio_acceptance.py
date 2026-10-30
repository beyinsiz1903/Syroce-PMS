"""Regressions from Demo Hotel service -> folio acceptance; LOCAL replica only."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.pms import operations_router as concierge
from domains.pms import transfer_parking_router as transport
from domains.pms.folio.repositories.folio_repository import FolioRepository
from routers import mice
from shared_kernel import audit_helper
from tests.test_pos_final_consistency_replica import db  # noqa: F401


def actor():
    return SimpleNamespace(id="manager", tenant_id="t", name="QA Manager", email="qa@example.invalid", username="qa", role="admin", is_super_admin=False)


@pytest_asyncio.fixture
async def wired(db, monkeypatch):  # noqa: F811
    for name in (
        "bookings",
        "folios",
        "folio_charges",
        "folio_postings",
        "payments",
        "concierge_requests",
        "mice_events",
        "audit_logs",
        "audit_chain_state",
        "transport_resources",
        "transport_bookings",
        "transport_late_charges",
        "transport_slot_locks",
        "idempotency_keys",
    ):
        await db.create_collection(name)
    await db.tenant_settings.update_one({"tenant_id": "t"}, {"$set": {"business_date": "2026-10-26"}})
    await db.bookings.insert_one({"id": "b", "tenant_id": "t", "status": "checked_in", "currency": "TRY"})
    await db.folios.insert_one({"id": "actual-folio", "booking_id": "b", "tenant_id": "t", "status": "open", "currency": "TRY", "balance": 0})
    await db.concierge_requests.insert_one(
        {
            "_id": "c",
            "tenant_id": "t",
            "status": "in_progress",
            "booking_id": "b",
            "folio_id": "actual-folio",
            "amount": 600,
            "currency": "TRY",
            "type": "tour",
            "details": "QA tour",
            "date": "2026-10-30",
            "time": "15:00",
            "charge_to_folio": True,
            "notes": "QA retained source",
            "folio_charge_id": "",
        }
    )
    await db.mice_events.insert_one(
        {
            "id": "m",
            "tenant_id": "t",
            "status": "completed",
            "name": "QA workshop",
            "reservation_id": "b",
            "currency": "TRY",
            "start_date": "2026-10-30",
            "end_date": "2026-10-30",
            "totals": {"grand_total": 1368, "net_total": 1140, "service_total": 0, "tax_total": 228},
            "notes": "QA retained source",
        }
    )
    monkeypatch.setattr(concierge, "db", db)
    monkeypatch.setattr(FolioRepository, "collection", db.folios)
    monkeypatch.setattr(mice, "get_system_db", lambda: db)
    monkeypatch.setattr(mice, "_tenant_currency_code", AsyncMock(return_value="TRY"))
    monkeypatch.setattr(transport, "db", db)
    monkeypatch.setattr(transport, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(transport, "get_tenant_limit", AsyncMock(return_value=None))
    monkeypatch.setattr(audit_helper, "db", db)
    monkeypatch.setattr("core.audit_chain._system_db", lambda: db)
    from integrations.xchange.bus import bus

    monkeypatch.setattr(bus, "publish", AsyncMock())
    return db


async def finish_concierge():
    return await concierge.update_concierge_request("c", {"status": "completed"}, actor(), None)


async def test_concierge_completion_is_canonical_receivable_not_embedded_only(wired):
    await finish_concierge()
    charge = await wired.folio_charges.find_one({"source_concierge_request_id": "c"})
    assert charge and charge["total"] == 600
    assert charge["booking_id"] == "b" and charge["folio_id"] == "actual-folio"
    assert charge["business_date"] == "2026-10-26" and charge["service_date"] == "2026-10-30"
    assert charge["service_time"] == "15:00" and charge["charge_category"] == "concierge"
    assert (await wired.folios.find_one({"id": "actual-folio"}))["balance"] == 600
    audit = await wired.audit_logs.find_one({"action": "concierge_charge_posted"})
    assert audit["actor_id"] == "manager" and audit.get("record_hash")


async def test_mice_completion_posts_real_folio_and_exact_declared_tax(wired):
    event = await wired.mice_events.find_one({"id": "m"})
    await mice._post_event_to_folio("t", event)
    charge = await wired.folio_charges.find_one({"source_mice_event_id": "m"})
    assert charge and (charge["amount"], charge["vat_amount"], charge["total"]) == (1140, 228, 1368)
    assert charge["folio_id"] == "actual-folio" and charge["business_date"] == "2026-10-26"
    assert (await wired.folios.find_one({"id": "actual-folio"}))["balance"] == 1368
    posting = await wired.folio_postings.find_one({"source": "mice_module"})
    assert posting["folio_id"] == "actual-folio" and posting["folio_charge_id"] == charge["id"]
    actuals = await mice.get_event_actuals("m", actor(), None)
    assert actuals["report"]["posted_net_revenue"] == 1140
    assert actuals["report"]["revenue_source"] == "folio_charges"


async def test_concierge_concurrent_replay_posts_once(wired):
    await asyncio.gather(finish_concierge(), finish_concierge())
    await finish_concierge()
    assert await wired.folio_charges.count_documents({"source_concierge_request_id": "c"}) == 1
    assert (await wired.folios.find_one({"id": "actual-folio"}))["balance"] == 600
    assert await wired.audit_logs.count_documents({"action": "concierge_charge_posted"}) == 1


@pytest.mark.parametrize("field,value", [("currency", "EUR"), ("status", "checked_out"), ("tenant_id", "other")])
async def test_concierge_rejects_invalid_booking_without_completing(wired, field, value):
    await wired.bookings.update_one({"id": "b"}, {"$set": {field: value}})
    with pytest.raises(HTTPException):
        await finish_concierge()
    assert not await wired.folio_charges.count_documents({})
    assert (await wired.concierge_requests.find_one({"_id": "c"}))["status"] == "in_progress"


async def test_transport_unlimited_quota_does_not_call_bounded_counter(monkeypatch):
    monkeypatch.setattr(transport, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(transport, "get_tenant_limit", AsyncMock(return_value=None))
    monkeypatch.setattr(transport, "get_idempotency_key", lambda request: None)
    reserve = AsyncMock(side_effect=AssertionError("Unlimited quota must not enter numeric bounded reserve"))
    monkeypatch.setattr(transport, "reserve_quota", reserve)
    monkeypatch.setattr(transport, "db", SimpleNamespace(transport_resources=SimpleNamespace(insert_one=AsyncMock())))
    response = await transport.create_resource(SimpleNamespace(), transport.ResourceIn(name="QA transfer", kind="transfer_vehicle", price=850), actor())
    assert response["resource"]["price"] == 850
    reserve.assert_not_awaited()


async def test_transport_resource_real_idempotency_contract_and_payload_mismatch(wired, monkeypatch):
    from starlette.requests import Request

    request = Request({"type": "http", "headers": [(b"idempotency-key", b"resource-qa")]})
    payload = transport.ResourceIn(name="QA transfer", kind="transfer_vehicle", price=850)
    reserve = AsyncMock(side_effect=AssertionError("unlimited must not reserve"))
    monkeypatch.setattr(transport, "reserve_quota", reserve)
    # Deliberately exercise degraded response caching too: durable resource
    # identity must still prevent a duplicate after a success response is lost.
    monkeypatch.setattr("shared_kernel.idempotency.seal_response_body", lambda value: {})
    first = await transport.create_resource(request, payload, actor())
    second = await transport.create_resource(request, payload, actor())
    assert first == second
    assert await wired.transport_resources.count_documents({}) == 1
    with pytest.raises(HTTPException) as error:
        await transport.create_resource(request, payload.model_copy(update={"price": 900}), actor())
    assert error.value.status_code == 409
    reserve.assert_not_awaited()
    # Even after TTL removes the cache, the stable source is authoritative.
    await wired.idempotency_keys.delete_many({})
    assert await transport.create_resource(request, payload, actor()) == first
    assert await wired.transport_resources.count_documents({}) == 1


async def test_concierge_legacy_embedded_source_is_retained_and_reconciled_once(wired):
    legacy = {"id": "old-embedded", "concierge_request_id": "c", "amount": 600, "currency": "TRY"}
    await wired.folios.update_one({"id": "actual-folio"}, {"$set": {"charges": [legacy], "balance": 600}})
    await wired.concierge_requests.update_one({"_id": "c"}, {"$set": {"status": "completed", "folio_charge_id": "old-embedded"}})
    await finish_concierge()
    await finish_concierge()
    folio = await wired.folios.find_one({"id": "actual-folio"})
    assert folio["charges"] == [legacy] and folio["balance"] == 600
    assert await wired.folio_charges.count_documents({}) == 1
    audit = await wired.audit_logs.find_one({"action": "concierge_charge_posted"})
    assert "old-embedded" in str(audit)


async def test_mice_legacy_stub_is_reconciled_not_duplicated(wired):
    await wired.folio_postings.insert_one(
        {"id": "legacy-posting", "tenant_id": "t", "source": "mice_module", "reference": "m", "posting_type": "CHARGE", "reservation_id": "b", "folio_id": "b", "amount": 1368, "currency": "TRY"}
    )
    event = await wired.mice_events.find_one({"id": "m"})
    await mice._post_event_to_folio("t", event, "manager")
    await mice._post_event_to_folio("t", event, "manager")
    posting = await wired.folio_postings.find_one({"id": "legacy-posting"})
    assert posting["folio_id"] == "actual-folio" and posting["amount"] == 1368
    assert await wired.folio_postings.count_documents({}) == 1
    assert await wired.folio_charges.count_documents({}) == 1
    assert await wired.audit_logs.count_documents({"action": "mice_charge_posted"}) == 1


@pytest.mark.parametrize("kind", ["concierge", "mice"])
async def test_legacy_source_amount_conflict_rolls_back_charge(wired, kind):
    if kind == "concierge":
        await wired.folios.update_one({"id": "actual-folio"}, {"$set": {"charges": [{"concierge_request_id": "c", "amount": 999, "currency": "TRY"}]}})
        call = finish_concierge
    else:
        await wired.folio_postings.insert_one({"tenant_id": "t", "source": "mice_module", "reference": "m", "posting_type": "CHARGE", "reservation_id": "b", "amount": 999, "currency": "TRY"})

        async def call():
            await mice._post_event_to_folio("t", await wired.mice_events.find_one({"id": "m"}))

    with pytest.raises(HTTPException):
        await call()
    assert await wired.folio_charges.count_documents({}) == 0
    assert (await wired.folios.find_one({"id": "actual-folio"}))["balance"] == 0


async def test_audit_failure_rolls_back_concierge_completion_and_money(wired, monkeypatch):
    monkeypatch.setattr("core.department_folio.append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError):
        await finish_concierge()
    assert not await wired.folio_charges.count_documents({})
    assert (await wired.folios.find_one({"id": "actual-folio"}))["balance"] == 0
    assert (await wired.concierge_requests.find_one({"_id": "c"}))["status"] == "in_progress"


async def test_mice_status_and_receivable_are_one_transaction(wired, monkeypatch):
    await wired.mice_events.update_one({"id": "m"}, {"$set": {"status": "confirmed"}})
    monkeypatch.setattr(mice, "_ensure_indexes", AsyncMock())
    monkeypatch.setattr(mice, "release_quota", AsyncMock())
    monkeypatch.setattr(mice, "log_audit_event", AsyncMock())
    monkeypatch.setattr("core.department_folio.append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError):
        await mice.change_status("m", mice.StatusUpdate(status="completed"), actor(), None)
    assert (await wired.mice_events.find_one({"id": "m"}))["status"] == "confirmed"
    assert not await wired.folio_charges.count_documents({})


@pytest.mark.parametrize("kind,price", [("transfer_vehicle", 850), ("parking_spot", 150)])
async def test_transport_is_source_owned_current_day_receivable_with_audit(wired, kind, price):
    doc = {
        "id": "trip",
        "tenant_id": "t",
        "booking_id": "b",
        "folio_id": "actual-folio",
        "currency": "TRY",
        "kind": kind,
        "resource_name": "QA vehicle/spot",
        "total": price,
        "schedule": {"pickup_at": "2026-10-30T17:30:00+03:00"} if kind == "transfer_vehicle" else {"start_date": "2026-10-30"},
        "note": "QA retained service",
    }
    posted = await transport._post_booking_to_folio("t", "manager", doc)
    assert posted["charged"]
    await transport._post_booking_to_folio("t", "manager", doc)
    charge = await wired.folio_charges.find_one({"source_transport_booking_id": "trip"})
    assert charge["total"] == price and charge["business_date"] == "2026-10-26"
    assert charge["service_date"] == "2026-10-30" and charge["vat_amount"] is None
    assert (await wired.folios.find_one({"id": "actual-folio"}))["balance"] == price
    assert await wired.folio_charges.count_documents({}) == 1
    assert await wired.audit_logs.count_documents({"action": charge["charge_category"] + "_charge_posted"}) == 1


@pytest.mark.parametrize("case", ["closed", "multiple", "foreign", "source_changed", "voided"])
async def test_concierge_target_and_source_guards_never_duplicate_debt(wired, case):
    if case == "closed":
        await wired.folios.update_one({"id": "actual-folio"}, {"$set": {"status": "closed"}})
    elif case == "multiple":
        await wired.concierge_requests.update_one({"_id": "c"}, {"$unset": {"folio_id": ""}})
        await wired.folios.insert_one({"id": "second", "booking_id": "b", "tenant_id": "t", "status": "open", "currency": "TRY"})
    elif case == "foreign":
        await wired.folios.update_one({"id": "actual-folio"}, {"$set": {"tenant_id": "other"}})
    else:
        await finish_concierge()
        if case == "source_changed":
            await wired.concierge_requests.update_one({"_id": "c"}, {"$set": {"amount": 900}})
        else:
            await wired.folio_charges.update_one({"source_concierge_request_id": "c"}, {"$set": {"voided": True}})
    before = await wired.folio_charges.count_documents({})
    with pytest.raises(HTTPException):
        await finish_concierge()
    assert await wired.folio_charges.count_documents({}) == before


async def test_all_department_receivables_reconcile_in_open_day_report(wired):
    from routers.reports_pkg.standard_reports import _posted_revenue_rows
    from datetime import date

    await finish_concierge()
    await mice._post_event_to_folio("t", await wired.mice_events.find_one({"id": "m"}), "manager")
    rows = await _posted_revenue_rows("t", date(2026, 10, 26), date(2026, 10, 26), database=wired)
    assert sum(row["total"] for row in rows) == 1968
    from modules.pms_core.revenue_report import charge_breakdown
    assert {charge_breakdown(row)["category"] for row in rows} == {"concierge", "mice"}
    assert not await _posted_revenue_rows("t", date(2026, 10, 30), date(2026, 10, 30), database=wired)


async def test_paid_concierge_requires_finance_authority(wired):
    user = actor()
    user.role = "staff"
    with pytest.raises(HTTPException) as error:
        await concierge.update_concierge_request("c", {"status": "completed"}, user, None)
    assert error.value.status_code == 403
    assert not await wired.folio_charges.count_documents({})


async def test_closed_business_day_refuses_new_department_charge(wired):
    await wired.night_audit_runs.insert_one({"tenant_id": "t", "business_date": "2026-10-26", "status": "completed"})
    with pytest.raises(HTTPException) as error:
        await finish_concierge()
    assert error.value.status_code == 409
    assert not await wired.folio_charges.count_documents({})
