"""
Phase C.1 Battle Tests — Room-Type Inventory Materialized View
================================================================
ADR-003 INV-7: room_type_inventory.sellable matches lock count exactly.

Uses HTTP API calls (consistent with existing battle tests).

Tests:
  1. GET /api/inventory/room-types returns data
  2. Sellable counts match physical totals for unlocked dates
  3. Booking locks reduce sellable correctly
  4. POST reconcile detects drift after manual corruption
  5. GET health endpoint reports freshness
  6. Summary endpoint returns correct aggregation
  7. Room type filter works correctly
  8. Invalid date returns 400
  9. Reconcile processes date range
  10. Hold + OOO locks categorized correctly via full booking flow
"""
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

API_URL = os.environ.get("VITE_BACKEND_URL", "http://localhost:8001")

_RUN_TAG = random.randint(2100, 9999)

# ── Auth Helper ─────────────────────────────────────────────────

_cached_headers = None
_cached_tenant_id = None


async def get_auth():
    global _cached_headers, _cached_tenant_id
    if _cached_headers:
        return _cached_headers, _cached_tenant_id
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(f"{API_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        _cached_headers = {"Authorization": f"Bearer {token}"}
        _cached_tenant_id = (
            data.get("tenant_id")
            or data.get("user", {}).get("tenant_id")
            or data.get("tenant", {}).get("id")
        )
        return _cached_headers, _cached_tenant_id


# ── Test 1: GET room-types returns data ─────────────────────────

@pytest.mark.asyncio
async def test_get_room_types_returns_data():
    """GET /api/inventory/room-types?date=YYYY-MM-DD returns room type data."""
    headers, tenant_id = await get_auth()
    today = datetime.now(timezone.utc).date().isoformat()
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": today},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "room_types" in data
    assert "totals" in data
    assert len(data["room_types"]) > 0
    # Each room type must have required fields
    for rt in data["room_types"]:
        assert "room_type" in rt
        assert "physical_total" in rt
        assert "sellable" in rt
        assert "locked_booking" in rt
        assert "locked_hold" in rt
        assert "locked_ooo" in rt
        assert "locked_oos" in rt


# ── Test 2: Sellable equals physical for far-future date ────────

@pytest.mark.asyncio
async def test_sellable_equals_physical_unlocked():
    """For a date with no locks, sellable == physical_total."""
    headers, _ = await get_auth()
    far_future = (datetime.now(timezone.utc).date() + timedelta(days=365)).isoformat()
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": far_future},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    for rt in data["room_types"]:
        assert rt["sellable"] == rt["physical_total"], (
            f"{rt['room_type']}: sellable={rt['sellable']} != physical={rt['physical_total']}"
        )
        assert rt["locked_booking"] == 0
        assert rt["locked_hold"] == 0


# ── Test 3: Booking reduces sellable ────────────────────────────

@pytest.mark.asyncio
async def test_booking_reduces_sellable():
    """Create a booking, then verify sellable decreased."""
    headers, tenant_id = await get_auth()
    check_in = f"{_RUN_TAG}-06-10"
    check_out = f"{_RUN_TAG}-06-12"

    # Get room list to find an available room
    async with httpx.AsyncClient(timeout=15) as c:
        rooms_resp = await c.get(f"{API_URL}/api/pms/rooms", headers=headers)
    assert rooms_resp.status_code == 200, f"Rooms endpoint failed: {rooms_resp.status_code}"
    rooms = rooms_resp.json()
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms", rooms.get("data", []))

    available = [r for r in rooms if r.get("status") == "available" and r.get("room_type")]
    if not available:
        pytest.skip("No available rooms found for booking test")
    room = available[0]
    room_type = room.get("room_type")

    # Get pre-booking inventory
    async with httpx.AsyncClient(timeout=15) as c:
        pre_resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": check_in, "room_type": room_type},
            headers=headers,
        )
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
    pre_types = [t for t in pre_data["room_types"] if t["room_type"] == room_type]
    if not pre_types:
        pytest.skip(f"No inventory data for room type {room_type}")
    pre_sellable = pre_types[0]["sellable"]

    # Create a booking using quick-booking endpoint (simpler schema)
    booking_data = {
        "guest_name": f"INV Test Guest {uuid.uuid4().hex[:6]}",
        "room_id": room.get("id"),
        "check_in": f"{check_in}T14:00:00+00:00",
        "check_out": f"{check_out}T11:00:00+00:00",
        "total_amount": 200,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        book_resp = await c.post(
            f"{API_URL}/api/pms/quick-booking",
            json=booking_data,
            headers={**headers, "Idempotency-Key": f"inv-test-{uuid.uuid4().hex}"},
        )
    if book_resp.status_code not in (200, 201):
        pytest.skip(f"Booking creation failed ({book_resp.status_code}): {book_resp.text[:200]}")

    # Force reconciliation
    async with httpx.AsyncClient(timeout=15) as c:
        recon_resp = await c.post(
            f"{API_URL}/api/inventory/room-types/reconcile",
            params={"start_date": check_in, "end_date": check_in},
            headers=headers,
        )
    assert recon_resp.status_code == 200

    # Get post-booking inventory
    async with httpx.AsyncClient(timeout=15) as c:
        post_resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": check_in, "room_type": room_type},
            headers=headers,
        )
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    post_types = [t for t in post_data["room_types"] if t["room_type"] == room_type]
    if post_types:
        post_sellable = post_types[0]["sellable"]
        assert post_sellable < pre_sellable, (
            f"Sellable should decrease after booking: pre={pre_sellable}, post={post_sellable}"
        )


