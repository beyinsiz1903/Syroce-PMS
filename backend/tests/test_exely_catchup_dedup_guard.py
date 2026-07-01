"""
Exely Catchup Pre-Insert Dedup Guard — Regression Tests
========================================================

Background
----------
Task #56: mirror the HotelRunner pre-insert dedup guard for the Exely
catchup ingest path.

The Exely pull worker (``ExelyPullScheduler``) re-fetches every event
inside a 5-minute safety window on every cycle, so the same external
reservation will appear multiple times. Without a guard,
``store_raw_event`` creates a fresh document in ``exely_raw_events`` for
every re-fetched event, bloating the collection (and tripping the same
"failed event pile-up" alert HotelRunner had before its guard).

The guard added in ``common_ingest.ingest_reservation``:
  1. Computes a deterministic ``provider_event_id`` from
     ``external_id`` + ``event_type`` + ``last_modify``.
  2. Calls a per-provider ``_check_provider_event_recorded`` lookup on
     ``{provider}_raw_events``.
  3. If found, increments ``dedup_counter`` and returns
     ``action="duplicate"`` without inserting.
  4. Otherwise inserts via ``store_raw_event`` with the
     ``provider_event_id`` field stamped on the row, so the next call
     short-circuits.

These tests pin the Exely-side contract.

Test isolation
--------------
Each test uses a unique ``tenant_id`` and cleans up its own rows from
``exely_raw_events``, ``exely_reservations``, and the dedup counter.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from core.database import db
from domains.channel_manager.providers.common_ingest import (
    _build_provider_event_id,
    ingest_reservation,
)
from domains.channel_manager.providers.exely.normalizer import (
    normalize_reservation,
)
from domains.channel_manager.monitoring import dedup_counter


PROVIDER = "exely"


def _make_payload(reservation_id: str, last_modify: str) -> dict[str, Any]:
    return {
        "reservation_id": reservation_id,
        "last_modify": last_modify,
        "create_date": last_modify,
        "channel": "Booking.com",
        "status": "commit",
        "guest_firstname": "Dedup",
        "guest_lastname": "Tester",
        "guest_email": "exely-dedup@test.local",
        "guest_phone": "+905550000000",
        "guest_country": "TR",
        "checkin_date": "2026-05-01",
        "checkout_date": "2026-05-03",
        "currency": "TRY",
        "total": 1000.0,
        "rooms": [{
            "room_type_code": "STD",
            "rate_plan_code": "BAR",
            "room_name": "Standard Double",
            "adults": 2,
            "children": 0,
            "amount": 1000,
            "daily_rates": [],
        }],
        "total_rooms": 1,
        "total_guests": 2,
        "notes": "",
        "payment_method": "card",
    }


async def _count_raw_events(tenant_id: str, reservation_id: str) -> int:
    return await db["exely_raw_events"].count_documents({
        "tenant_id": tenant_id,
        "external_id": reservation_id,
    })


async def _delete_tenant_artifacts(tenant_id: str) -> None:
    """Best-effort cleanup of every collection these tests touch."""
    for coll in ("exely_raw_events", "exely_reservations", "exely_sync_logs"):
        try:
            await db[coll].delete_many({"tenant_id": tenant_id})
        except Exception:
            pass


async def _ensure_exely_raw_events_writable() -> str | None:
    """Probe whether ``exely_raw_events`` accepts a write right now.

    Dev Atlas free-tier is at the 500-collection cap, so a brand-new
    collection cannot be auto-created on first insert. In that
    environment we skip the integration scenarios with an explicit
    reason — the production code path is identical and the unit-level
    helpers (``_build_provider_event_id``) are still exercised by the
    pure-function tests further down.

    Returns None on success, or a skip-reason string on failure.
    """
    probe_id = f"probe-{uuid.uuid4().hex[:8]}"
    try:
        await db["exely_raw_events"].insert_one({
            "id": probe_id, "tenant_id": probe_id, "_probe": True,
        })
        await db["exely_raw_events"].delete_one({"id": probe_id})
        return None
    except Exception as e:
        return f"exely_raw_events not writable in this environment: {e}"


@pytest.fixture(scope="module")
async def _exely_writable_check():
    """Module-scoped probe so we issue ONE probe-write per file rather
    than one per test. Returns the skip reason or None."""
    return await _ensure_exely_raw_events_writable()


@pytest.fixture
async def tenant_id(_exely_writable_check):
    """Per-test tenant, with cleanup afterwards (DB + dedup counter).

    Skips immediately when the module-scoped probe reported the Atlas
    cap is blocking new collections.
    """
    if _exely_writable_check:
        pytest.skip(_exely_writable_check)
    tid = f"test-exely-dedup-{uuid.uuid4()}"
    yield tid
    await _delete_tenant_artifacts(tid)
    await dedup_counter.reset()


# ══════════════════════════════════════════════════════════════════════
# Scenario 1 — same reservation_id + last_modify twice → second is skipped
# ══════════════════════════════════════════════════════════════════════

async def test_same_event_does_not_insert_twice(tenant_id):
    """Calling ingest_reservation twice with an identical Exely payload
    must:
      - return action='duplicate' on the second call,
      - leave exactly ONE document in exely_raw_events,
      - increment the catchup dedup counter once.
    """
    last_mod = datetime.now(UTC).isoformat()
    rid = f"EX-DEDUP-{uuid.uuid4().hex[:8]}"
    payload = _make_payload(rid, last_mod)

    first = await ingest_reservation(
        PROVIDER, tenant_id, payload, normalize_reservation,
        event_type="reservation", source="pull",
    )
    second = await ingest_reservation(
        PROVIDER, tenant_id, payload, normalize_reservation,
        event_type="reservation", source="pull",
    )

    assert first["success"] is True, f"first call must succeed, got {first}"
    assert second.get("action") == "duplicate", (
        f"second call must short-circuit as duplicate, got {second}"
    )
    assert second.get("reason") == "already_recorded"

    count = await _count_raw_events(tenant_id, rid)
    assert count == 1, (
        f"expected exactly 1 exely_raw_events row for reservation_id={rid}, "
        f"found {count}"
    )

    counts = await dedup_counter.get_counts()
    assert counts["last_24h_by_tenant_provider"].get(f"{PROVIDER}/{tenant_id}") == 1, (
        f"dedup counter must have recorded exactly one Exely skip for this "
        f"tenant, got {counts}"
    )


# ══════════════════════════════════════════════════════════════════════
# Scenario 2 — different reservation_ids each create a distinct row
# ══════════════════════════════════════════════════════════════════════

async def test_distinct_reservations_each_create_a_row(tenant_id):
    """The guard must not over-suppress: distinct reservation_ids must
    each persist."""
    last_mod = datetime.now(UTC).isoformat()
    rid_a = f"EX-DEDUP-A-{uuid.uuid4().hex[:8]}"
    rid_b = f"EX-DEDUP-B-{uuid.uuid4().hex[:8]}"

    res_a = await ingest_reservation(
        PROVIDER, tenant_id, _make_payload(rid_a, last_mod),
        normalize_reservation, event_type="reservation", source="pull",
    )
    res_b = await ingest_reservation(
        PROVIDER, tenant_id, _make_payload(rid_b, last_mod),
        normalize_reservation, event_type="reservation", source="pull",
    )

    assert res_a.get("action") != "duplicate", res_a
    assert res_b.get("action") != "duplicate", res_b

    total = await db["exely_raw_events"].count_documents({"tenant_id": tenant_id})
    assert total == 2, (
        f"expected 2 distinct exely_raw_events rows, found {total}"
    )


# ══════════════════════════════════════════════════════════════════════
# Scenario 3 — different last_modify values are NOT deduped (modification
# events are real updates that must be ingested)
# ══════════════════════════════════════════════════════════════════════

async def test_modification_with_newer_last_modify_is_ingested(tenant_id):
    """A second ingest of the same reservation with a NEWER last_modify
    must be treated as a fresh event by the pre-insert guard, since it
    represents a real modification the downstream pipeline needs to
    process."""
    rid = f"EX-DEDUP-MOD-{uuid.uuid4().hex[:8]}"
    payload_v1 = _make_payload(rid, "2026-04-27T10:00:00+00:00")
    payload_v2 = _make_payload(rid, "2026-04-27T10:30:00+00:00")
    payload_v2["status"] = "modify"

    first = await ingest_reservation(
        PROVIDER, tenant_id, payload_v1, normalize_reservation,
        event_type="reservation", source="pull",
    )
    second = await ingest_reservation(
        PROVIDER, tenant_id, payload_v2, normalize_reservation,
        event_type="modification", source="pull",
    )

    assert first["success"] is True
    assert second.get("action") != "duplicate", (
        f"distinct (reservation_id, event_type, last_modify) tuple must NOT "
        f"be deduped, got {second}"
    )

    total = await db["exely_raw_events"].count_documents({"tenant_id": tenant_id})
    assert total == 2, (
        f"expected 2 rows (initial + modification), found {total}"
    )


# ══════════════════════════════════════════════════════════════════════
# Scenario 4 — provider_event_id helper formats correctly
# ══════════════════════════════════════════════════════════════════════

def test_build_provider_event_id_uses_last_modify_when_present():
    """Unit-level guard for the deterministic ID format. The ingest
    pipeline depends on this being stable across catchup cycles."""
    payload = {"reservation_id": "RES-1", "last_modify": "2026-04-27T10:00:00+00:00"}
    pe = _build_provider_event_id(payload, "RES-1", "reservation", "abc123")
    assert pe == "RES-1_reservation_2026-04-27T10:00:00+00:00", pe


def test_build_provider_event_id_falls_back_to_payload_hash():
    """When the payload has no last-modified field, fall back to the
    payload hash so byte-identical replays still dedupe."""
    payload = {"reservation_id": "RES-2"}
    pe = _build_provider_event_id(payload, "RES-2", "reservation", "abc123")
    assert pe == "RES-2_reservation_hash:abc123", pe


# ══════════════════════════════════════════════════════════════════════
# Scenario 5 — documented limitation: same last_modify hides payload edits
# ══════════════════════════════════════════════════════════════════════

async def test_same_last_modify_skips_even_if_inner_payload_changed(tenant_id):
    """Pin the inherited HotelRunner behaviour: when the provider sends
    two events with the same external_id + same last_modify but with
    different inner payload contents, the pre-insert guard treats the
    second one as a duplicate.

    Why this is acceptable today
    ----------------------------
    Both Exely and HotelRunner bump ``last_modify`` on every real
    modification. A payload edit without a timestamp bump indicates a
    provider bug (or someone replaying historical data), not a
    legitimate update. The downstream ``check_idempotency`` path in
    ``process_reservation`` is the authoritative guard for content
    changes, but it never runs because the pre-insert short-circuit
    fires first.

    This test exists so a future maintainer who *does* want changed-
    payload-with-same-timestamp to pass through immediately sees this
    test fail and knows the pre-insert guard is the layer to revisit.
    """
    fixed_last_mod = "2026-04-27T12:00:00+00:00"
    rid = f"EX-DEDUP-SAMETS-{uuid.uuid4().hex[:8]}"

    payload_a = _make_payload(rid, fixed_last_mod)
    payload_b = _make_payload(rid, fixed_last_mod)
    # Edit the inner payload without bumping last_modify.
    payload_b["notes"] = "edited but same timestamp"
    payload_b["total"] = 9999.0

    first = await ingest_reservation(
        PROVIDER, tenant_id, payload_a, normalize_reservation,
        event_type="reservation", source="pull",
    )
    second = await ingest_reservation(
        PROVIDER, tenant_id, payload_b, normalize_reservation,
        event_type="reservation", source="pull",
    )

    assert first["success"] is True
    assert second.get("action") == "duplicate", (
        f"DOCUMENTED LIMITATION: same last_modify treats edited payload "
        f"as duplicate, got {second}. If this fails, the guard semantics "
        f"have changed — update both the docstring and the runbook."
    )
    count = await _count_raw_events(tenant_id, rid)
    assert count == 1, (
        f"only one row should be persisted under the documented "
        f"limitation, found {count}"
    )
