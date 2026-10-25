"""Room-id-only bookings must keep readable room labels in report exports."""
from copy import deepcopy
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from openpyxl import load_workbook

from core import tenant_currency
from modules.pms_core.report_room_types import enrich_booking_room_labels
from routers.departments import reports
from routers.reports_pkg import reservation_performance

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


async def test_missing_labels_are_tenant_scoped_and_preserve_explicit_history(ledger_db):
    await ledger_db.rooms.insert_many([
        {"tenant_id": "A", "id": "r", "room_number": "203", "room_type_id": "type"},
        {"tenant_id": "B", "id": "r", "room_number": "Secret", "room_type": "Foreign"},
    ])
    await ledger_db.room_types.insert_many([
        {"tenant_id": "A", "id": "type", "name": "Deluxe"},
        {"tenant_id": "B", "id": "type", "name": "Foreign type"},
    ])
    bookings = [{"id": "b", "room_id": "r"}, {"id": "old", "room_id": "r", "room_number": "101", "room_type": "Historical Suite"}]
    before = deepcopy(bookings)
    result = await enrich_booking_room_labels(ledger_db, "A", bookings)
    assert result[0]["room_number"] == "203" and result[0]["room_type"] == "Deluxe"
    assert result[1]["room_number"] == "101" and result[1]["room_type"] == "Historical Suite"
    assert bookings == before


async def test_orphan_id_does_not_match_a_different_room_by_number(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "replacement", "room_number": "203", "room_type": "New suite"})
    rows = await enrich_booking_room_labels(ledger_db, "A", [{"room_id": "deleted", "room_number": "203"}, {"room_number": "203"}])
    assert "room_type" not in rows[0]
    assert rows[1]["room_type"] == "New suite"


async def test_revenue_detail_and_performance_use_assigned_room_labels_without_changing_money(ledger_db, monkeypatch):
    for module in (reports, reservation_performance):
        monkeypatch.setattr(module, "db", ledger_db)
    monkeypatch.setattr(reports, "_enforce", lambda *_: None)
    monkeypatch.setattr(reports, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-24"}))
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(reservation_performance, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r", "room_number": "203", "room_type": "Deluxe"})
    await ledger_db.bookings.insert_one({"tenant_id": "A", "id": "b", "room_id": "r", "guest_name": "Guest",
        "check_in": "2026-10-01", "check_out": "2026-10-03", "total_amount": 200, "currency": "EUR", "status": "checked_out"})
    user = SimpleNamespace(tenant_id="A", role="admin")
    response = await reports.export_revenue_detail_excel("2026-10-01", "2026-10-03", user)
    wb = load_workbook(BytesIO(b"".join([chunk async for chunk in response.body_iterator])))
    rows = list(wb.active.values)[2:]
    assert {r[1] for r in rows} == {"Deluxe"}
    assert sum(r[5] for r in rows) == 200
    performance = await reservation_performance._reservation_performance_payload(tenant_id="A", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31))
    assert performance["rows"][0]["room_number"] == "203"
    assert performance["summary"]["booked_revenue_by_currency"] == {"EUR": 200}


async def test_enrichment_batches_room_reads_without_a_row_cap():
    queries = []

    class Collection:
        def find(self, query, projection):
            queries.append((query, projection))
            return self

        async def to_list(self, count):
            assert count is None
            return [{"id": "r", "room_number": "203", "room_type": "Deluxe"}]

    db = SimpleNamespace(rooms=Collection())
    rows = await enrich_booking_room_labels(db, "A", [{"room_id": "r"} for _ in range(2000)])
    assert len(queries) == 1 and len(rows) == 2000
    assert queries[0][0] == {"tenant_id": "A", "$or": [{"id": {"$in": ["r"]}}]}
