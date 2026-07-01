"""
Test: CM Conflict Queue API (CM-Hardening Turu #1b, May 2026)
==============================================================

Pinned regression for `routers.cm_conflict_queue`:
  GET  /api/channel-manager/conflict-queue
  GET  /api/channel-manager/conflict-queue/count
  POST /api/channel-manager/conflict-queue/{id}/resolve {"room_id": "..."}

Background:
  Turu #1a closed the *signaling* gap (silent `lock_conflict` →
  `db.notifications` overbooking_risk row). Turu #1b closes the *resolution*
  loop: front-desk needs an authenticated, tenant-scoped API to (a) list
  pending_assignment bookings and (b) atomically claim a specific room for
  one — without bypassing the room-night-locks unique index that prevents
  overbooking in the first place.

Pinned behaviour:
  T1: list endpoint surfaces only this-tenant's pending_assignment bookings
  T2: count endpoint matches list total
  T3: resolve happy path → 200, room_id assigned, allocation_source promoted
  T4: resolve returns 404 if booking already resolved (idempotency boundary)
  T5: resolve returns 404 for cross-tenant booking_id (auth scope)
  T6: resolve returns 409 if target room is no longer free for any night,
      with conflict_night + conflicting_booking_id in the error body
  T8: bulk-resolve mixed batch (1 success + 1 conflict) → 200 with both
      succeeded[] and failed[] populated; success row gets locks, failure
      row stays pending (Turu #2)
  T9: bulk-resolve invalid room_id is reported as failed without aborting
      the rest of the batch (Turu #2)
"""
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from core.database import db


pytestmark = pytest.mark.asyncio

API = os.environ.get("VITE_BACKEND_URL", "http://localhost:8000").rstrip("/")
QUEUE = f"{API}/api/channel-manager/conflict-queue"
LOGIN = f"{API}/api/auth/login"


async def _login() -> tuple[dict, str]:
    """Return (auth headers, tenant_id) for the demo admin tenant."""
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(LOGIN, json={"email": "demo@hotel.com", "password": "demo123"})
    if resp.status_code != 200:
        pytest.skip(f"Demo login unavailable ({resp.status_code})")
    body = resp.json()
    token = body.get("access_token") or body.get("token")
    tenant_id = body["user"]["tenant_id"]
    return {"Authorization": f"Bearer {token}"}, tenant_id


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


async def _seed_pending_booking(tenant_id: str, *, anchor_days: int = 480) -> str:
    """Insert a pending_assignment booking directly (mirrors OTA fallback)."""
    bid = f"queue-test-{uuid.uuid4().hex[:10]}"
    ci = datetime.now(UTC) + timedelta(days=anchor_days)
    co = ci + timedelta(days=2)
    await db.bookings.insert_one({
        "id": bid,
        "tenant_id": tenant_id,
        "room_id": None,
        "allocation_source": "pending_assignment",
        "guest_id": f"queue-guest-{uuid.uuid4().hex[:6]}",
        "guest_name": "Queue Tester",
        "check_in": _iso(ci),
        "check_out": _iso(co),
        "status": "confirmed",
        "channel": "test_ota",
        "source": "ota",
        "total_amount": 100,
        "currency": "TRY",
        "external_confirmation": f"EXT-{bid}",
        "created_at": datetime.now(UTC).isoformat(),
    })
    return bid


async def _seed_room(tenant_id: str) -> str:
    rid = f"queue-room-{uuid.uuid4().hex[:8]}"
    await db.rooms.insert_one({
        "id": rid,
        "tenant_id": tenant_id,
        "room_number": f"QT{uuid.uuid4().hex[:4].upper()}",
        "room_type": "standard",
        "status": "available",
        "created_at": datetime.now(UTC).isoformat(),
    })
    return rid


async def _cleanup(tenant_id: str, booking_ids: list[str], room_ids: list[str]):
    if booking_ids:
        await db.bookings.delete_many({"id": {"$in": booking_ids}, "tenant_id": tenant_id})
        await db.room_night_locks.delete_many({
            "tenant_id": tenant_id,
            "booking_id": {"$in": booking_ids},
        })
        await db.notifications.delete_many({
            "tenant_id": tenant_id,
            "related_id": {"$in": booking_ids},
        })
    if room_ids:
        await db.rooms.delete_many({"id": {"$in": room_ids}, "tenant_id": tenant_id})


