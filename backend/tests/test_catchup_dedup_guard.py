"""
Catchup Pre-Insert Dedup Guard — Regression Tests
==================================================

Background
----------
The HotelRunner sync/catchup code path (and the webhook entry point) feeds
every event through `domains.channel_manager.providers.hotelrunner_shared
._persist_and_process`. Before the guard added in earlier work, an event
that finalized with `processing_status='failed'` (e.g. `pending_mapping`)
was re-inserted on every catchup cycle because the downstream pipeline's
`check_provider_event_exists` only short-circuits on
`processed`/`duplicate`. That bug previously produced 8000+ failed
`raw_channel_events` rows and triggered a `critical` health alert.

The pre-insert guard in `_persist_and_process` calls
`unified_repository.check_provider_event_recorded` and, if any row already
exists for the (tenant, provider, provider_event_id) triple, returns a
SKIP/`duplicate` PipelineResult without inserting a second row.

These tests pin that behavior down so a future refactor of the ingest
pipeline cannot silently regress it.

Test isolation
--------------
Each test uses a unique `tenant_id` and cleans up its own rows from
`raw_channel_events`, `webhook_raw_payloads`, `reservation_lineage`, and
`channel_reconciliation_cases` after running. Tests talk to the same
MongoDB the backend uses (configured by `conftest.py`).

Note on `pytest-asyncio` mode
-----------------------------
The repo runs with `asyncio_mode = "auto"`, so `async def test_*`
functions are picked up automatically — no per-test marker needed.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from core.database import db
from domains.channel_manager.data_model import (
    COLL_RAW_CHANNEL_EVENTS,
    COLL_RECONCILIATION_CASES,
    COLL_RESERVATION_LINEAGE,
)
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
)


PROPERTY_ID = "prop-test-dedup"


def _make_payload(hr_number: str, last_modified: str) -> dict[str, Any]:
    """Build a minimal HotelRunner-shaped reservation payload.

    The room_type ('UNMAPPED-TEST') is intentionally not present in
    `room_mappings` for the test tenant, so the pipeline classifies the
    event as `pending_mapping` → `processing_status='failed'`. This is
    exactly the historical condition that re-ingest storms exploited.
    """
    return {
        "hr_number": hr_number,
        "guest": {
            "first_name": "Dedup",
            "last_name": "Tester",
            "email": "dedup@test.local",
            "phone": "+905550000000",
        },
        "checkin_date": "2026-05-01",
        "checkout_date": "2026-05-03",
        "rooms": [{"room_code": "UNMAPPED-TEST", "price": 1000}],
        "rate_plan": "BAR",
        "adults": 2,
        "children": 0,
        "currency": "TRY",
        "total": 1000.0,
        "state": "confirmed",
        "updated_at": last_modified,
    }


async def _count_raw_events(tenant_id: str, provider_event_id: str) -> int:
    return await db[COLL_RAW_CHANNEL_EVENTS].count_documents({
        "tenant_id": tenant_id,
        "provider_event_id": provider_event_id,
    })


async def _delete_tenant_artifacts(tenant_id: str) -> None:
    """Best-effort cleanup of every collection these tests touch.

    `_persist_and_process` writes to:
      - raw_channel_events           (the row we are guarding)
      - webhook_raw_payloads         (raw JSON archive)
      - event_timeline               (controlplane.timeline_writer)
      - reservation_lineage          (only on CREATE/UPDATE/CANCEL paths)
      - channel_reconciliation_cases (only on PENDING_MAPPING etc.)
    """
    for coll in (
        COLL_RAW_CHANNEL_EVENTS,
        COLL_RESERVATION_LINEAGE,
        COLL_RECONCILIATION_CASES,
    ):
        try:
            await db[coll].delete_many({"tenant_id": tenant_id})
        except Exception:
            pass
    for extra_coll in ("webhook_raw_payloads", "event_timeline"):
        try:
            await db[extra_coll].delete_many({"tenant_id": tenant_id})
        except Exception:
            pass


@pytest.fixture
async def tenant_id():
    """Per-test tenant, with cleanup afterwards."""
    tid = f"test-dedup-{uuid.uuid4()}"
    yield tid
    await _delete_tenant_artifacts(tid)


# ══════════════════════════════════════════════════════════════════════
# Scenario 1 — same provider_event_id called twice → second is duplicate
# ══════════════════════════════════════════════════════════════════════

async def test_same_provider_event_id_does_not_insert_twice(tenant_id):
    """
    Calling _persist_and_process twice with an identical payload must:
      - return a SKIP / duplicate result on the second call
      - leave exactly ONE raw_channel_events row in the database
    """
    last_mod = datetime.now(UTC).isoformat()
    hr_number = f"HR-DEDUP-{uuid.uuid4().hex[:8]}"
    payload = _make_payload(hr_number, last_mod)
    expected_pe_id = f"{hr_number}_reservation_create_{last_mod}"

    first = await _persist_and_process(
        tenant_id, PROPERTY_ID, payload, "reservation_create",
    )
    second = await _persist_and_process(
        tenant_id, PROPERTY_ID, payload, "reservation_create",
    )

    assert second.decision == "skip", (
        f"second call should be skipped, got decision={second.decision!r} "
        f"reason={second.reason!r}"
    )
    assert second.status == "duplicate", (
        f"second call status should be 'duplicate', got {second.status!r}"
    )
    assert "duplicate" in second.reason.lower() or "already" in second.reason.lower(), (
        f"second call reason should mention duplicate/already, got {second.reason!r}"
    )

    count = await _count_raw_events(tenant_id, expected_pe_id)
    assert count == 1, (
        f"expected exactly 1 raw_channel_events row for "
        f"provider_event_id={expected_pe_id}, found {count}. "
        f"first decision={first.decision!r} status={first.status!r}"
    )


# ══════════════════════════════════════════════════════════════════════
# Scenario 2 — different provider_event_ids must each be inserted
# ══════════════════════════════════════════════════════════════════════

async def test_different_provider_event_ids_each_create_a_row(tenant_id):
    """The guard must not over-suppress: distinct provider_event_ids
    (different hr_number OR different last_modified) must each persist.
    """
    base_ts = datetime.now(UTC).isoformat()
    hr_a = f"HR-DEDUP-A-{uuid.uuid4().hex[:8]}"
    hr_b = f"HR-DEDUP-B-{uuid.uuid4().hex[:8]}"

    res_a = await _persist_and_process(
        tenant_id, PROPERTY_ID,
        _make_payload(hr_a, base_ts), "reservation_create",
    )
    res_b = await _persist_and_process(
        tenant_id, PROPERTY_ID,
        _make_payload(hr_b, base_ts), "reservation_create",
    )

    assert res_a.decision != "skip" or res_a.status != "duplicate", (
        f"first event must not be treated as duplicate, got {res_a.to_dict()}"
    )
    assert res_b.decision != "skip" or res_b.status != "duplicate", (
        f"second (distinct) event must not be treated as duplicate, "
        f"got {res_b.to_dict()}"
    )

    total = await db[COLL_RAW_CHANNEL_EVENTS].count_documents({
        "tenant_id": tenant_id,
    })
    assert total == 2, (
        f"expected 2 distinct raw_channel_events rows, found {total}"
    )


# ══════════════════════════════════════════════════════════════════════
# Scenario 3 — historical bug: first event ends 'failed', second still skipped
# ══════════════════════════════════════════════════════════════════════

async def test_failed_first_event_still_blocks_second_insert(tenant_id):
    """
    This is the exact regression we are guarding against:
      1. First catchup pass ingests an event that finalizes with
         processing_status='failed' (because the room is unmapped — a
         realistic production scenario before mappings are wired up).
      2. The next catchup pass sees the same provider_event_id again.
      3. Without the guard, the downstream pipeline's dedup check
         (which only matches 'processed'/'duplicate') would let the
         second insert through, and the failed-event count would grow
         unbounded — exactly the 8000+ row pile-up we previously fixed.
      4. With the guard, the second call must short-circuit to
         duplicate/skip, and the DB row count stays at 1.
    """
    last_mod = datetime.now(UTC).isoformat()
    hr_number = f"HR-DEDUP-FAIL-{uuid.uuid4().hex[:8]}"
    payload = _make_payload(hr_number, last_mod)
    expected_pe_id = f"{hr_number}_reservation_create_{last_mod}"

    first = await _persist_and_process(
        tenant_id, PROPERTY_ID, payload, "reservation_create",
    )

    # Confirm the precondition: first event was actually persisted with a
    # non-success status. If this assertion ever flips, the unmapped-room
    # condition stopped reproducing the historical scenario and the test
    # needs to be re-targeted.
    first_row = await db[COLL_RAW_CHANNEL_EVENTS].find_one({
        "tenant_id": tenant_id,
        "provider_event_id": expected_pe_id,
    }, {"_id": 0, "processing_status": 1, "decision_result": 1})
    assert first_row is not None, "first event was not persisted at all"
    assert first_row.get("processing_status") in ("failed", "pending"), (
        f"precondition: first event should be failed/pending (unmapped "
        f"room), got status={first_row.get('processing_status')!r} "
        f"decision={first_row.get('decision_result')!r}. "
        f"first result: {first.to_dict()}"
    )
    # Strong precondition: the unmapped room must drive the pipeline into
    # the PENDING_MAPPING decision. If this assertion ever flips (e.g. the
    # 'UNMAPPED-TEST' room code somehow gets a mapping), the historical
    # scenario is no longer being reproduced and the test must be retargeted.
    assert first.decision == "pending_mapping", (
        f"precondition: first event must take the PENDING_MAPPING path "
        f"to reproduce the original failed-row regression, got "
        f"decision={first.decision!r}"
    )

    # Re-run the catchup: same payload, same provider_event_id.
    second = await _persist_and_process(
        tenant_id, PROPERTY_ID, payload, "reservation_create",
    )

    assert second.decision == "skip", (
        f"second call must be skipped by the guard, got "
        f"decision={second.decision!r} reason={second.reason!r}"
    )
    assert second.status == "duplicate", (
        f"second call status must be 'duplicate', got {second.status!r}"
    )

    count = await _count_raw_events(tenant_id, expected_pe_id)
    assert count == 1, (
        f"REGRESSION: failed event was re-inserted by catchup. "
        f"Expected 1 row for provider_event_id={expected_pe_id}, found {count}."
    )