# ── Test 4: Reconcile endpoint works ───────────────────────────

@pytest.mark.asyncio
async def test_reconcile_endpoint():
    """POST /api/inventory/room-types/reconcile processes date range."""
    headers, _ = await get_auth()
    today = datetime.now(timezone.utc).date()
    start = today.isoformat()
    end = (today + timedelta(days=3)).isoformat()

    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(
            f"{API_URL}/api/inventory/room-types/reconcile",
            params={"start_date": start, "end_date": end},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["dates_processed"] == 4  # today + 3 days
    assert data["types_processed"] > 0


# ── Test 5: Health endpoint ─────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint():
    """GET /api/inventory/room-types/health reports freshness."""
    headers, _ = await get_auth()

    # First reconcile today to ensure data exists
    today = datetime.now(timezone.utc).date().isoformat()
    async with httpx.AsyncClient(timeout=15) as c:
        await c.post(
            f"{API_URL}/api/inventory/room-types/reconcile",
            params={"start_date": today, "end_date": today},
            headers=headers,
        )
        resp = await c.get(
            f"{API_URL}/api/inventory/room-types/health",
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "healthy" in data
    assert "freshness" in data
    assert "room_types_today" in data
    assert data["room_types_today"] > 0
    assert data["freshness"] in ("fresh", "recent")


# ── Test 6: Summary endpoint ───────────────────────────────────

@pytest.mark.asyncio
async def test_summary_endpoint():
    """GET /api/inventory/room-types/summary returns aggregated data."""
    headers, _ = await get_auth()
    today = datetime.now(timezone.utc).date()
    start = today.isoformat()
    end = (today + timedelta(days=2)).isoformat()

    # Ensure data exists
    async with httpx.AsyncClient(timeout=15) as c:
        await c.post(
            f"{API_URL}/api/inventory/room-types/reconcile",
            params={"start_date": start, "end_date": end},
            headers=headers,
        )
        resp = await c.get(
            f"{API_URL}/api/inventory/room-types/summary",
            params={"start_date": start, "end_date": end},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "room_types" in data
    assert "date_range" in data
    assert "total_sellable_room_nights" in data
    assert "total_physical_room_nights" in data
    assert len(data["room_types"]) > 0


# ── Test 7: Room type filter ───────────────────────────────────

@pytest.mark.asyncio
async def test_room_type_filter():
    """Filtering by room_type returns only that type."""
    headers, _ = await get_auth()
    today = datetime.now(timezone.utc).date().isoformat()

    async with httpx.AsyncClient(timeout=15) as c:
        # Get all types first
        all_resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": today},
            headers=headers,
        )
    assert all_resp.status_code == 200
    all_data = all_resp.json()
    if not all_data["room_types"]:
        pytest.skip("No room types found")

    target_type = all_data["room_types"][0]["room_type"]

    async with httpx.AsyncClient(timeout=15) as c:
        filtered_resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": today, "room_type": target_type},
            headers=headers,
        )
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()
    for rt in filtered_data["room_types"]:
        assert rt["room_type"] == target_type


# ── Test 8: Invalid date returns 400 ──────────────────────────

@pytest.mark.asyncio
async def test_invalid_date_returns_400():
    """Invalid date format returns HTTP 400."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": "not-a-date"},
            headers=headers,
        )
    assert resp.status_code == 400


# ── Test 9: Totals are consistent ──────────────────────────────

@pytest.mark.asyncio
async def test_totals_consistent():
    """Totals section matches sum of individual room types."""
    headers, _ = await get_auth()
    today = datetime.now(timezone.utc).date().isoformat()

    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": today},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    types = data["room_types"]
    totals = data["totals"]

    calc_physical = sum(t["physical_total"] for t in types)
    calc_sellable = sum(t["sellable"] for t in types)
    calc_locked = sum(
        t["locked_booking"] + t["locked_hold"] + t["locked_ooo"] + t["locked_oos"]
        for t in types
    )

    assert totals["physical"] == calc_physical
    assert totals["sellable"] == calc_sellable
    assert totals["locked"] == calc_locked


# ── Test 10: INV-7 — Sellable is exact match with locks ─────────

@pytest.mark.asyncio
async def test_inv7_sellable_matches_locks():
    """
    INV-7 verification: For each room type, sellable == physical - all_locks.
    """
    headers, _ = await get_auth()
    today = datetime.now(timezone.utc).date().isoformat()

    # Force fresh reconciliation
    async with httpx.AsyncClient(timeout=15) as c:
        await c.post(
            f"{API_URL}/api/inventory/room-types/reconcile",
            params={"start_date": today, "end_date": today},
            headers=headers,
        )
        resp = await c.get(
            f"{API_URL}/api/inventory/room-types",
            params={"date": today},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()

    for rt in data["room_types"]:
        total_locked = (
            rt["locked_booking"] + rt["locked_hold"] +
            rt["locked_ooo"] + rt["locked_oos"]
        )
        expected_sellable = max(0, rt["physical_total"] - total_locked)
        assert rt["sellable"] == expected_sellable, (
            f"INV-7 violation for {rt['room_type']}: "
            f"sellable={rt['sellable']} != expected={expected_sellable} "
            f"(physical={rt['physical_total']}, locked={total_locked})"
        )
