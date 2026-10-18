"""Isolated Mongo acceptance. Runs in CI and never uses a non-local server."""
import os
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from modules.pms_core.report_money import add_amount, rounded_totals
from routers.reports_pkg.standard_reports import _posted_revenue_rows


@pytest.fixture
async def ledger_db():
    uri = os.environ.get("REPORT_AUDIT_MONGO_URL") or os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017/")
    parsed = urlsplit(uri)
    if parsed.scheme != "mongodb" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port not in {27017, 27987} or "," in parsed.netloc:
        pytest.fail("Report acceptance tests only permit a local Mongo server")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000, directConnection=True)
    name = "report_audit_acceptance_" + uuid4().hex
    database = client[name]
    try:
        yield database
    finally:
        await client.drop_database(name)
        client.close()


def totals(rows):
    result = {}
    for row in rows:
        add_amount(result, row.get("currency"), row.get("total"))
    return rounded_totals(result)


async def test_real_mongo_postings_refunds_date_precedence_and_tenant_scope(ledger_db):
    db = ledger_db
    await db.folio_charges.insert_many([
        {"tenant_id": "A", "business_date": "2026-10-01", "date": "2026-10-02T02:00:00Z", "total": 50, "currency": "EUR"},
        {"tenant_id": "A", "date": "2026-10-01", "created_at": "2026-10-02", "total": 30, "currency": "TRY"},
        {"tenant_id": "A", "business_date": "", "created_at": "2026-10-01", "total": 5, "currency": "EUR"},
        {"tenant_id": "A", "business_date": "2026-10-01", "total": 999, "voided": True},
        {"tenant_id": "A", "business_date": "2026-10-01", "total": 42, "currency": "TRY", "source_pos_order_id": "room"},
        {"tenant_id": "B", "business_date": "2026-10-01", "total": 999999},
    ])
    await db.extra_charges.insert_one({"tenant_id": "A", "date": "2026-10-01", "total": 7, "currency": "TRY"})
    await db.pos_orders.insert_many([
        {"tenant_id": "A", "id": "direct", "business_date": "2026-10-01", "closed_at": "2026-10-02", "status": "closed", "grand_total": 24, "currency": "TRY"},
        {"tenant_id": "A", "id": "open", "business_date": "2026-10-01", "status": "pending", "grand_total": 1000},
        {"tenant_id": "A", "id": "free", "business_date": "2026-10-01", "status": "closed", "grand_total": 0, "total_amount": 20, "currency": "TRY"},
        {"tenant_id": "A", "id": "settled", "business_date": "2026-10-01", "status": "closed", "grand_total": 100, "currency": "EUR"},
        {"tenant_id": "A", "id": "room", "business_date": "2026-10-01", "status": "closed", "grand_total": 42, "currency": "TRY"},
    ])
    sale = {"tenant_id": "A", "id": "sale", "order_id": "settled", "transaction_date": "2026-10-01", "status": "completed", "total_amount": 110, "tip_amount": 10, "currency": "EUR"}
    await db.pos_transactions.insert_many([sale,
        {"tenant_id": "A", "id": "refund", "order_id": "settled", "transaction_date": "2026-10-02", "status": "refunded", "total_amount": -55, "tip_amount": -5},
        {"tenant_id": "A", "id": "room-tx", "order_id": "room", "transaction_date": "2026-10-01", "status": "completed", "total_amount": 42, "currency": "TRY", "payment_method": "room_charge"},
    ])
    await db.pos_menu_transactions.insert_one({**sale, "id": "mirror"})
    await db.transactions.insert_one({"tenant_id": "A", "transaction_date": "2026-10-01", "status": "completed", "category": "other", "total_amount": 999999})
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 1), database=db)) == {"EUR": 155, "TRY": 103}
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 2), date(2026, 10, 2), database=db)) == {"EUR": -50}
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 2), database=db)) == {"EUR": 105, "TRY": 103}


async def test_real_mongo_legacy_bson_dates_do_not_get_lost_or_moved_to_creation_day(ledger_db):
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "date": datetime(2026, 10, 1, 10, tzinfo=UTC), "created_at": datetime(2026, 10, 2, tzinfo=UTC), "total": 19.99, "currency": "EUR"})
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 1), database=ledger_db)) == {"EUR": 19.99}
    assert await _posted_revenue_rows("A", date(2026, 10, 2), date(2026, 10, 2), database=ledger_db) == []


async def test_real_mongo_flash_does_not_turn_unposted_reservations_into_income_and_keeps_cancelled_details(ledger_db, monkeypatch):
    from routers.reports_pkg import flash_email
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "check_in": "2026-10-01", "check_out": "2026-10-02", "status": "confirmed", "total_amount": 99999},
        {"tenant_id": "A", "check_in": "2026-10-01", "check_out": "2026-10-02", "status": "no_show"},
        {"tenant_id": "A", "check_in": "2026-10-03", "check_out": "2026-10-04", "status": "cancelled", "updated_at": datetime(2026, 10, 1, 10, tzinfo=UTC)},
        {"tenant_id": "B", "status": "cancelled", "updated_at": datetime(2026, 10, 1, 10, tzinfo=UTC)},
    ])
    monkeypatch.setattr(flash_email, "db", ledger_db)
    monkeypatch.setattr(flash_email, "load_stay_night_metrics", AsyncMock(return_value=[{"occupied_rooms": 0, "sold_rooms": 0, "total_rooms": 10, "occupancy_rate": 0}]))
    report = await flash_email.get_flash_report.__wrapped__("2026-10-01", SimpleNamespace(tenant_id="A"))
    assert report["revenue"]["total"] == 0
    assert report["operations"]["no_shows"] == 1
    assert report["operations"]["cancellations"] == 1
    assert len(report["attention_details"]["cancellations"]) == 1
