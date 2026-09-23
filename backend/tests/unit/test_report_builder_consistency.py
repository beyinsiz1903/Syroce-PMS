from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from routers.report_builder import (
    DATA_SOURCES,
    ReportConfig,
    ReportFilter,
    _effective_source_date,
    _enrich_report_docs,
    _matches_report_filter,
    _within_requested_dates,
    fetch_report_data,
)


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length):
        return self.docs[:length]

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, length):
        self.docs = self.docs[:length]
        return self


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection):
        docs = list(self.docs)
        if "tenant_id" in query:
            docs = [doc for doc in docs if doc.get("tenant_id") == query["tenant_id"]]
        ids = query.get("id", {}).get("$in")
        if ids is not None:
            docs = [doc for doc in docs if doc.get("id") in ids]
        folio_ids = query.get("folio_id", {}).get("$in")
        if folio_ids is not None:
            docs = [doc for doc in docs if doc.get("folio_id") in folio_ids]
        if query.get("voided") == {"$ne": True}:
            docs = [doc for doc in docs if doc.get("voided") is not True]
        excluded = query.get("status", {}).get("$nin", [])
        if excluded:
            docs = [doc for doc in docs if doc.get("status") not in excluded]
        return _Cursor(docs)


class _DB(SimpleNamespace):
    def __getitem__(self, name):
        return getattr(self, name)


@pytest.mark.asyncio
async def test_reservation_builder_resolves_guest_and_room_relations():
    db = _DB(
        bookings=_Collection([]),
        rooms=_Collection([{"id": "r1", "tenant_id": "t1", "room_number": "201", "room_type": "Standard"}]),
        guests=_Collection([{"id": "g1", "tenant_id": "t1", "first_name": "Ada", "last_name": "Lovelace"}]),
        folio_charges=_Collection([]),
        payments=_Collection([]),
    )
    docs = [{"id": "b1", "tenant_id": "t1", "room_id": "r1", "guest_id": "g1"}]

    result = await _enrich_report_docs(db, "reservations", "t1", docs)

    assert result[0]["guest_name"] == "Ada Lovelace"
    assert result[0]["room_number"] == "201"
    assert result[0]["room_type"] == "Standard"


@pytest.mark.asyncio
async def test_folio_builder_recomputes_active_ledger_totals():
    db = _DB(
        bookings=_Collection([{"id": "b1", "tenant_id": "t1", "room_id": "r1", "guest_id": "g1"}]),
        rooms=_Collection([{"id": "r1", "tenant_id": "t1", "room_number": "201"}]),
        guests=_Collection([{"id": "g1", "tenant_id": "t1", "name": "Test Misafir"}]),
        folio_charges=_Collection(
            [
                {"tenant_id": "t1", "folio_id": "f1", "total": 1000},
                {"tenant_id": "t1", "folio_id": "f1", "total": 400, "voided": True},
            ]
        ),
        payments=_Collection(
            [
                {"tenant_id": "t1", "folio_id": "f1", "amount": 300, "status": "paid"},
                {"tenant_id": "t1", "folio_id": "f1", "amount": 100, "status": "failed"},
                {"tenant_id": "t1", "folio_id": "f1", "amount": 50, "status": "paid", "payment_type": "refund"},
            ]
        ),
    )
    docs = [{"id": "f1", "tenant_id": "t1", "booking_id": "b1", "total_charges": 9999}]

    result = await _enrich_report_docs(db, "folios", "t1", docs)

    assert result[0]["guest_name"] == "Test Misafir"
    assert result[0]["room_number"] == "201"
    assert result[0]["total_charges"] == 1000
    assert result[0]["total_payments"] == 250
    assert result[0]["balance"] == 750


def test_revenue_date_uses_business_date_and_handles_bson_datetime():
    source = DATA_SOURCES["revenue"]
    config = ReportConfig(
        data_source="revenue",
        columns=["date", "total"],
        date_from="2026-09-23",
        date_to="2026-09-23",
    )
    row = {"business_date": datetime(2026, 9, 23, 22, 30, tzinfo=UTC), "total": 500}

    assert _effective_source_date(source, row) == "2026-09-23"
    assert _within_requested_dates(config, source, row) is True
    assert (
        _matches_report_filter(
            "revenue",
            source,
            row,
            ReportFilter(field="total", operator="gte", value="500"),
        )
        is True
    )


@pytest.mark.asyncio
async def test_fetch_report_data_applies_relations_dates_and_computed_filter(monkeypatch):
    db = _DB(
        bookings=_Collection(
            [
                {
                    "id": "b1",
                    "tenant_id": "t1",
                    "room_id": "r1",
                    "guest_id": "g1",
                    "check_in": "2026-09-23T15:00:00",
                    "check_out": "2026-09-25T11:00:00",
                    "total_amount": 2000,
                },
                {
                    "id": "b2",
                    "tenant_id": "t1",
                    "room_id": "r2",
                    "guest_id": "g2",
                    "check_in": "2026-09-20T15:00:00",
                    "check_out": "2026-09-21T11:00:00",
                    "total_amount": 500,
                },
            ]
        ),
        rooms=_Collection(
            [
                {"id": "r1", "tenant_id": "t1", "room_number": "201"},
                {"id": "r2", "tenant_id": "t1", "room_number": "202"},
            ]
        ),
        guests=_Collection(
            [
                {"id": "g1", "tenant_id": "t1", "name": "Birinci Misafir"},
                {"id": "g2", "tenant_id": "t1", "name": "İkinci Misafir"},
            ]
        ),
        folio_charges=_Collection([]),
        payments=_Collection([]),
    )
    monkeypatch.setattr("routers.report_builder._db", db)
    config = ReportConfig(
        data_source="reservations",
        columns=["guest_name", "room_number", "nights", "total_amount"],
        date_from="2026-09-23",
        date_to="2026-09-23",
        filters=[ReportFilter(field="nights", operator="gte", value="2")],
    )

    rows = await fetch_report_data(config, "t1", has_pii=True)

    assert rows == [
        {
            "guest_name": "Birinci Misafir",
            "room_number": "201",
            "nights": 2,
            "total_amount": 2000,
        }
    ]
