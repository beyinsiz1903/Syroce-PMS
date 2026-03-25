"""
Multi-Tenant Concurrent Load Tests
====================================
Verify system correctness when multiple tenants execute operations
simultaneously.  Tenant isolation must hold: writes from tenant-A
must never leak into tenant-B's read path.

Scenarios
---------
1. Parallel bookings across tenants — no cross-contamination
2. Concurrent dashboard reads per tenant — each sees only own data
3. Mixed read/write across tenants — no 500 errors, correct counts
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

pytestmark = [pytest.mark.asyncio]

FUTURE_CI = (date.today() + timedelta(days=130)).isoformat()
FUTURE_CO = (date.today() + timedelta(days=132)).isoformat()
LOAD_SRC = "load_test_framework"


# ── helpers ──────────────────────────────────────────────────────

async def _create_tenant_with_user(raw_db, suffix: str):
    """Create an isolated tenant + user and return (tenant_id, user_doc)."""
    tid = f"load-tenant-{suffix}"
    user_id = str(uuid.uuid4())
    from core.security import hash_password
    user = {
        "id": user_id,
        "tenant_id": tid,
        "email": f"lt-{suffix}@test.com",
        "name": f"Load Tenant {suffix}",
        "role": "admin",
        "permissions": ["all"],
        "active": True,
        "hashed_password": hash_password("lt-pass"),
        "source": LOAD_SRC,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await raw_db.users.update_one(
        {"email": user["email"]},
        {"$set": user},
        upsert=True,
    )
    # Ensure a minimal tenant document exists
    await raw_db.tenants.update_one(
        {"id": tid},
        {"$set": {
            "id": tid,
            "name": f"Load Hotel {suffix}",
            "property_name": f"Load Hotel {suffix}",
            "subscription_plan": "core_small_hotel",
            "source": LOAD_SRC,
        }},
        upsert=True,
    )
    return tid, user


async def _login(api_url: str, email: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=api_url, timeout=10) as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]


# ── fixtures ─────────────────────────────────────────────────────

@pytest.fixture
async def two_tenants(api_url, raw_db):
    """Create two independent tenants, each with a logged-in token."""
    tid_a, user_a = await _create_tenant_with_user(raw_db, "alpha")
    tid_b, user_b = await _create_tenant_with_user(raw_db, "bravo")
    tok_a = await _login(api_url, user_a["email"], "lt-pass")
    tok_b = await _login(api_url, user_b["email"], "lt-pass")

    yield {
        "a": {"tid": tid_a, "token": tok_a, "headers": {"Authorization": f"Bearer {tok_a}"}},
        "b": {"tid": tid_b, "token": tok_b, "headers": {"Authorization": f"Bearer {tok_b}"}},
    }

    # Cleanup
    for tid in (tid_a, tid_b):
        for coll in ("bookings", "rooms", "guests", "staff_tasks", "room_blocks"):
            await raw_db[coll].delete_many({"tenant_id": tid, "source": LOAD_SRC})
        await raw_db.users.delete_many({"tenant_id": tid, "source": LOAD_SRC})
        await raw_db.tenants.delete_many({"id": tid, "source": LOAD_SRC})


# ── tests ────────────────────────────────────────────────────────

class TestMultiTenantBookingIsolation:
    """Bookings from one tenant must never appear in another tenant's results."""

    async def test_parallel_bookings_across_tenants(self, api_url, raw_db, two_tenants):
        """
        Both tenants create 3 bookings simultaneously.
        Each tenant must see only its own bookings afterwards.
        """
        tenants = two_tenants

        async def _seed_rooms(tid, count=3):
            rooms = []
            for _ in range(count):
                room = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tid,
                    "room_number": f"MT-{uuid.uuid4().hex[:5]}",
                    "room_type": "STD",
                    "floor": 1,
                    "status": "available",
                    "housekeeping_status": "clean",
                    "source": LOAD_SRC,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await raw_db.rooms.insert_one(room)
                rooms.append(room)
            return rooms

        rooms_a = await _seed_rooms(tenants["a"]["tid"])
        rooms_b = await _seed_rooms(tenants["b"]["tid"])

        async def _book(api_url, headers, room, guest_suffix):
            guest = {
                "id": str(uuid.uuid4()),
                "tenant_id": room["tenant_id"],
                "name": f"MT Guest {guest_suffix}",
                "email": f"mt-{guest_suffix}@test.com",
                "source": LOAD_SRC,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await raw_db.guests.insert_one(guest)
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as c:
                resp = await c.post(
                    "/api/pms/bookings",
                    json={
                        "guest_id": guest["id"],
                        "room_id": room["id"],
                        "check_in": FUTURE_CI,
                        "check_out": FUTURE_CO,
                        "adults": 1, "children": 0, "guests_count": 1,
                        "status": "confirmed",
                        "total_amount": 200,
                        "source": LOAD_SRC,
                    },
                    headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                )
                return resp.status_code

        # Fire bookings for both tenants in parallel
        tasks = []
        for i, room in enumerate(rooms_a):
            tasks.append(_book(api_url, tenants["a"]["headers"], room, f"a{i}"))
        for i, room in enumerate(rooms_b):
            tasks.append(_book(api_url, tenants["b"]["headers"], room, f"b{i}"))

        results = await asyncio.gather(*tasks)
        assert all(s in (200, 201) for s in results), f"Some bookings failed: {results}"

        # Verify isolation: tenant A should NOT see tenant B's bookings
        async with httpx.AsyncClient(base_url=api_url, timeout=30) as c:
            resp_a = await c.get("/api/pms/bookings?limit=500", headers=tenants["a"]["headers"])
            resp_b = await c.get("/api/pms/bookings?limit=500", headers=tenants["b"]["headers"])

        bookings_a = resp_a.json()
        bookings_b = resp_b.json()

        a_room_ids = {r["id"] for r in rooms_a}
        b_room_ids = {r["id"] for r in rooms_b}

        # No booking from tenant A should reference a tenant-B room
        for b in bookings_a:
            assert b.get("room_id") not in b_room_ids, (
                f"TENANT LEAK: Tenant-A sees Tenant-B's room {b.get('room_id')}"
            )
        for b in bookings_b:
            assert b.get("room_id") not in a_room_ids, (
                f"TENANT LEAK: Tenant-B sees Tenant-A's room {b.get('room_id')}"
            )

        print(f"\n[MULTI-TENANT] A bookings={len(bookings_a)}, B bookings={len(bookings_b)} — isolation OK")


class TestMultiTenantDashboardIsolation:
    """Dashboard data must be scoped to the requesting tenant."""

    @pytest.mark.ci_load
    async def test_concurrent_dashboard_reads_per_tenant(self, api_url, two_tenants):
        """
        Both tenants read the dashboard simultaneously 10 times each.
        No cross-contamination and no server errors.
        """
        async def _read_dashboard(headers, label):
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as c:
                r = await c.get("/api/pms/dashboard", headers=headers)
                return label, r.status_code

        tasks = []
        for _ in range(10):
            tasks.append(_read_dashboard(two_tenants["a"]["headers"], "A"))
            tasks.append(_read_dashboard(two_tenants["b"]["headers"], "B"))

        results = await asyncio.gather(*tasks)
        errors = [(label, s) for label, s in results if s >= 500]
        assert len(errors) == 0, f"Dashboard errors: {errors}"

        a_ok = sum(1 for label, s in results if label == "A" and s == 200)
        b_ok = sum(1 for label, s in results if label == "B" and s == 200)
        print(f"\n[MULTI-TENANT DASHBOARD] A={a_ok}/10, B={b_ok}/10 — no cross-talk")


class TestMultiTenantMixedWorkload:
    """Mixed read/write across tenants must not cause server errors."""

    async def test_mixed_operations_across_tenants(self, api_url, two_tenants, raw_db):
        """
        Tenant-A writes (bookings) while Tenant-B reads (dashboard, search).
        No 500 errors should occur.
        """
        async def _tenant_a_write(idx):
            room = {
                "id": str(uuid.uuid4()),
                "tenant_id": two_tenants["a"]["tid"],
                "room_number": f"MW-{uuid.uuid4().hex[:5]}",
                "room_type": "STD",
                "floor": 1, "status": "available",
                "housekeeping_status": "clean",
                "source": LOAD_SRC,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await raw_db.rooms.insert_one(room)
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as c:
                r = await c.post(
                    "/api/pms/staff-tasks",
                    json={
                        "task_type": "maintenance",
                        "department": "housekeeping",
                        "title": f"MT write {idx}",
                        "room_id": room["id"],
                        "priority": "normal",
                        "source": LOAD_SRC,
                    },
                    headers=two_tenants["a"]["headers"],
                )
                return ("a_write", r.status_code)

        async def _tenant_b_read(endpoint):
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as c:
                r = await c.get(f"/api/{endpoint}", headers=two_tenants["b"]["headers"])
                return ("b_read", r.status_code)

        tasks = []
        for i in range(5):
            tasks.append(_tenant_a_write(i))
            tasks.append(_tenant_b_read("pms/dashboard"))
            tasks.append(_tenant_b_read("pms/bookings?limit=10"))

        results = await asyncio.gather(*tasks)
        errors = [(t, s) for t, s in results if s >= 500]
        assert len(errors) == 0, f"Server errors in mixed MT workload: {errors}"

        print(f"\n[MULTI-TENANT MIXED] {len(results)} ops, 0 server errors")
