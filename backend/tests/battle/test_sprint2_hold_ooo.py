"""
Sprint 2 — Booking Hold TTL + OOO/OOS Integration Tests
=========================================================
Tests for:
  - TTL/Hold mechanism (create, confirm, release, expiry)
  - OOO/OOS INV-5 integration (PMS blocks write to room_night_locks)
  - Cross-check: blocked room rejects bookings
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from core.database import _raw_db as raw_db, db
from core.tenant_db import set_tenant_context, clear_tenant_context

TENANT_ID = "test-sprint2-tenant"


@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    """Clean up test data before and after each test.

    Uses raw_db for cleanup (bypasses TenantAwareDBProxy) and sets
    tenant context for the test body so service functions and direct
    db access via the proxy both work correctly.
    """
    await raw_db.room_night_locks.delete_many({"tenant_id": TENANT_ID})
    await raw_db.bookings.delete_many({"tenant_id": TENANT_ID})
    set_tenant_context(TENANT_ID)
    yield
    clear_tenant_context()
    await raw_db.room_night_locks.delete_many({"tenant_id": TENANT_ID})
    await raw_db.bookings.delete_many({"tenant_id": TENANT_ID})


# ── Hold Creation Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hold_create_basic():
    """Hold should claim room-night locks with expiry."""
    from core.booking_hold_service import create_booking_hold

    result = await create_booking_hold(
        tenant_id=TENANT_ID,
        booking_id="hold-test-001",
        room_id="room-A",
        check_in="2026-05-01",
        check_out="2026-05-03",
        ttl_minutes=10,
    )

    assert result["success"] is True
    assert len(result["nights_held"]) == 2
    assert "2026-05-01" in result["nights_held"]
    assert "2026-05-02" in result["nights_held"]
    assert result["ttl_minutes"] == 10

    # Verify locks exist in DB with hold type
    locks = await db.room_night_locks.find(
        {"tenant_id": TENANT_ID, "booking_id": "hold-test-001"},
        {"_id": 0},
    ).to_list(10)
    assert len(locks) == 2
    assert all(l["lock_type"] == "hold" for l in locks)
    assert all("hold_expires_at" in l for l in locks)


@pytest.mark.asyncio
async def test_hold_blocks_booking():
    """A hold should prevent another booking from claiming the same nights."""
    from core.booking_hold_service import create_booking_hold

    # First hold succeeds
    r1 = await create_booking_hold(
        tenant_id=TENANT_ID,
        booking_id="hold-first",
        room_id="room-B",
        check_in="2026-05-10",
        check_out="2026-05-12",
    )
    assert r1["success"] is True

    # Second hold on same room+dates fails
    r2 = await create_booking_hold(
        tenant_id=TENANT_ID,
        booking_id="hold-second",
        room_id="room-B",
        check_in="2026-05-10",
        check_out="2026-05-12",
    )
    assert r2["success"] is False
    assert "not available" in r2.get("error", "")


@pytest.mark.asyncio
async def test_hold_blocks_regular_booking():
    """A hold should prevent a regular booking from claiming the same room."""
    from core.booking_hold_service import create_booking_hold
    from core.atomic_booking import create_booking_atomic, BookingConflictError

    # Create a hold first
    await create_booking_hold(
        tenant_id=TENANT_ID,
        booking_id="hold-blocker",
        room_id="room-C",
        check_in="2026-06-01",
        check_out="2026-06-03",
    )

    # Try to create a regular booking — should be blocked
    booking_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "room_id": "room-C",
        "check_in": "2026-06-01",
        "check_out": "2026-06-03",
        "status": "confirmed",
        "guest_id": "guest-x",
        "_version": 1,
    }
    with pytest.raises(BookingConflictError):
        await create_booking_atomic(booking_doc)


# ── Hold Confirm Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hold_confirm():
    """Confirming a hold should upgrade locks from 'hold' to 'booking' and remove expiry."""
    from core.booking_hold_service import create_booking_hold, confirm_hold

    await create_booking_hold(
        tenant_id=TENANT_ID,
        booking_id="hold-confirm-001",
        room_id="room-D",
        check_in="2026-05-15",
        check_out="2026-05-17",
    )

    result = await confirm_hold(TENANT_ID, "hold-confirm-001")
    assert result["success"] is True
    assert result["confirmed_count"] == 2

    # Verify locks are now type=booking with no expiry
    locks = await db.room_night_locks.find(
        {"tenant_id": TENANT_ID, "booking_id": "hold-confirm-001"},
        {"_id": 0},
    ).to_list(10)
    assert len(locks) == 2
    assert all(l["lock_type"] == "booking" for l in locks)
    assert all("hold_expires_at" not in l for l in locks)


# ── Hold Release Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hold_manual_release():
    """Manually releasing a hold should free room-night locks."""
    from core.booking_hold_service import create_booking_hold, release_hold

    await create_booking_hold(
        tenant_id=TENANT_ID,
        booking_id="hold-release-001",
        room_id="room-E",
        check_in="2026-05-20",
        check_out="2026-05-22",
    )

    result = await release_hold(TENANT_ID, "hold-release-001", reason="user_cancelled")
    assert result["success"] is True
    assert result["released_count"] == 2

    # Verify locks are gone
    count = await db.room_night_locks.count_documents(
        {"tenant_id": TENANT_ID, "booking_id": "hold-release-001"}
    )
    assert count == 0


# ── Hold Expiry/Sweep Tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_hold_sweep_expired():
    """Sweeper should auto-release expired holds."""
    from core.booking_hold_service import sweep_expired_holds

    # Insert a hold with already-expired TTL
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    for night in ["2026-07-01", "2026-07-02"]:
        await db.room_night_locks.insert_one({
            "tenant_id": TENANT_ID,
            "room_id": "room-F",
            "night_date": night,
            "booking_id": "hold-expired-001",
            "lock_type": "hold",
            "hold_expires_at": past,
            "created_at": past,
        })

    # Also create a pending booking for it
    await db.bookings.insert_one({
        "id": "hold-expired-001",
        "tenant_id": TENANT_ID,
        "room_id": "room-F",
        "status": "pending",
        "check_in": "2026-07-01",
        "check_out": "2026-07-03",
    })

    result = await sweep_expired_holds()
    assert result["expired_count"] == 2
    assert result["bookings_affected"] == 1

    # Verify locks are gone
    count = await db.room_night_locks.count_documents(
        {"tenant_id": TENANT_ID, "booking_id": "hold-expired-001"}
    )
    assert count == 0

    # Verify booking status changed
    booking = await db.bookings.find_one(
        {"id": "hold-expired-001", "tenant_id": TENANT_ID},
        {"_id": 0, "status": 1},
    )
    assert booking["status"] == "hold_expired"


@pytest.mark.asyncio
async def test_hold_sweep_does_not_touch_confirmed():
    """Sweeper should NOT touch confirmed booking locks (only holds)."""
    from core.booking_hold_service import sweep_expired_holds

    # Insert a confirmed lock (lock_type=booking, no hold_expires_at)
    await db.room_night_locks.insert_one({
        "tenant_id": TENANT_ID,
        "room_id": "room-G",
        "night_date": "2026-08-01",
        "booking_id": "confirmed-booking-001",
        "lock_type": "booking",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    result = await sweep_expired_holds()
    assert result["expired_count"] == 0

    # Verify confirmed lock still exists
    count = await db.room_night_locks.count_documents(
        {"tenant_id": TENANT_ID, "booking_id": "confirmed-booking-001"}
    )
    assert count == 1


# ── OOO/OOS INV-5 Integration Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_ooo_block_writes_to_room_night_locks():
    """Applying an OOO block should write to room_night_locks."""
    from core.atomic_booking import apply_room_block

    result = await apply_room_block(
        tenant_id=TENANT_ID,
        room_id="room-H",
        block_type="ooo",
        start_date="2026-09-01",
        end_date="2026-09-03",
        reason="Water leak",
        actor="test-user",
    )

    assert result["success"] is True
    assert len(result["nights_blocked"]) == 2

    # Verify locks exist
    locks = await db.room_night_locks.find(
        {"tenant_id": TENANT_ID, "room_id": "room-H", "lock_type": "ooo"},
        {"_id": 0},
    ).to_list(10)
    assert len(locks) == 2


@pytest.mark.asyncio
async def test_ooo_block_prevents_booking():
    """A room with an OOO block should reject booking attempts."""
    from core.atomic_booking import apply_room_block, create_booking_atomic, BookingConflictError

    await apply_room_block(
        tenant_id=TENANT_ID,
        room_id="room-I",
        block_type="oos",
        start_date="2026-10-01",
        end_date="2026-10-03",
        reason="Renovation",
    )

    booking_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "room_id": "room-I",
        "check_in": "2026-10-01",
        "check_out": "2026-10-03",
        "status": "confirmed",
        "guest_id": "guest-y",
        "_version": 1,
    }
    with pytest.raises(BookingConflictError) as exc_info:
        await create_booking_atomic(booking_doc)
    assert exc_info.value.conflict_type == "oos"


@pytest.mark.asyncio
async def test_ooo_release_frees_room():
    """Releasing an OOO block should allow new bookings."""
    from core.atomic_booking import apply_room_block, release_room_block, create_booking_atomic

    await apply_room_block(
        tenant_id=TENANT_ID,
        room_id="room-J",
        block_type="maintenance",
        start_date="2026-11-01",
        end_date="2026-11-03",
        reason="AC repair",
    )

    # Release the block
    release_result = await release_room_block(
        tenant_id=TENANT_ID,
        room_id="room-J",
        block_type="maintenance",
        start_date="2026-11-01",
        end_date="2026-11-03",
    )
    assert release_result["released_count"] == 2

    # Now booking should succeed
    booking_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "room_id": "room-J",
        "check_in": "2026-11-01",
        "check_out": "2026-11-03",
        "status": "confirmed",
        "guest_id": "guest-z",
        "_version": 1,
    }
    result = await create_booking_atomic(booking_doc)
    assert result["status"] == "confirmed"
