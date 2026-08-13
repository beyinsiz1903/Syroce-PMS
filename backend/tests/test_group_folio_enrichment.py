from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers.hotel_services_pkg import group_folio
from routers.hotel_services_pkg._common import GroupFolioMerge


def _matches(document: dict, query: dict) -> bool:
    for field, expected in query.items():
        if field == "$and":
            if not all(_matches(document, option) for option in expected):
                return False
            continue
        if field == "$or":
            if not any(_matches(document, option) for option in expected):
                return False
            continue
        value = document.get(field)
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
            if "$exists" in expected and (field in document) != expected["$exists"]:
                return False
            if "$type" in expected and expected["$type"] == "string" and not isinstance(value, str):
                return False
        elif value != expected:
            return False
    return True


class _Cursor:
    def __init__(self, documents):
        self.documents = documents
        self._index = 0

    async def to_list(self, length=None):
        rows = deepcopy(self.documents)
        return rows[:length] if length else rows

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self.documents):
            raise StopAsyncIteration
        document = deepcopy(self.documents[self._index])
        self._index += 1
        return document


class _Collection:
    def __init__(self, documents, name="collection"):
        self.documents = documents
        self.find_calls = 0
        self.name = name

    def find(self, query, projection=None):
        self.find_calls += 1
        return _Cursor([document for document in self.documents if _matches(document, query)])

    async def find_one(self, query, projection=None):
        return next((deepcopy(document) for document in self.documents if _matches(document, query)), None)

    async def update_one(self, query, update, upsert=False):
        document = next((document for document in self.documents if _matches(document, query)), None)
        if document is None and upsert:
            document = deepcopy(update["$setOnInsert"])
            self.documents.append(document)
            return SimpleNamespace(upserted_id=document.get("id", "inserted"), modified_count=0)
        if document is None:
            return SimpleNamespace(upserted_id=None, modified_count=0)
        if "$set" in update:
            document.update(deepcopy(update["$set"]))
            for field in update.get("$unset", {}):
                document.pop(field, None)
            return SimpleNamespace(upserted_id=None, modified_count=1)
        return SimpleNamespace(upserted_id=None, modified_count=0)


class _Database:
    def __init__(self):
        self.bookings = _Collection(
            [
                {
                    "id": "booking-1",
                    "tenant_id": "tenant-a",
                    "guest_id": "guest-1",
                    "room_id": "room-1",
                    "total_amount": 2500,
                },
                {
                    "id": "booking-1",
                    "tenant_id": "tenant-b",
                    "guest_name": "other tenant",
                    "room_number": "999",
                    "total_amount": 9000,
                },
            ]
        )
        self.guests = _Collection(
            [
                {"id": "guest-1", "tenant_id": "tenant-a", "first_name": "Test", "last_name": "Guest"},
                {"id": "guest-1", "tenant_id": "tenant-b", "name": "Other Tenant Guest"},
            ]
        )
        self.rooms = _Collection(
            [
                {"id": "room-1", "tenant_id": "tenant-a", "room_number": "104"},
                {"id": "room-1", "tenant_id": "tenant-b", "room_number": "999"},
            ]
        )
        self.folios = _Collection(
            [
                {"booking_id": "booking-1", "tenant_id": "tenant-a", "type": "charge", "amount": 500},
                {"booking_id": "booking-1", "tenant_id": "tenant-a", "type": "payment", "amount": 100},
                {"booking_id": "booking-1", "tenant_id": "tenant-b", "type": "charge", "amount": 9000},
            ]
        )
        self.payments = _Collection(
            [
                {"booking_id": "booking-1", "tenant_id": "tenant-a", "amount": 250},
                {"booking_id": "booking-1", "tenant_id": "tenant-b", "amount": 9000},
            ]
        )