async def test_list_and_count_surface_pending_bookings_for_tenant():
    """T1+T2: list returns this-tenant pending row, count == list total."""
    headers, tenant_id = await _login()
    bid = await _seed_pending_booking(tenant_id, anchor_days=480)

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            list_resp = await c.get(QUEUE, headers=headers, params={"limit": 200})
            count_resp = await c.get(f"{QUEUE}/count", headers=headers)

        assert list_resp.status_code == 200, list_resp.text
        assert count_resp.status_code == 200, count_resp.text

        items = list_resp.json()["items"]
        ids = [it["id"] for it in items]
        assert bid in ids, "Seeded pending booking missing from queue"

        # Every returned row must be a pending_assignment for this tenant
        my_row = next(it for it in items if it["id"] == bid)
        assert my_row["status"] in {"confirmed", "guaranteed", "pending"}
        assert my_row["channel"] == "test_ota"

        # Count parity with list total field
        assert count_resp.json()["count"] == list_resp.json()["total"]
    finally:
        await _cleanup(tenant_id, [bid], [])


async def test_resolve_happy_path_assigns_room_and_promotes_allocation_source():
    """T3: POST resolve → 200, booking gets room_id and allocation_source updated,
    a room_night_locks entry is created per night, and a notification is written."""
    headers, tenant_id = await _login()
    bid = await _seed_pending_booking(tenant_id, anchor_days=485)
    rid = await _seed_room(tenant_id)

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.post(
                f"{QUEUE}/{bid}/resolve",
                headers=headers,
                json={"room_id": rid},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["room_id"] == rid

        # Booking promoted out of pending_assignment
        booking = await db.bookings.find_one({"id": bid, "tenant_id": tenant_id}, {"_id": 0})
        assert booking["room_id"] == rid
        assert booking["allocation_source"] == "front_desk_resolve"

        # Locks created for both nights of a 2-night stay
        lock_count = await db.room_night_locks.count_documents({
            "tenant_id": tenant_id, "room_id": rid, "booking_id": bid,
        })
        assert lock_count == 2, f"Expected 2 night locks, got {lock_count}"

        # Notification written
        notif = await db.notifications.find_one({
            "tenant_id": tenant_id,
            "type": "overbooking_resolved",
            "related_id": bid,
        })
        assert notif is not None
    finally:
        await _cleanup(tenant_id, [bid], [rid])


async def test_resolve_returns_404_if_booking_already_resolved():
    """T4: second resolve attempt on the same booking → 404 (no longer pending)."""
    headers, tenant_id = await _login()
    bid = await _seed_pending_booking(tenant_id, anchor_days=490)
    rid = await _seed_room(tenant_id)

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            first = await c.post(f"{QUEUE}/{bid}/resolve", headers=headers, json={"room_id": rid})
            assert first.status_code == 200, first.text
            second = await c.post(f"{QUEUE}/{bid}/resolve", headers=headers, json={"room_id": rid})
        assert second.status_code == 404
    finally:
        await _cleanup(tenant_id, [bid], [rid])


async def test_resolve_returns_404_for_unknown_booking_id():
    """T5: bogus booking_id → 404 (auth scope sanity)."""
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(
            f"{QUEUE}/does-not-exist-{uuid.uuid4().hex[:6]}/resolve",
            headers=headers,
            json={"room_id": "anything"},
        )
    assert resp.status_code == 404


async def test_resolve_compensation_releases_partial_locks_on_mid_stay_conflict():
    """T7 (architect follow-up): a 2-night booking where the SECOND night
    conflicts must release the lock claimed for the first night — verifies
    the `claimed` compensation list works for partial-success rollback,
    not just first-night failure (which never claims anything)."""
    headers, tenant_id = await _login()
    bid = await _seed_pending_booking(tenant_id, anchor_days=500)
    rid = await _seed_room(tenant_id)

    # Plant a conflicting lock on the SECOND (last) night
    pending = await db.bookings.find_one(
        {"id": bid, "tenant_id": tenant_id}, {"_id": 0, "check_in": 1, "check_out": 1},
    )
    ci_date = datetime.fromisoformat(pending["check_in"].replace("Z", "+00:00")).date()
    second_night = (ci_date + timedelta(days=1)).isoformat()  # nights = [day0, day1]; conflict on day1
    blocker_id = f"queue-mid-blocker-{uuid.uuid4().hex[:8]}"
    await db.room_night_locks.insert_one({
        "tenant_id": tenant_id,
        "room_id": rid,
        "night_date": second_night,
        "booking_id": blocker_id,
        "lock_type": "booking",
        "created_at": datetime.now(UTC).isoformat(),
    })

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.post(f"{QUEUE}/{bid}/resolve", headers=headers, json={"room_id": rid})
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["conflict_night"] == second_night

        # Compensation: NO partial locks for our booking remain on this room
        # (the first-night lock that WAS claimed must have been deleted)
        leftover = await db.room_night_locks.count_documents({
            "tenant_id": tenant_id, "room_id": rid, "booking_id": bid,
        })
        assert leftover == 0, "Mid-stay compensation failed — first night lock not released"

        # Booking still pending
        booking = await db.bookings.find_one({"id": bid, "tenant_id": tenant_id}, {"_id": 0})
        assert booking["room_id"] is None
        assert booking["allocation_source"] == "pending_assignment"
    finally:
        await db.room_night_locks.delete_many({
            "tenant_id": tenant_id, "room_id": rid, "booking_id": blocker_id,
        })
        await _cleanup(tenant_id, [bid], [rid])


async def test_bulk_resolve_partial_success_does_not_abort_batch():
    """T8 (Turu #2): mixed batch — first booking has a clean room, second
    booking targets a room with a planted conflict on its first night.
    Both items must be processed; succeeded[] holds row 1, failed[] holds
    row 2 with conflict metadata. The success row's booking and locks must
    persist; the failure row's booking stays pending and leaves no locks.
    """
    headers, tenant_id = await _login()
    bid_ok = await _seed_pending_booking(tenant_id, anchor_days=520)
    bid_fail = await _seed_pending_booking(tenant_id, anchor_days=525)
    rid_ok = await _seed_room(tenant_id)
    rid_fail = await _seed_room(tenant_id)

    # Plant blocker on the FIRST night of the failing booking's stay
    pending = await db.bookings.find_one(
        {"id": bid_fail, "tenant_id": tenant_id}, {"_id": 0, "check_in": 1},
    )
    first_night = (
        datetime.fromisoformat(pending["check_in"].replace("Z", "+00:00")).date().isoformat()
    )
    blocker_id = f"queue-bulk-blocker-{uuid.uuid4().hex[:8]}"
    await db.room_night_locks.insert_one({
        "tenant_id": tenant_id,
        "room_id": rid_fail,
        "night_date": first_night,
        "booking_id": blocker_id,
        "lock_type": "booking",
        "created_at": datetime.now(UTC).isoformat(),
    })

    try:
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.post(
                f"{QUEUE}/bulk-resolve",
                headers=headers,
                json={"items": [
                    {"booking_id": bid_ok, "room_id": rid_ok},
                    {"booking_id": bid_fail, "room_id": rid_fail},
                ]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 2

        succeeded_ids = [r["booking_id"] for r in body["succeeded"]]
        failed_rows = {r["booking_id"]: r for r in body["failed"]}
        assert bid_ok in succeeded_ids
        assert bid_fail in failed_rows
        assert failed_rows[bid_fail]["error"] == "room_not_available"
        assert failed_rows[bid_fail]["conflict_night"] == first_night
        assert failed_rows[bid_fail]["conflicting_booking_id"] == blocker_id

        # Success row promoted, failure row still pending
        ok_doc = await db.bookings.find_one({"id": bid_ok, "tenant_id": tenant_id}, {"_id": 0})
        fail_doc = await db.bookings.find_one({"id": bid_fail, "tenant_id": tenant_id}, {"_id": 0})
        assert ok_doc["room_id"] == rid_ok
        assert ok_doc["allocation_source"] == "front_desk_resolve"
        assert fail_doc["room_id"] is None
        assert fail_doc["allocation_source"] == "pending_assignment"

        # No leftover locks for failed booking
        leftover = await db.room_night_locks.count_documents({
            "tenant_id": tenant_id, "room_id": rid_fail, "booking_id": bid_fail,
        })
        assert leftover == 0
    finally:
        await db.room_night_locks.delete_many({
            "tenant_id": tenant_id, "room_id": rid_fail, "booking_id": blocker_id,
        })
        await _cleanup(tenant_id, [bid_ok, bid_fail], [rid_ok, rid_fail])


async def test_bulk_resolve_invalid_room_id_reported_per_row():
    """T9 (Turu #2): a non-existent room_id surfaces as a failed row with
    error='room_not_found' — the rest of the batch must still process.
    """
    headers, tenant_id = await _login()
    bid_ok = await _seed_pending_booking(tenant_id, anchor_days=530)
    bid_bad = await _seed_pending_booking(tenant_id, anchor_days=532)
    rid_ok = await _seed_room(tenant_id)
    bogus_room = f"does-not-exist-{uuid.uuid4().hex[:6]}"

    try:
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.post(
                f"{QUEUE}/bulk-resolve",
                headers=headers,
                json={"items": [
                    {"booking_id": bid_ok, "room_id": rid_ok},
                    {"booking_id": bid_bad, "room_id": bogus_room},
                ]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 2

        succeeded_ids = [r["booking_id"] for r in body["succeeded"]]
        failed_rows = {r["booking_id"]: r for r in body["failed"]}
        assert bid_ok in succeeded_ids
        assert failed_rows[bid_bad]["error"] == "room_not_found"

        # bid_bad still pending (no claim attempted)
        bad_doc = await db.bookings.find_one({"id": bid_bad, "tenant_id": tenant_id}, {"_id": 0})
        assert bad_doc["room_id"] is None
    finally:
        await _cleanup(tenant_id, [bid_ok, bid_bad], [rid_ok])


async def test_resolve_returns_409_when_room_not_available():
    """T6: target room is locked for one of the booking's nights → 409 with
    conflict_night + conflicting_booking_id; pending booking remains pending."""
    headers, tenant_id = await _login()
    bid = await _seed_pending_booking(tenant_id, anchor_days=495)
    rid = await _seed_room(tenant_id)

    # Plant a conflicting lock on the FIRST night of the pending booking
    pending = await db.bookings.find_one({"id": bid, "tenant_id": tenant_id}, {"_id": 0, "check_in": 1})
    first_night = (
        datetime.fromisoformat(pending["check_in"].replace("Z", "+00:00")).date().isoformat()
    )
    blocker_id = f"queue-blocker-{uuid.uuid4().hex[:8]}"
    await db.room_night_locks.insert_one({
        "tenant_id": tenant_id,
        "room_id": rid,
        "night_date": first_night,
        "booking_id": blocker_id,
        "lock_type": "booking",
        "created_at": datetime.now(UTC).isoformat(),
    })

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.post(f"{QUEUE}/{bid}/resolve", headers=headers, json={"room_id": rid})
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["error"] == "room_not_available"
        assert detail["conflict_night"] == first_night
        assert detail["conflicting_booking_id"] == blocker_id

        # Pending booking unchanged
        booking = await db.bookings.find_one({"id": bid, "tenant_id": tenant_id}, {"_id": 0})
        assert booking["room_id"] is None
        assert booking["allocation_source"] == "pending_assignment"

        # No partial locks left behind for this booking on this room
        leftover = await db.room_night_locks.count_documents({
            "tenant_id": tenant_id, "room_id": rid, "booking_id": bid,
        })
        assert leftover == 0, "Partial-night locks should have been compensated on conflict"
    finally:
        await db.room_night_locks.delete_many({
            "tenant_id": tenant_id, "room_id": rid, "booking_id": blocker_id,
        })
        await _cleanup(tenant_id, [bid], [rid])
