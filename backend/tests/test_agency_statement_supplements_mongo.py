"""Supplement acceptance against an isolated local Mongo (including projections)."""

import asyncio
import copy
import os
from datetime import date
from unittest.mock import AsyncMock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from core.agency_reports import build_report
from core.agency_statements import build_statement, statement_line, statement_totals
from routers import agency_statements as st


@pytest.fixture
async def statement_db(monkeypatch):
    uri = os.environ.get("STATEMENT_TEST_MONGO_URL") or os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017/")
    parsed = urlsplit(uri)
    if parsed.scheme != "mongodb" or parsed.hostname not in {"127.0.0.1", "localhost"} or "," in parsed.netloc:
        pytest.fail("Statement acceptance tests only permit an isolated local Mongo server")
    client = AsyncIOMotorClient(uri, directConnection=True, serverSelectionTimeoutMS=2000)
    name = "statement_acceptance_" + uuid4().hex
    db = client[name]
    monkeypatch.setattr(st, "get_system_db", lambda: db)
    monkeypatch.setattr(st, "_notify_agency", AsyncMock())
    monkeypatch.setattr(st, "_notify_hotel", AsyncMock())
    try:
        await db.agency_contracts.insert_one({
            "tenant_id": "t1", "agency_id": "a1", "contract_code": "SOZ-1", "agency_name": "Agency", "hotel_name": "Hotel",
        })
        yield db
    finally:
        await client.drop_database(name)
        client.close()


async def seed_stay(db, booking_id, *, day="2026-11-21", tenant="t1", agency="a1", currency="TRY"):
    ledger = {
        "id": booking_id, "confirmation_code": f"MKT-{booking_id}", "tenant_id": tenant, "agency_id": agency,
        "check_in": day, "check_out": "2026-11-23", "currency": currency, "status": "confirmed",
        "total_amount": 8000.0, "commission_pct": 15.0, "payment_terms": "on_arrival",
    }
    await db.marketplace_bookings.insert_one(copy.deepcopy(ledger))
    await db.bookings.insert_one({
        **ledger, "check_in": day + "T14:00:00", "check_out": "2026-11-23T12:00:00",
        "agency_completion": {"kind": "marketplace"},
    })
    return statement_line(ledger, None)


async def seed_original(db, line, *, status="settled", end="2026-11-30"):
    doc = {
        "id": "original", "number": "EKS-ORIGINAL", "tenant_id": "t1", "agency_id": "a1", "currency": "TRY",
        "period_start": "2026-11-01", "period_end": end, "status": status, "issuer": "hotel", "revision": 1,
        "agreements": {"hotel": 1, "agency": 1}, "lines": [line], "totals": statement_totals([line]),
        "payments": [{"id": "paid", "amount": 1200.0, "direction": "hotel_to_agency"}],
    }
    await db.agency_statements.insert_one(copy.deepcopy(doc))
    return doc


def request(**extra):
    return st.StatementCreate(agency_id="a1", period_start="2026-11-01", period_end="2026-11-30", currency="TRY", **extra)