class _MergeDatabase:
    def __init__(self):
        self.group_bookings = _Collection(
            [{"id": "group-1", "tenant_id": "tenant-a", "booking_ids": ["master", "source"]}],
            "group_bookings",
        )
        self.bookings = _Collection(
            [
                {"id": "master", "tenant_id": "tenant-a", "room_number": "101"},
                {"id": "source", "tenant_id": "tenant-a", "room_number": "102"},
            ],
            "bookings",
        )
        self.rooms = _Collection([], "rooms")
        self.folios = _Collection(
            [{"id": "folio-1", "tenant_id": "tenant-a", "booking_id": "source", "type": "charge", "amount": 300}],
            "folios",
        )
        self.payments = _Collection(
            [{"id": "payment-1", "tenant_id": "tenant-a", "booking_id": "source", "amount": 100}],
            "payments",
        )
        self.folio_merge_logs = _Collection([], "folio_merge_logs")


@pytest.mark.asyncio
async def test_group_folio_enriches_guest_and_room_with_tenant_scoped_bulk_queries(monkeypatch):
    database = _Database()
    monkeypatch.setattr(group_folio, "db", database)
    monkeypatch.setattr(group_folio, "decrypt_guest_doc", lambda document: document)

    rows = await group_folio._load_group_booking_rows("tenant-a", ["booking-1", "booking-1"])

    assert len(rows) == 1
    assert rows[0]["guest_name"] == "Test Guest"
    assert rows[0]["room_number"] == "104"
    assert rows[0]["folio_charges"] == 500
    assert rows[0]["payments"] == 250
    assert rows[0]["balance"] == 2750
    assert all(
        collection.find_calls == 1
        for collection in (
            database.bookings,
            database.guests,
            database.rooms,
            database.folios,
            database.payments,
        )
    )


@pytest.mark.asyncio
async def test_group_folio_returns_empty_without_database_queries(monkeypatch):
    database = _Database()
    monkeypatch.setattr(group_folio, "db", database)

    assert await group_folio._load_group_booking_rows("tenant-a", []) == []
    assert all(
        collection.find_calls == 0
        for collection in (
            database.bookings,
            database.guests,
            database.rooms,
            database.folios,
            database.payments,
        )
    )


@pytest.mark.asyncio
async def test_group_folio_merge_is_idempotent_and_keeps_financial_copies_single(monkeypatch):
    database = _MergeDatabase()
    monkeypatch.setattr(group_folio, "db", database)

    async def _index_ready(*args, **kwargs):
        return None

    monkeypatch.setattr(group_folio, "ensure_compound_unique", _index_ready)
    payload = GroupFolioMerge(
        group_id="group-1",
        master_booking_id="master",
        merge_booking_ids=["source"],
        merge_payments=True,
    )
    user = SimpleNamespace(tenant_id="tenant-a", name="Auditor")

    first = await group_folio.merge_group_folios(payload, current_user=user)
    second = await group_folio.merge_group_folios(payload, current_user=user)

    assert first["merged_entries_count"] == 1
    assert first["merged_payments_count"] == 1
    assert second["merged_entries_count"] == 0
    assert second["merged_payments_count"] == 0
    assert len([row for row in database.folios.documents if row.get("merged_from") == "source"]) == 1
    assert len([row for row in database.payments.documents if row.get("merged_from") == "source"]) == 1
    assert len(database.folio_merge_logs.documents) == 1
    assert next(row for row in database.bookings.documents if row["id"] == "source")["folio_merged_to"] == "master"


@pytest.mark.asyncio
async def test_group_folio_merge_rejects_booking_outside_group(monkeypatch):
    database = _MergeDatabase()
    monkeypatch.setattr(group_folio, "db", database)
    payload = GroupFolioMerge(
        group_id="group-1",
        master_booking_id="master",
        merge_booking_ids=["outside"],
        merge_payments=True,
    )

    with pytest.raises(HTTPException) as exc:
        await group_folio.merge_group_folios(
            payload,
            current_user=SimpleNamespace(tenant_id="tenant-a", name="Auditor"),
        )

    assert exc.value.status_code == 400
