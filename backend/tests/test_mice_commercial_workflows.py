"""Commercial contracts on isolated, real Mongo; no provider or live data."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.mice_integrity import price_breakdown
from routers import mice
from tests.test_mice_mongo_acceptance import USER, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


@pytest.mark.parametrize("policy,expected", [
    ({}, (100, 0, 0, 100)),
    ({"discount_percent": 10, "service_percent": 10, "tax_percent": 20}, (90, 9, 19.8, 118.8)),
    ({"discount_percent": 10, "service_percent": 10, "tax_percent": 20, "tax_on_service": False}, (90, 9, 18, 117)),
    ({"discount_percent": 100, "service_percent": 100, "tax_percent": 100}, (0, 0, 0, 0)),
])
def test_price_order_and_cent_reconciliation(policy, expected):
    result = price_breakdown(100, policy)
    assert tuple(result[k] for k in ("net_total", "service_total", "tax_total", "grand_total")) == expected
    assert round(result["net_total"] + result["service_total"] + result["tax_total"], 2) == result["grand_total"]


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), 101])
def test_invalid_percentage_is_never_a_quote(value):
    with pytest.raises(ValueError): price_breakdown(100, {"tax_percent": value})


async def event(db, **extras):
    value = {"id": "event", "tenant_id": "A", "name": "Synthetic conference", "client_name": "Synthetic customer",
             "currency": "TRY", "status": "definite", "created_at": "2026-10-21T10:00:00+00:00", "expected_pax": 20,
             "totals": {"grand_total": 120, "tax_total": 20}, "space_bookings": [], "resources": [], **extras}
    await db.mice_events.insert_one(value)
    return value


@pytest.mark.asyncio
async def test_document_snapshot_is_immutable_and_issue_is_idempotent(wired):  # noqa: F811
    original = await event(wired)
    body = mice.DocumentIssueIn(reason="Offer issued", client_request_id="request-123", expected_revision=original["created_at"])
    result = await mice.issue_beo_document("event", body, USER)
    # A retry with the original revision must replay the existing document.
    replay = await mice.issue_beo_document("event", body, USER)
    assert result["id"] == replay["id"]
    await wired.mice_events.update_one({"id": "event", "tenant_id": "A"}, {"$set": {"totals.grand_total": 999}})
    document = (await wired.mice_events.find_one({"id": "event", "tenant_id": "A"}))["document_history"][0]
    assert document["snapshot"]["event"]["totals"]["grand_total"] == 120
    assert len((await mice.list_beo_documents("event", USER))["documents"]) == 1
    assert "snapshot" not in (await mice.list_beo_documents("event", USER))["documents"][0]


@pytest.mark.asyncio
async def test_stale_document_issue_and_cross_tenant_pdf_fail_closed(wired):  # noqa: F811
    await event(wired)
    with pytest.raises(HTTPException) as stale:
        await mice.issue_beo_document("event", mice.DocumentIssueIn(reason="Offer issued", client_request_id="request-123", expected_revision="stale"), USER)
    assert stale.value.status_code == 409
    await wired.mice_events.insert_one({"tenant_id": "B", "id": "secret", "document_history": [{"id": "private-doc"}]})
    with pytest.raises(HTTPException) as forbidden: await mice.beo_document_pdf("secret", "private-doc", USER)
    assert forbidden.value.status_code == 404


@pytest.mark.asyncio
async def test_parallel_documents_from_same_revision_have_one_winner(wired):  # noqa: F811
    original = await event(wired)
    outcomes = await asyncio.gather(*[mice._store_document(original, USER, "Issued concurrently", f"request-{i}") for i in range(2)], return_exceptions=True)
    assert sum(isinstance(o, dict) for o in outcomes) == 1
    assert sum(isinstance(o, HTTPException) and o.status_code == 409 for o in outcomes) == 1


@pytest.mark.asyncio
async def test_approval_uses_frozen_document_and_amendment_archives_signature(wired):  # noqa: F811
    await event(wired)
    request = await mice.create_beo_signature_request("event", mice.SignatureRequestIn(client_email="example@example.com"), USER)
    approved = await mice.verify_public_beo(request["token"])
    assert approved["document"]["number"] == 1
    saved = await wired.mice_events.find_one({"id": "event", "tenant_id": "A"})
    signature = {"name": "Synthetic client", "document_id": saved["active_document_id"], "signed_at": "2026-10-21T11:00:00+00:00"}
    await wired.mice_events.update_one({"id": "event", "tenant_id": "A"}, {"$set": {"signature": signature, "status": "confirmed"}})
    await mice.begin_beo_amendment("event", mice.AmendmentIn(reason="Customer changed service time", expected_revision=saved["updated_at"]), USER)
    amended = await wired.mice_events.find_one({"id": "event", "tenant_id": "A"})
    assert amended["status"] == "definite"
    assert amended["signature"] is None and amended["signature_request"] is None
    assert amended["document_history"][0]["signature"] == signature
    with pytest.raises(HTTPException): await mice.verify_public_beo(request["token"])


@pytest.mark.asyncio
async def test_actuals_are_not_revenue_or_cash_and_stale_save_is_rejected(wired):  # noqa: F811
    original = await event(wired)
    before = await mice.get_event_actuals("event", USER)
    assert before["report"]["actual_cost"] is None
    body = mice.EventActualsIn(actual_pax=18, guaranteed_pax=20, budget_cost=30,
                              costs=[{"name": "Consumed meals", "category": "food", "quantity": 18, "unit_cost": 2.5}], expected_revision=original["created_at"])
    await mice.save_event_actuals("event", body, USER)
    report = await mice.get_event_actuals("event", USER)
    assert report["report"]["quoted_net_revenue"] == 100
    assert report["report"]["actual_cost"] == 45
    assert report["report"]["quote_based_contribution"] == 55
    with pytest.raises(HTTPException) as stale: await mice.save_event_actuals("event", body, USER)
    assert stale.value.status_code == 409
    public_read = await mice.get_event("event", USER)
    assert "actuals" not in public_read
    assert public_read["totals"]["grand_total"] == 120
    assert await wired.folio_payments.count_documents({}) == 0


@pytest.mark.asyncio
async def test_gl_splits_tax_and_prevents_duplicate_recognition_on_linked_reservation(wired, monkeypatch):  # noqa: F811
    await event(wired)
    journal = AsyncMock(return_value={"id": "synthetic-journal"})
    monkeypatch.setattr(mice, "post_journal_entry", journal)
    await mice.post_beo_to_folio("event", None, USER)
    lines = journal.await_args.kwargs["lines"]
    assert [(l["account_code"], l.get("debit", 0), l.get("credit", 0)) for l in lines] == [("120", 120, 0), ("600", 0, 100), ("391", 0, 20)]
    await wired.mice_events.update_one({"id": "event", "tenant_id": "A"}, {"$set": {"reservation_id": "booking"}})
    with pytest.raises(HTTPException) as linked: await mice.post_beo_to_folio("event", None, USER)
    assert linked.value.status_code == 409
    assert journal.await_count == 1


@pytest.mark.asyncio
async def test_interrupted_gl_post_freezes_editing_and_retry_preserves_its_amount(wired, monkeypatch):  # noqa: F811
    await event(wired)
    journal = AsyncMock(side_effect=RuntimeError("simulated interrupted result"))
    monkeypatch.setattr(mice, "post_journal_entry", journal)
    with pytest.raises(RuntimeError): await mice.post_beo_to_folio("event", None, USER)
    value = await wired.mice_events.find_one({"id": "event", "tenant_id": "A"})
    assert value["gl_posting_state"] == "pending"
    with pytest.raises(HTTPException) as blocked:
        await mice._update_event_impl("event", mice.EventIn(name="Changed", client_name="Test", status="definite", start_date="2026-10-21", end_date="2026-10-21"), USER)
    assert blocked.value.status_code == 409
    journal.side_effect = None
    journal.return_value = {"id": "recovered-journal"}
    await mice.post_beo_to_folio("event", None, USER)
    replay = await mice.post_beo_to_folio("event", None, USER)
    assert replay["already_posted"]
    assert journal.await_count == 2  # failed/uncertain + recovery; no third posting
    assert (await wired.mice_events.find_one({"id": "event", "tenant_id": "A"}))["gl_posting_state"] == "posted"
