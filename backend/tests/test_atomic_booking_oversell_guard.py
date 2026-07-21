"""F8N — Reservation oversell guard regression tests.

Direct DB-level tests that exercise `create_booking_atomic` without going
through HTTP. They validate four scenarios required by Task #215:

  (a) Serial overlap → second insert raises BookingConflictError (409).
  (b) Non-overlap (adjacent dates) → both inserts succeed.
  (c) Terminal-state booking (cancelled / no_show / checked_out) does NOT
      block a fresh booking on the same room/dates.
  (d) Concurrent parallel inserts → exactly one wins, the rest raise
      BookingConflictError.

The bookings-level defense-in-depth overlap helper
(`_find_overlapping_active_booking`) is also exercised directly.

Skips automatically when MongoDB is not reachable (the conftest fixture
binds Motor to the session event loop).
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.atomic_booking import ensure_booking_indexes

@pytest.fixture(autouse=True)
async def _ensure_rnl_index(isolated_tenant):
    await ensure_booking_indexes()


pytestmark = pytest.mark.asyncio


# ── helpers ────────────────────────────────────────────────────────────────

TEST_TENANT_PREFIX = "f8n_oversell_test_"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _mk_booking_doc(tenant_id: str, room_id: str, check_in: str, check_out: str,
                    *, status: str = "confirmed", booking_id: str | None = None) -> dict:
    return {
        "id": booking_id or str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "room_id": room_id,
        "guest_id": str(uuid.uuid4()),
        "check_in": check_in,
        "check_out": check_out,
        "adults": 1,
        "children": 0,
        "guests_count": 1,
        "total_amount": 1000.0,
        "paid_amount": 0.0,
        "status": status,
        "channel": "direct",
        "source_channel": "direct",
        "origin": "f8n_test",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "_version": 1,
    }


async def _cleanup(tenant_id: str) -> None:
    from core.database import db
    from core.tenant_db import tenant_context
    with tenant_context(tenant_id):
        await db.bookings.delete_many({"tenant_id": tenant_id})
        await db.room_night_locks.delete_many({"tenant_id": tenant_id})


@pytest.fixture
async def isolated_tenant():
    """Yield a unique tenant_id and wipe its bookings + locks after the test."""
    tid = f"{TEST_TENANT_PREFIX}{_ts()}_{uuid.uuid4().hex[:8]}"
    yield tid
    try:
        await _cleanup(tid)
    except Exception:
        pass


# ── tests ──────────────────────────────────────────────────────────────────


async def test_a_serial_overlap_rejects(isolated_tenant):
    """Second booking on same room + overlapping dates → BookingConflictError."""
    from core.atomic_booking import (
        BookingConflictError,
        create_booking_atomic,
    )

    from core.tenant_db import tenant_context

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:12]}"
    ci = "2030-06-10"
    co = "2030-06-14"

    first = _mk_booking_doc(tid, room_id, ci, co)
    with tenant_context(tid):
        await create_booking_atomic(first)

        # Identical window — must reject.
        second = _mk_booking_doc(tid, room_id, ci, co)
        with pytest.raises(BookingConflictError) as exc:
            await create_booking_atomic(second)
        assert exc.value.conflicting_booking_id is not None

        # Partial overlap (back half) — must also reject.
        third = _mk_booking_doc(tid, room_id, "2030-06-12", "2030-06-16")
        with pytest.raises(BookingConflictError):
            await create_booking_atomic(third)


async def test_b_non_overlap_accepts(isolated_tenant):
    """Adjacent dates (check_out == next check_in) → both succeed."""
    from core.atomic_booking import create_booking_atomic

    from core.tenant_db import tenant_context

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:12]}"

    first = _mk_booking_doc(tid, room_id, "2030-07-01", "2030-07-03")
    second = _mk_booking_doc(tid, room_id, "2030-07-03", "2030-07-05")
    with tenant_context(tid):
        await create_booking_atomic(first)
        await create_booking_atomic(second)  # must NOT raise

        from core.database import db
        count = await db.bookings.count_documents({"tenant_id": tid, "room_id": room_id})
    assert count == 2


@pytest.mark.parametrize("terminal_status", ["cancelled", "no_show", "checked_out"])
async def test_c_terminal_state_does_not_block(isolated_tenant, terminal_status):
    """A booking in cancelled / no_show / checked_out releases its window."""
    from core.atomic_booking import create_booking_atomic, release_booking_nights
    from core.database import db

    from core.tenant_db import tenant_context

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:12]}"
    ci, co = "2030-08-10", "2030-08-13"

    with tenant_context(tid):
        # For cancelled/no_show statuses, atomic_booking inserts without claiming
        # locks. For checked_out we must simulate the lifecycle: insert as
        # confirmed, then transition + release locks.
        if terminal_status in ("cancelled", "no_show"):
            first = _mk_booking_doc(tid, room_id, ci, co, status=terminal_status)
            await create_booking_atomic(first)
        else:
            first = _mk_booking_doc(tid, room_id, ci, co, status="confirmed")
            await create_booking_atomic(first)
            await db.bookings.update_one(
                {"id": first["id"], "tenant_id": tid},
                {"$set": {"status": terminal_status}},
            )
            await release_booking_nights(tid, first["id"], reason="test_setup")

        # Fresh booking on same window must succeed.
        fresh = _mk_booking_doc(tid, room_id, ci, co, status="confirmed")
        await create_booking_atomic(fresh)

        count = await db.bookings.count_documents(
            {"tenant_id": tid, "room_id": room_id, "status": "confirmed"}
        )
    assert count == 1


async def test_d_concurrent_parallel_inserts_exactly_one_wins(isolated_tenant):
    """5 parallel inserts on same room/dates → exactly 1 success, 4 conflicts."""
    from core.atomic_booking import (
        BookingConflictError,
        create_booking_atomic,
    )

    from core.tenant_db import tenant_context

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:12]}"
    ci, co = "2030-09-10", "2030-09-12"

    docs = [_mk_booking_doc(tid, room_id, ci, co) for _ in range(5)]

    async def attempt(doc):
        with tenant_context(tid):
            try:
                await create_booking_atomic(doc)
                return ("ok", doc["id"])
            except BookingConflictError as e:
                return ("conflict", e.conflicting_booking_id)
            except Exception as e:  # surface unexpected types in assertion
                return ("error", repr(e))

    results = await asyncio.gather(*(attempt(d) for d in docs))
    successes = [r for r in results if r[0] == "ok"]
    conflicts = [r for r in results if r[0] == "conflict"]
    errors = [r for r in results if r[0] == "error"]

    assert errors == [], f"Unexpected errors: {errors}"
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
    assert len(conflicts) == 4, f"Expected 4 conflicts, got {len(conflicts)}: {results}"


async def test_e_overlap_helper_excludes_terminal_states(isolated_tenant):
    """`_find_overlapping_active_booking` must ignore terminal-state docs."""
    from core.atomic_booking import _find_overlapping_active_booking
    from core.database import db

    from core.tenant_db import tenant_context

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:12]}"
    ci, co = "2030-10-01", "2030-10-05"

    with tenant_context(tid):
        # Seed two terminal bookings directly (bypassing atomic helper).
        await db.bookings.insert_many([
            _mk_booking_doc(tid, room_id, ci, co, status="cancelled"),
            _mk_booking_doc(tid, room_id, ci, co, status="no_show"),
            _mk_booking_doc(tid, room_id, ci, co, status="checked_out"),
        ])

        # No active booking → helper returns None.
        found = await _find_overlapping_active_booking(
            tenant_id=tid, room_id=room_id, check_in=ci, check_out=co,
        )
        assert found is None, f"Terminal-state seed should not block: {found}"

        # Add an active overlap → helper finds it.
        active = _mk_booking_doc(tid, room_id, "2030-10-03", "2030-10-07", status="confirmed")
        await db.bookings.insert_one(active)
        found = await _find_overlapping_active_booking(
            tenant_id=tid, room_id=room_id, check_in=ci, check_out=co,
        )
    assert found is not None
    assert found["id"] == active["id"]


async def test_f_defense_in_depth_blocks_legacy_seed_overlap(isolated_tenant):
    """Bookings inserted *bypassing* the atomic helper (no RNL rows) must
    still be detected by the bookings-level overlap guard.

    This is the exact F8N CI failure pattern: stress seed inserted a booking
    via raw `insert_many` but the unique RNL index was missing, so the
    subsequent atomic create could not detect the conflict via locks alone.
    The defense-in-depth bookings overlap check catches it.
    """
    from core.atomic_booking import BookingConflictError, create_booking_atomic
    from core.database import db

    from core.tenant_db import tenant_context

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:12]}"
    ci, co = "2030-11-10", "2030-11-14"

    with tenant_context(tid):
        # Simulate seed: direct insert, NO room_night_locks rows.
        seeded = _mk_booking_doc(tid, room_id, ci, co, status="checked_in")
        await db.bookings.insert_one(seeded)

        fresh = _mk_booking_doc(tid, room_id, ci, co, status="confirmed")
        with pytest.raises(BookingConflictError) as exc:
            await create_booking_atomic(fresh)
    assert exc.value.conflicting_booking_id == seeded["id"]
