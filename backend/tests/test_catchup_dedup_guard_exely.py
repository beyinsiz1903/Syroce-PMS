"""
Catchup Pre-Insert Dedup Guard — Exely Coverage (Task #56)
==========================================================

Background
----------
Tasks #52 / #53 added the pre-insert duplicate guard to the HotelRunner
ingest path (`hotelrunner_shared._persist_and_process`). The Exely pull
worker (`exely_pull_worker.ExelyPullScheduler.pull_for_tenant`) follows
the same catchup pattern — every 5-minute cycle re-fetches Exely
reservations within a safety window and feeds them into the shared
`common_ingest.ingest_reservation` pipeline.

`common_ingest.ingest_reservation` already implements the same guard
generically (it computes a deterministic ``provider_event_id`` and
short-circuits via ``_check_provider_event_recorded`` before inserting
into ``{provider}_raw_events``). This file pins that behaviour down for
the Exely entry point with three scenarios mirroring the HotelRunner
regression suite (``test_catchup_dedup_guard.py``):

  1. Same payload ingested twice → second call returns
     ``action='duplicate'`` and exactly ONE ``exely_raw_events`` row
     exists.
  2. Distinct ``reservation_id`` values each insert their own row (the
     guard must not over-suppress).
  3. The historical bug: an event whose first ingestion finalised with
     ``status='error'`` is STILL skipped on the next catchup cycle —
     without the guard, downstream dedup only matches
     ``processed``/``duplicate`` and the failed-row pile-up that
     previously produced 8000+ orphan rows would recur.

Test isolation
--------------
These tests use an in-memory MongoDB-shaped stub (``_FakeDB``) for two
reasons:

  * Atlas's free tier caps the project at 500 collections, and
    ``exely_raw_events`` does not yet exist in the dev cluster — driving
    the catchup path against the real DB would trip the cap and fail
    with ``cannot create a new collection``.
  * The behaviour under test is the dedup guard's logic, not Mongo I/O.
    Stubbing ``db`` keeps the test fast (<100ms) and free of cross-test
    contamination.

The stub implements only the operations the dedup path touches:
``find_one``/``insert_one``/``update_one``/``count_documents``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from domains.channel_manager.providers.common_ingest import (
    PROVIDER_COLLECTIONS,
    ingest_reservation,
)
from domains.channel_manager.providers.exely.normalizer import (
    normalize_reservation,
)


PROVIDER = "exely"
RAW_EVENTS = PROVIDER_COLLECTIONS[PROVIDER]["raw_events"]   # exely_raw_events
RESERVATIONS = PROVIDER_COLLECTIONS[PROVIDER]["reservations"]


# ── In-memory MongoDB stub ─────────────────────────────────────────────


def _matches(doc: dict, query: dict) -> bool:
    for k, v in query.items():
        if k.startswith("$"):
            return False
        if doc.get(k) != v:
            return False
    return True


class _FakeColl:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict) -> Any:
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id") or doc.get("_id")})()

    async def find_one(self, query: dict, projection: dict | None = None) -> dict | None:
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def count_documents(self, query: dict) -> int:
        return sum(1 for d in self.docs if _matches(d, query))

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> Any:
        target = None
        for d in self.docs:
            if _matches(d, query):
                target = d
                break
        if target is None and upsert:
            target = {**query}
            self.docs.append(target)
        if target is not None:
            if "$set" in update:
                target.update(update["$set"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    target[k] = (target.get(k) or 0) + v
        return type("R", (), {"matched_count": int(target is not None)})()


class _FakeDB:
    def __init__(self) -> None:
        self._colls: dict[str, _FakeColl] = {}

    def __getitem__(self, name: str) -> _FakeColl:
        if name not in self._colls:
            self._colls[name] = _FakeColl()
        return self._colls[name]


@pytest.fixture
def fake_db(monkeypatch):
    """Replace ``common_ingest.db`` (and the dedup_counter db) with the
    in-memory stub for the duration of the test."""
    fake = _FakeDB()
    from domains.channel_manager.providers import common_ingest as ci
    monkeypatch.setattr(ci, "db", fake)

    # dedup_counter writes to its own collection — point it at the same
    # stub so record_skip is a true no-op rather than a network call.
    try:
        from domains.channel_manager.monitoring import dedup_counter as dc
        monkeypatch.setattr(dc, "db", fake, raising=False)
    except Exception:
        pass

    # set_tenant_context inside ingest paths uses real DB — patch out.
    try:
        from core import tenant_db
        monkeypatch.setattr(tenant_db, "set_tenant_context", lambda _t: None,
                            raising=False)
    except Exception:
        pass

    return fake


# ── Helpers ────────────────────────────────────────────────────────────


def _make_exely_payload(reservation_id: str, last_modify: str) -> dict[str, Any]:
    """Build a minimal Exely-shaped reservation payload — the room is
    intentionally unmapped so process_reservation takes the
    ``pending_mapping`` branch, but that detail is incidental to the
    dedup guard which keys off provider_event_id only."""
    return {
        "reservation_id": reservation_id,
        "status": "commit",
        "guest_name": "Dedup Tester",
        "guest_firstname": "Dedup",
        "guest_lastname": "Tester",
        "guest_email": "dedup@test.local",
        "guest_phone": "+905550000000",
        "guest_country": "TR",
        "checkin_date": "2026-05-01",
        "checkout_date": "2026-05-03",
        "channel": "exely",
        "last_modify": last_modify,
        "create_date": last_modify,
        "rooms": [{
            "room_type_code": "UNMAPPED-EXELY-TEST",
            "rate_plan_code": "BAR",
            "room_name": "Standard",
            "adults": 2,
            "children": 0,
            "amount": 1000,
            "daily_rates": [],
        }],
        "total_amount": 1000.0,
        "currency": "TRY",
    }


def _expected_event_id(reservation_id: str, event_type: str, last_modify: str) -> str:
    return f"{reservation_id}_{event_type}_{last_modify}"


# ══════════════════════════════════════════════════════════════════════
# Scenario 1 — same provider_event_id called twice → second is duplicate
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_same_provider_event_id_does_not_insert_twice(fake_db):
    """Calling ingest_reservation twice with an identical Exely payload
    must return ``action='duplicate'`` on the second call and leave
    exactly ONE ``exely_raw_events`` row in the database."""
    last_mod = datetime.now(UTC).isoformat()
    res_id = f"EXELY-DEDUP-{uuid.uuid4().hex[:8]}"
    tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"
    payload = _make_exely_payload(res_id, last_mod)
    expected_pe_id = _expected_event_id(res_id, "reservation", last_mod)

    first = await ingest_reservation(
        provider=PROVIDER, tenant_id=tenant_id, raw_payload=payload,
        normalizer=normalize_reservation,
        event_type="reservation", source="scheduled_pull",
    )
    second = await ingest_reservation(
        provider=PROVIDER, tenant_id=tenant_id, raw_payload=payload,
        normalizer=normalize_reservation,
        event_type="reservation", source="scheduled_pull",
    )

    assert second.get("success") is True
    assert second.get("action") == "duplicate", (
        f"second call should be a duplicate, got {second!r}. first: {first!r}"
    )
    assert second.get("provider_event_id") == expected_pe_id

    count = await fake_db[RAW_EVENTS].count_documents({
        "tenant_id": tenant_id, "provider_event_id": expected_pe_id,
    })
    assert count == 1, (
        f"expected exactly 1 exely_raw_events row, found {count}. "
        f"first result: {first!r}"
    )


# ══════════════════════════════════════════════════════════════════════
# Scenario 2 — distinct reservation_ids must each persist their own row
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_different_reservation_ids_each_create_a_row(fake_db):
    """The guard must not over-suppress: distinct provider_event_ids
    (different reservation_id) must each insert their own row."""
    base_ts = datetime.now(UTC).isoformat()
    tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"
    res_a = f"EXELY-DEDUP-A-{uuid.uuid4().hex[:8]}"
    res_b = f"EXELY-DEDUP-B-{uuid.uuid4().hex[:8]}"

    out_a = await ingest_reservation(
        provider=PROVIDER, tenant_id=tenant_id,
        raw_payload=_make_exely_payload(res_a, base_ts),
        normalizer=normalize_reservation,
        event_type="reservation", source="scheduled_pull",
    )
    out_b = await ingest_reservation(
        provider=PROVIDER, tenant_id=tenant_id,
        raw_payload=_make_exely_payload(res_b, base_ts),
        normalizer=normalize_reservation,
        event_type="reservation", source="scheduled_pull",
    )

    assert out_a.get("action") != "duplicate", (
        f"first event must not be duplicate, got {out_a!r}"
    )
    assert out_b.get("action") != "duplicate", (
        f"distinct second event must not be duplicate, got {out_b!r}"
    )

    total = await fake_db[RAW_EVENTS].count_documents({"tenant_id": tenant_id})
    assert total == 2, (
        f"expected 2 distinct exely_raw_events rows, found {total}"
    )


# ══════════════════════════════════════════════════════════════════════
# Scenario 3 — historical bug: failed first event still blocks re-insert
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_failed_first_event_still_blocks_second_insert(fake_db):
    """Regression for the 8000+ failed-row pile-up scenario: an event
    whose first ingestion finalised with a non-success status must STILL
    short-circuit on the next catchup cycle. The guard keys off
    provider_event_id existence — it deliberately ignores the row's
    processing status, otherwise failed events would be re-inserted on
    every re-fetch and the collection would grow unbounded."""
    last_mod = datetime.now(UTC).isoformat()
    res_id = f"EXELY-DEDUP-FAIL-{uuid.uuid4().hex[:8]}"
    tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"
    payload = _make_exely_payload(res_id, last_mod)
    expected_pe_id = _expected_event_id(res_id, "reservation", last_mod)

    first = await ingest_reservation(
        provider=PROVIDER, tenant_id=tenant_id, raw_payload=payload,
        normalizer=normalize_reservation,
        event_type="reservation", source="scheduled_pull",
    )
    first_row = await fake_db[RAW_EVENTS].find_one({
        "tenant_id": tenant_id, "provider_event_id": expected_pe_id,
    })
    assert first_row is not None, (
        f"first event was not persisted at all. result: {first!r}"
    )

    # Force the row into a failed terminal status to faithfully reproduce
    # the historical scenario.
    await fake_db[RAW_EVENTS].update_one(
        {"tenant_id": tenant_id, "provider_event_id": expected_pe_id},
        {"$set": {"status": "error", "error_message": "synthetic-test"}},
    )

    second = await ingest_reservation(
        provider=PROVIDER, tenant_id=tenant_id, raw_payload=payload,
        normalizer=normalize_reservation,
        event_type="reservation", source="scheduled_pull",
    )

    assert second.get("action") == "duplicate", (
        f"second call must be skipped by the guard (failed-first "
        f"regression case), got {second!r}"
    )
    assert second.get("reason") == "already_recorded"

    count = await fake_db[RAW_EVENTS].count_documents({
        "tenant_id": tenant_id, "provider_event_id": expected_pe_id,
    })
    assert count == 1, (
        f"REGRESSION: failed Exely event was re-inserted by catchup. "
        f"Expected 1 row for provider_event_id={expected_pe_id}, found {count}."
    )
