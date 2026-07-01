"""F8N Task #222 — Auto-resolve duplicate room-night lock rows.

Direct DB-level tests for `list_room_night_lock_duplicate_groups` and
`resolve_room_night_lock_duplicates`. Skips automatically when MongoDB is
not reachable (conftest fixture binds Motor to the session event loop).
"""
import uuid
from datetime import UTC, datetime

import pytest


pytestmark = pytest.mark.asyncio

TEST_TENANT_PREFIX = "f8n_rnl_resolve_test_"


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


async def _cleanup(tenant_id: str) -> None:
    from core.database import db
    from core.tenant_db import audit_retention_context
    await db.bookings.delete_many({"tenant_id": tenant_id})
    await db.room_night_locks.delete_many({"tenant_id": tenant_id})
    # audit_logs is append-only (Task #568); test teardown uses the sanctioned escape.
    with audit_retention_context():
        await db.audit_logs.delete_many({"tenant_id": tenant_id})


@pytest.fixture
async def isolated_tenant():
    tid = f"{TEST_TENANT_PREFIX}{_ts()}_{uuid.uuid4().hex[:8]}"
    yield tid
    try:
        await _cleanup(tid)
    except Exception:
        pass


async def _seed_lock(tenant_id, room_id, night, booking_id, lock_type="booking"):
    from core.database import db
    await db.room_night_locks.insert_one({
        "tenant_id": tenant_id,
        "room_id": room_id,
        "night_date": night,
        "booking_id": booking_id,
        "lock_type": lock_type,
        "created_at": datetime.now(UTC).isoformat(),
    })


async def _seed_booking(tenant_id, booking_id, status):
    from core.database import db
    await db.bookings.insert_one({
        "id": booking_id,
        "tenant_id": tenant_id,
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
    })


async def test_auto_safe_keeps_active_retires_terminal(isolated_tenant):
    """One active + one cancelled booking on same night → auto_safe."""
    from core.atomic_booking import (
        list_room_night_lock_duplicate_groups,
        resolve_room_night_lock_duplicates,
    )
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-09-10"
    active_id = str(uuid.uuid4())
    cancelled_id = str(uuid.uuid4())

    await _seed_booking(tid, active_id, "confirmed")
    await _seed_booking(tid, cancelled_id, "cancelled")
    await _seed_lock(tid, room_id, night, active_id)
    await _seed_lock(tid, room_id, night, cancelled_id)

    plan = await list_room_night_lock_duplicate_groups(limit=50)
    mine = [g for g in plan if g["tenant_id"] == tid]
    assert len(mine) == 1
    assert mine[0]["recommendation"] == "auto_safe"
    assert mine[0]["keep_booking_id"] == active_id
    assert mine[0]["retire_booking_ids"] == [cancelled_id]

    dry = await resolve_room_night_lock_duplicates(apply=False, limit=50)
    assert dry["applied"] is False
    assert any(r["tenant_id"] == tid for r in dry["resolved"])
    remaining = await db.room_night_locks.count_documents(
        {"tenant_id": tid, "room_id": room_id, "night_date": night}
    )
    assert remaining == 2  # dry-run did not delete

    applied = await resolve_room_night_lock_duplicates(
        apply=True, limit=50, actor_id="test", actor_name="test", actor_role="super_admin",
    )
    assert applied["applied"] is True
    assert applied["resolved_count"] >= 1

    remaining = await db.room_night_locks.find(
        {"tenant_id": tid, "room_id": room_id, "night_date": night},
        {"_id": 0, "booking_id": 1},
    ).to_list(10)
    assert len(remaining) == 1
    assert remaining[0]["booking_id"] == active_id

    audit = await db.audit_logs.find_one(
        {"tenant_id": tid, "action": "AUTO_RESOLVE_RNL_DUPLICATE"}
    )
    assert audit is not None
    assert audit["changes"]["keep_booking_id"] == active_id
    assert cancelled_id in audit["changes"]["retire_booking_ids"]


async def test_manual_required_two_active_bookings(isolated_tenant):
    from core.atomic_booking import (
        list_room_night_lock_duplicate_groups,
        resolve_room_night_lock_duplicates,
    )
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-09-11"
    a, b = str(uuid.uuid4()), str(uuid.uuid4())

    await _seed_booking(tid, a, "confirmed")
    await _seed_booking(tid, b, "checked_in")
    await _seed_lock(tid, room_id, night, a)
    await _seed_lock(tid, room_id, night, b)

    plan = await list_room_night_lock_duplicate_groups(limit=50)
    mine = [g for g in plan if g["tenant_id"] == tid][0]
    assert mine["recommendation"] == "manual_required"
    assert mine["keep_booking_id"] is None

    res = await resolve_room_night_lock_duplicates(apply=True, limit=50)
    skipped_ids = [s["tenant_id"] for s in res["skipped"]]
    assert tid in skipped_ids
    remaining = await db.room_night_locks.count_documents(
        {"tenant_id": tid, "room_id": room_id, "night_date": night}
    )
    assert remaining == 2  # nothing deleted