@pytest.mark.parametrize("issuer", ["hotel", "agency"])
async def test_supplement_contains_only_unbilled_stays_and_settles_independently(statement_db, issuer):
    db = statement_db
    old = await seed_original(db, await seed_stay(db, "old"))
    await seed_stay(db, "late")
    await seed_stay(db, "other-hotel", tenant="t2")
    await seed_stay(db, "other-agency", agency="a2")
    await seed_stay(db, "euro", currency="EUR")
    preview = await st._preview(db, "t1", request(), "issuer", issuer)
    assert [line["booking_id"] for line in preview["lines"]] == ["late"]
    assert preview["supplement_of"] == [old["number"]]
    issued = await st._issue(db, "t1", request(expected_signature=preview["signature"]), issuer=issuer, actor="issuer")
    assert issued["totals"]["gross"] == 8000 and issued["outstanding"] == -1200
    counterpart = st.Party("agency", "agency", agency_id="a1") if issuer == "hotel" else st.Party("hotel", "hotel", tenant_id="t1")
    agreed = await st._agree(issued["id"], 1, counterpart)
    assert agreed["status"] == "agreed"
    paid = await st._record_payment_as(issued["id"], st.PaymentCreate(
        amount=1200, direction="hotel_to_agency", paid_at="2026-12-01", reference="SUPPLEMENT-PAYMENT",
    ), st.Party("agency", "agency", agency_id="a1"))
    assert paid["status"] == "settled" and paid["outstanding"] == 0
    assert await db.agency_statements.find_one({"id": old["id"]}, {"_id": 0}) == old
    report = await build_report(db, side="agency", scope={"agency_id": "a1"},
                               period_start="2026-11-01", period_end="2026-11-30", today=date(2026, 12, 1))
    row = next(row for row in report["rows"] if row["party_id"] == "t1" and row["currency"] == "TRY")
    assert row["receivables"]["hotel_owes_agency"] == 0 and row["unbilled"]["bookings"] == 0
    with pytest.raises(HTTPException) as repeat:
        await st._issue(db, "t1", request(), issuer=issuer, actor="issuer")
    assert repeat.value.status_code == 400
    assert await db.agency_statements.count_documents({"tenant_id": "t1"}) == 2


async def test_void_original_does_not_exclude_its_stays_from_reissue(statement_db):
    db = statement_db
    await seed_original(db, await seed_stay(db, "old"), status="void")
    await seed_stay(db, "late")
    issued = await st._issue(db, "t1", request(), issuer="hotel", actor="issuer")
    assert {line["booking_id"] for line in issued["lines"]} == {"old", "late"}
    assert issued["supplement_of"] == [] and issued["outstanding"] == -2400


async def test_real_projection_still_detects_a_moved_stay_in_overlapping_periods(statement_db):
    db = statement_db
    await seed_original(db, await seed_stay(db, "moved", day="2026-11-05"), end="2026-11-07")
    await db.bookings.update_one({"id": "moved"}, {"$set": {"check_in": "2026-11-21T14:00:00"}})
    await seed_stay(db, "late")
    with pytest.raises(HTTPException) as conflict:
        await st._issue(db, "t1", request(), issuer="agency", actor="issuer")
    assert conflict.value.status_code == 409 and "MKT-moved" in conflict.value.detail
    assert await db.agency_statements.count_documents({}) == 1


async def test_two_simultaneous_supplements_cannot_bill_the_same_stay(statement_db, monkeypatch):
    db = statement_db
    await seed_original(db, await seed_stay(db, "old"))
    await seed_stay(db, "late")
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_build(*args, **kwargs):
        result = await build_statement(*args, **kwargs)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(st, "build_statement", slow_build)
    task = asyncio.create_task(st._issue(db, "t1", request(), issuer="hotel", actor="hotel"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        with pytest.raises(HTTPException) as busy:
            await st._issue(db, "t1", request(), issuer="agency", actor="agency")
        assert isinstance(busy.value, st._StatementIssueBusy)
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=5)
    assert await db.agency_statements.count_documents({"lines.booking_id": "late"}) == 1
    assert await db.agency_statement_locks.count_documents({}) == 0


async def test_monthly_supplement_with_partial_coverage_is_idempotent(statement_db):
    db = statement_db
    await seed_original(db, await seed_stay(db, "old", day="2026-11-05"), end="2026-11-07")
    await seed_stay(db, "late-covered", day="2026-11-06")
    await seed_stay(db, "gap", day="2026-11-21")
    result = await st.auto_issue_previous_month(db, date(2026, 12, 1))
    assert len(result["issued"]) == 2 and result["failed"] == []
    supplement = await db.agency_statements.find_one({"lines.booking_id": "late-covered"})
    assert [line["booking_id"] for line in supplement["lines"]] == ["late-covered"]
    assert "EKS-ORIGINAL" in supplement["supplement_of"]
    again = await st.auto_issue_previous_month(db, date(2026, 12, 1))
    assert again["issued"] == [] and again["failed"] == []
    for booking_id in ("old", "late-covered", "gap"):
        assert await db.agency_statements.count_documents({"status": {"$ne": "void"}, "lines.booking_id": booking_id}) == 1
