"""
Runtime Stress Tests — Mobile Concurrency
Simulates concurrent mobile operations: no-show processing, room changes,
quick tasks, and quick issues hitting the database at the same time.
"""
import asyncio
import pytest
import uuid
from datetime import datetime, timezone, timedelta


async def test_concurrent_no_show_processing(db):
    """Process 20 no-shows concurrently."""
    tid = f"stress-noshow-{uuid.uuid4().hex[:8]}"

    booking_ids = []
    for i in range(20):
        bid = str(uuid.uuid4())
        booking_ids.append(bid)
        await db.bookings.insert_one({
            "id": bid,
            "tenant_id": tid,
            "guest_id": f"guest-{i}",
            "room_id": f"room-{i}",
            "status": "confirmed",
            "check_in": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "check_out": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def process_no_show(bid):
        result = await db.bookings.update_one(
            {"id": bid, "tenant_id": tid, "status": "confirmed"},
            {"$set": {"status": "no_show", "no_show_at": datetime.now(timezone.utc).isoformat()}},
        )
        return result.modified_count > 0

    tasks = [process_no_show(bid) for bid in booking_ids]
    results = await asyncio.gather(*tasks)
    assert sum(results) == 20

    no_shows = await db.bookings.count_documents({"tenant_id": tid, "status": "no_show"})
    assert no_shows == 20

    await db.bookings.delete_many({"tenant_id": tid})


async def test_concurrent_room_changes(db):
    """Multiple room changes executing at the same time."""
    tid = f"stress-roomchg-{uuid.uuid4().hex[:8]}"

    rooms = []
    for i in range(10):
        rid = str(uuid.uuid4())
        rooms.append(rid)
        await db.rooms.insert_one({
            "id": rid, "tenant_id": tid,
            "room_number": f"R-{200 + i}", "status": "available",
        })

    booking_ids = []
    for i in range(5):
        bid = str(uuid.uuid4())
        booking_ids.append(bid)
        await db.bookings.insert_one({
            "id": bid, "tenant_id": tid, "guest_id": f"g-{i}",
            "room_id": rooms[i], "status": "checked_in",
            "check_in": datetime.now(timezone.utc).isoformat(),
            "check_out": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        })

    async def change_room(bid, new_room_id):
        booking = await db.bookings.find_one({"id": bid})
        old_room_id = booking["room_id"]
        await db.rooms.update_one({"id": old_room_id}, {"$set": {"status": "dirty"}})
        await db.rooms.update_one({"id": new_room_id}, {"$set": {"status": "occupied"}})
        await db.bookings.update_one({"id": bid}, {"$set": {"room_id": new_room_id}})
        return True

    tasks = [change_room(booking_ids[i], rooms[5 + i]) for i in range(5)]
    results = await asyncio.gather(*tasks)
    assert all(results)

    await db.rooms.delete_many({"tenant_id": tid})
    await db.bookings.delete_many({"tenant_id": tid})


async def test_quick_task_burst(db):
    """Create 30 quick housekeeping tasks concurrently."""
    tid = f"stress-task-{uuid.uuid4().hex[:8]}"

    async def create_task(idx):
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "room_id": f"room-{idx % 10}",
            "task_type": "cleaning" if idx % 2 == 0 else "minibar",
            "priority": "high" if idx % 3 == 0 else "normal",
            "status": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.housekeeping_tasks.insert_one(task)
        return task

    tasks = [create_task(i) for i in range(30)]
    results = await asyncio.gather(*tasks)
    assert len(results) == 30

    count = await db.housekeeping_tasks.count_documents({"tenant_id": tid})
    assert count == 30

    await db.housekeeping_tasks.delete_many({"tenant_id": tid})


async def test_concurrent_quick_issues(db):
    """Create 20 maintenance issues concurrently from mobile."""
    tid = f"stress-issue-{uuid.uuid4().hex[:8]}"

    async def create_issue(idx):
        issue = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "room_id": f"room-{idx % 10}",
            "issue_type": ["plumbing", "electrical", "hvac", "other"][idx % 4],
            "description": f"Issue from mobile staff {idx}",
            "priority": "urgent" if idx % 5 == 0 else "normal",
            "status": "open",
            "reported_by": f"staff-{idx % 5}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.tasks.insert_one(issue)
        return issue

    tasks = [create_issue(i) for i in range(20)]
    results = await asyncio.gather(*tasks)
    assert len(results) == 20

    count = await db.tasks.count_documents({"tenant_id": tid})
    assert count >= 20

    await db.tasks.delete_many({"tenant_id": tid})