async def test_auto_safe_all_inactive_keeps_one(isolated_tenant):
    """All cancelled → keep most recent for audit, retire rest."""
    from core.atomic_booking import resolve_room_night_lock_duplicates
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-09-12"
    a, b = str(uuid.uuid4()), str(uuid.uuid4())

    await _seed_booking(tid, a, "cancelled")
    await _seed_booking(tid, b, "no_show")
    await _seed_lock(tid, room_id, night, a)
    await _seed_lock(tid, room_id, night, b)

    res = await resolve_room_night_lock_duplicates(apply=True, limit=50)
    resolved = [r for r in res["resolved"] if r["tenant_id"] == tid]
    assert resolved
    assert resolved[0]["recommendation"] == "auto_safe_all_inactive"
    remaining = await db.room_night_locks.count_documents(
        {"tenant_id": tid, "room_id": room_id, "night_date": night}
    )
    assert remaining == 1


async def test_manual_resolve_keeps_chosen_booking(isolated_tenant):
    """Operator-driven manual_resolve deletes only the retired locks,
    leaves the keeper's lock intact, and writes an audit row."""
    from core.atomic_booking import (
        list_room_night_lock_duplicate_groups,
        manual_resolve_room_night_lock_duplicate,
    )
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-10-01"
    keep, retire = str(uuid.uuid4()), str(uuid.uuid4())

    await _seed_booking(tid, keep, "confirmed")
    await _seed_booking(tid, retire, "checked_in")
    await _seed_lock(tid, room_id, night, keep)
    await _seed_lock(tid, room_id, night, retire)

    plan = await list_room_night_lock_duplicate_groups(limit=50)
    mine = [g for g in plan if g["tenant_id"] == tid][0]
    assert mine["recommendation"] == "manual_required"

    res = await manual_resolve_room_night_lock_duplicate(
        tenant_id=tid, room_id=room_id, night_date=night,
        keep_booking_id=keep, retire_booking_ids=[retire],
        actor_id="op1", actor_name="op1", actor_role="super_admin",
    )
    assert res["applied"] is True
    assert res["deleted_count"] == 1
    assert res["remaining"] == 1

    remaining = await db.room_night_locks.find(
        {"tenant_id": tid, "room_id": room_id, "night_date": night},
        {"_id": 0, "booking_id": 1},
    ).to_list(10)
    assert len(remaining) == 1
    assert remaining[0]["booking_id"] == keep

    audit = await db.audit_logs.find_one(
        {"tenant_id": tid, "action": "MANUAL_RESOLVE_RNL_DUPLICATE"}
    )
    assert audit is not None
    assert audit["changes"]["keep_booking_id"] == keep
    assert retire in audit["changes"]["retire_booking_ids"]


async def test_manual_resolve_guards_reject_invalid_input(isolated_tenant):
    """Guards: keeper in retire list, retire without matching lock, empty
    retire list — all must skip cleanly without deleting anything."""
    from core.atomic_booking import manual_resolve_room_night_lock_duplicate
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-10-02"
    keep, retire = str(uuid.uuid4()), str(uuid.uuid4())
    bogus = str(uuid.uuid4())

    await _seed_lock(tid, room_id, night, keep)
    await _seed_lock(tid, room_id, night, retire)

    # keeper cannot also be retired
    r1 = await manual_resolve_room_night_lock_duplicate(
        tenant_id=tid, room_id=room_id, night_date=night,
        keep_booking_id=keep, retire_booking_ids=[keep],
    )
    assert r1["applied"] is False
    assert "cannot also be retired" in r1["skip_reason"]

    # retire booking_id without a lock on this triple
    r2 = await manual_resolve_room_night_lock_duplicate(
        tenant_id=tid, room_id=room_id, night_date=night,
        keep_booking_id=keep, retire_booking_ids=[bogus],
    )
    assert r2["applied"] is False
    assert "not present" in r2["skip_reason"]

    # empty retire list
    r3 = await manual_resolve_room_night_lock_duplicate(
        tenant_id=tid, room_id=room_id, night_date=night,
        keep_booking_id=keep, retire_booking_ids=[],
    )
    assert r3["applied"] is False

    # nothing deleted
    cnt = await db.room_night_locks.count_documents(
        {"tenant_id": tid, "room_id": room_id, "night_date": night}
    )
    assert cnt == 2


async def test_block_owner_treated_as_keeper(isolated_tenant):
    """OOO:/OOS:/MAINT: prefixed locks are always keepers."""
    from core.atomic_booking import list_room_night_lock_duplicate_groups
    from core.database import db  # noqa: F401

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-09-13"
    cancelled_id = str(uuid.uuid4())
    await _seed_booking(tid, cancelled_id, "cancelled")
    await _seed_lock(tid, room_id, night, f"OOO:{room_id}", lock_type="ooo")
    await _seed_lock(tid, room_id, night, cancelled_id)

    plan = await list_room_night_lock_duplicate_groups(limit=50)
    mine = [g for g in plan if g["tenant_id"] == tid][0]
    assert mine["recommendation"] == "auto_safe"
    assert mine["keep_booking_id"] == f"OOO:{room_id}"
    assert mine["retire_booking_ids"] == [cancelled_id]
