"""
PMS Decomposition Stage 3 — Pre-Extraction Regression Tests
=============================================================
These tests MUST be run BEFORE and AFTER extracting routes from pms.py.
They verify both route reachability AND response correctness.

Coverage:
- All 32 routes remaining in pms.py
- Response structure validation
- Business logic correctness for availability and reservations
- Edge cases: empty results, missing entities, boundary dates

Test Credential: demo@hotel.com / demo123
"""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

pytestmark = [pytest.mark.asyncio]

API_URL = os.environ.get("TEST_API_URL", "http://localhost:8001")
FUTURE_CI = (date.today() + timedelta(days=70)).isoformat()
FUTURE_CO = (date.today() + timedelta(days=72)).isoformat()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT / ".env")
    from core import database
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
    db_name = os.environ.get("DB_NAME", "hotel_pms")
    database.client = AsyncIOMotorClient(mongo_url)
    database.db = database.client[db_name]
    database._raw_db = database.client[db_name]
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def auth_headers():
    async with httpx.AsyncClient(base_url=API_URL, timeout=10) as c:
        resp = await c.post("/api/auth/login", json={"email": "demo@hotel.com", "password": "demo123"})
        resp.raise_for_status()
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def raw_db():
    from core.tenant_db import get_system_db
    return get_system_db()


@pytest.fixture
async def tenant_id(raw_db):
    user = await raw_db.users.find_one({"email": "demo@hotel.com"}, {"_id": 0, "tenant_id": 1})
    return user["tenant_id"]


@pytest.fixture
async def test_room(raw_db, tenant_id):
    room = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "room_number": f"S3-{uuid.uuid4().hex[:4]}",
        "room_type": "STD",
        "floor": 1,
        "status": "available",
        "housekeeping_status": "clean",
        "source": "stage3_test",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await raw_db.rooms.insert_one(room)
    yield room
    await raw_db.rooms.delete_one({"id": room["id"]})


@pytest.fixture
async def test_booking(raw_db, tenant_id, test_room):
    booking = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "room_id": test_room["id"],
        "guest_id": str(uuid.uuid4()),
        "guest_name": "Stage 3 Test Guest",
        "check_in": FUTURE_CI,
        "check_out": FUTURE_CO,
        "status": "confirmed",
        "total_amount": 500.0,
        "source": "stage3_test",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await raw_db.bookings.insert_one(booking)
    yield booking
    await raw_db.bookings.delete_one({"id": booking["id"]})


# ═══════════════════════════════════════════════════════════════════
# Group 1: Room Services (2 routes)
# ═══════════════════════════════════════════════════════════════════

class TestRoomServicesRoutes:
    async def test_get_room_services(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get("/api/pms/room-services", headers=auth_headers)
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    async def test_update_room_service_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.put(
                "/api/pms/room-services/nonexistent",
                json={"status": "completed"},
                headers=auth_headers,
            )
            # Should not 500 — graceful handling
            assert resp.status_code != 500


# ═══════════════════════════════════════════════════════════════════
# Group 2: Room Blocks (4 routes)
# ═══════════════════════════════════════════════════════════════════

class TestRoomBlockRoutes:
    async def test_get_room_blocks(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get("/api/pms/room-blocks", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "blocks" in data
            assert "count" in data
            assert isinstance(data["blocks"], list)

    async def test_create_and_cancel_room_block(self, auth_headers, test_room):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            create_resp = await c.post(
                "/api/pms/room-blocks",
                json={
                    "room_id": test_room["id"],
                    "type": "maintenance",
                    "reason": "Stage 3 test",
                    "start_date": FUTURE_CI,
                    "end_date": FUTURE_CO,
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
            assert create_resp.status_code in (200, 201)
            block_data = create_resp.json()
            block_id = block_data.get("block", {}).get("id")
            assert block_id

            # Cancel
            cancel_resp = await c.post(
                f"/api/pms/room-blocks/{block_id}/cancel",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
            assert cancel_resp.status_code in (200, 201)

    async def test_patch_room_block_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.patch(
                "/api/pms/room-blocks/nonexistent",
                json={"reason": "updated"},
                headers=auth_headers,
            )
            assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Group 3: Availability (CRITICAL)
# ═══════════════════════════════════════════════════════════════════

class TestAvailabilityRoutes:
    async def test_availability_returns_list(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/pms/rooms/availability",
                params={"check_in": FUTURE_CI, "check_out": FUTURE_CO},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)

    async def test_availability_rooms_have_required_fields(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/pms/rooms/availability",
                params={"check_in": FUTURE_CI, "check_out": FUTURE_CO},
                headers=auth_headers,
            )
            data = resp.json()
            if data:
                room = data[0]
                assert "id" in room
                assert "room_type" in room

    async def test_availability_with_room_type_filter(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/pms/rooms/availability",
                params={"check_in": FUTURE_CI, "check_out": FUTURE_CO, "room_type": "STD"},
                headers=auth_headers,
            )
            assert resp.status_code == 200

    async def test_booked_room_marked_unavailable(self, auth_headers, test_booking, test_room):
        """After booking test_room, it should appear as unavailable for overlapping dates."""
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/pms/rooms/availability",
                params={"check_in": FUTURE_CI, "check_out": FUTURE_CO},
                headers=auth_headers,
            )
            data = resp.json()
            room_entry = next((r for r in data if r["id"] == test_room["id"]), None)
            if room_entry:
                assert not room_entry.get("available", True), (
                    f"Room {test_room['id']} should be unavailable (booked)"
                )


# ═══════════════════════════════════════════════════════════════════
# Group 4: Staff Tasks (3 routes)
# ═══════════════════════════════════════════════════════════════════

class TestStaffTaskRoutes:
    async def test_get_staff_tasks(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get("/api/pms/staff-tasks", headers=auth_headers)
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    async def test_create_staff_task(self, auth_headers, raw_db):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/pms/staff-tasks",
                json={
                    "task_type": "maintenance",
                    "department": "engineering",
                    "title": "Stage 3 regression test task",
                    "priority": "high",
                    "source": "stage3_test",
                },
                headers=auth_headers,
            )
            assert resp.status_code in (200, 201)
            task = resp.json()
            assert task.get("id")
            assert task.get("title") == "Stage 3 regression test task"
            # Cleanup
            await raw_db.staff_tasks.delete_one({"id": task["id"]})

    async def test_update_staff_task_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.put(
                "/api/pms/staff-tasks/nonexistent",
                json={"status": "completed"},
                headers=auth_headers,
            )
            assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Group 5: Allotment Contracts (3 routes)
# ═══════════════════════════════════════════════════════════════════

class TestAllotmentContractRoutes:
    async def test_get_allotment_contracts(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get("/api/pms/allotment-contracts", headers=auth_headers)
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    async def test_create_allotment_contract(self, auth_headers, raw_db):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/pms/allotment-contracts",
                json={
                    "tour_operator": "Stage 3 Test Operator",
                    "room_type": "STD",
                    "allocated_rooms": 10,
                    "start_date": FUTURE_CI,
                    "end_date": FUTURE_CO,
                    "rate": 150.0,
                    "source": "stage3_test",
                },
                headers=auth_headers,
            )
            assert resp.status_code in (200, 201)
            data = resp.json()
            assert data.get("id")
            assert data.get("tour_operator") == "Stage 3 Test Operator"
            assert "_id" not in data  # No ObjectId leak
            await raw_db.allotment_contracts.delete_one({"id": data["id"]})

    async def test_release_contract_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/pms/allotment-contracts/nonexistent/release",
                headers=auth_headers,
            )
            assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Group 6: Group Reservations (2 routes)
# ═══════════════════════════════════════════════════════════════════

class TestGroupReservationRoutes:
    async def test_get_group_reservations(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get("/api/pms/group-reservations", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "groups" in data

    async def test_create_group_reservation(self, auth_headers, raw_db):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/pms/group-reservations",
                json={
                    "group_name": "Stage 3 Test Group",
                    "rooms_needed": 5,
                    "source": "stage3_test",
                },
                headers=auth_headers,
            )
            assert resp.status_code in (200, 201)
            data = resp.json()
            assert data.get("id")
            assert "_id" not in data
            await raw_db.group_reservations.delete_one({"id": data["id"]})


# ═══════════════════════════════════════════════════════════════════
# Group 7: Setup Status (1 route)
# ═══════════════════════════════════════════════════════════════════

class TestSetupStatusRoute:
    async def test_setup_status_returns_counts(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get("/api/pms/setup-status", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "rooms_count" in data
            assert "bookings_count" in data
            assert isinstance(data["rooms_count"], int)
            assert isinstance(data["bookings_count"], int)


# ═══════════════════════════════════════════════════════════════════
# Group 8: Room Details Enhanced (3 routes)
# ═══════════════════════════════════════════════════════════════════

class TestRoomDetailsEnhancedRoutes:
    async def test_get_room_details_enhanced(self, auth_headers, test_room):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                f"/api/rooms/{test_room['id']}/details-enhanced",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["room_id"] == test_room["id"]
            assert "notes" in data
            assert "minibar" in data
            assert "next_maintenance" in data

    async def test_room_details_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/rooms/nonexistent/details-enhanced",
                headers=auth_headers,
            )
            assert resp.status_code == 404

    async def test_add_room_note(self, auth_headers, test_room, raw_db):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                f"/api/rooms/{test_room['id']}/notes",
                params={"note_type": "issue", "description": "Stage 3 test note", "priority": "high"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("success") is True
            assert data.get("note_id")
            await raw_db.room_notes.delete_one({"id": data["note_id"]})

    async def test_minibar_update(self, auth_headers, test_room, raw_db):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                f"/api/rooms/{test_room['id']}/minibar-update",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("success") is True
            await raw_db.minibar_updates.delete_one({"id": data["update_id"]})


# ═══════════════════════════════════════════════════════════════════
# Group 9: Reservation Details (8 routes) — CRITICAL
# ═══════════════════════════════════════════════════════════════════

class TestReservationDetailRoutes:
    async def test_reservation_details_enhanced(self, auth_headers, test_booking):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                f"/api/reservations/{test_booking['id']}/details-enhanced",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["booking_id"] == test_booking["id"]
            assert "cancellation_policy" in data
            assert "rate_breakdown" in data

    async def test_reservation_details_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/reservations/nonexistent/details-enhanced",
                headers=auth_headers,
            )
            assert resp.status_code == 404

    async def test_double_booking_check(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/reservations/double-booking-check",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "total_conflicts" in data
            assert "conflicts" in data
            assert "status" in data

    async def test_double_booking_check_with_date(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/reservations/double-booking-check",
                params={"date": FUTURE_CI},
                headers=auth_headers,
            )
            assert resp.status_code == 200

    async def test_adr_visibility(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/reservations/adr-visibility",
                params={"start_date": FUTURE_CI, "end_date": FUTURE_CO},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "overall_adr" in data
            assert "total_room_revenue" in data
            assert "rate_breakdown" in data

    async def test_rate_override_panel(self, auth_headers, test_booking):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/reservations/rate-override-panel",
                params={
                    "booking_id": test_booking["id"],
                    "new_rate": 450.0,
                    "override_reason": "Stage 3 test override",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("success") is True
            assert data["new_rate"] == 450.0

    async def test_rate_override_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/reservations/rate-override-panel",
                params={
                    "booking_id": "nonexistent",
                    "new_rate": 100.0,
                    "override_reason": "test",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 404

    async def test_ota_details(self, auth_headers, test_booking):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                f"/api/reservations/{test_booking['id']}/ota-details",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["booking_id"] == test_booking["id"]
            assert "source_of_booking" in data

    async def test_add_extra_charge(self, auth_headers, test_booking, raw_db):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                f"/api/reservations/{test_booking['id']}/extra-charges",
                json={"charge_name": "Mini Bar", "charge_amount": 25.0, "notes": "Stage 3 test"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("success") is True
            # Cleanup
            await raw_db.extra_charges.delete_many({"booking_id": test_booking["id"]})

    async def test_search_reservations(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/reservations/search",
                params={"status": "confirmed"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "bookings" in data
            assert "count" in data

    async def test_search_by_query(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get(
                "/api/reservations/search",
                params={"query": "Stage 3 Test"},
                headers=auth_headers,
            )
            assert resp.status_code == 200

    async def test_multi_room_reservation(self, auth_headers, test_booking, raw_db):
        # Create a second booking for multi-room
        booking2_id = str(uuid.uuid4())
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/reservations/multi-room",
                json={
                    "group_name": "Stage 3 Multi-Room Test",
                    "primary_booking_id": test_booking["id"],
                    "related_booking_ids": [booking2_id],
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("success") is True
            await raw_db.multi_room_bookings.delete_many({"primary_booking_id": test_booking["id"]})


# ═══════════════════════════════════════════════════════════════════
# Group 10: Room Queue (5 routes)
# ═══════════════════════════════════════════════════════════════════

class TestRoomQueueRoutes:
    async def test_get_room_queue(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.get("/api/rooms/queue/list", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "queue" in data
            assert "queue_length" in data
            assert "available_rooms" in data

    async def test_add_to_queue(self, auth_headers, test_booking, raw_db):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/rooms/queue/add",
                json={"booking_id": test_booking["id"]},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("success") is True
            assert data.get("queue_id")
            await raw_db.room_queue.delete_one({"id": data["queue_id"]})

    async def test_assign_priority_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/rooms/queue/assign-priority",
                params={"queue_id": "nonexistent", "priority": 1},
                headers=auth_headers,
            )
            assert resp.status_code == 404

    async def test_notify_guest_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.post(
                "/api/rooms/queue/notify-guest",
                params={"queue_id": "nonexistent", "room_number": "101"},
                headers=auth_headers,
            )
            assert resp.status_code == 404

    async def test_delete_from_queue_not_found(self, auth_headers):
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            resp = await c.delete("/api/rooms/queue/nonexistent", headers=auth_headers)
            assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Group: Guests-count consistency (update reservation service)
# ═══════════════════════════════════════════════════════════════════

class TestGuestsCountConsistency:
    """adults/children degisince guests_count'un (ve legacy n alaninin)
    sunucu tarafinda yeniden turetildigini dogrular. _build_update_data
    saf is mantigidir; guest_id/room_id degismedikce repository'ye dokunmaz."""

    def _service(self):
        from modules.reservations.services.update_reservation_service import (
            UpdateReservationService,
        )
        return UpdateReservationService(repository=object())

    async def test_adults_change_recomputes_guests_count(self):
        svc = self._service()
        existing = {"adults": 2, "children": 1, "guests_count": 3}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"adults": 4},
        )
        assert result["adults"] == 4
        assert result["guests_count"] == 5

    async def test_children_change_recomputes_guests_count(self):
        svc = self._service()
        existing = {"adults": 2, "children": 0, "guests_count": 2}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"children": 3},
        )
        assert result["children"] == 3
        assert result["guests_count"] == 5

    async def test_client_omits_guests_count_still_derived(self):
        svc = self._service()
        existing = {"adults": 1, "children": 0, "guests_count": 1}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"adults": 3},
        )
        assert result["guests_count"] == 3

    async def test_client_wrong_guests_count_is_overridden(self):
        svc = self._service()
        existing = {"adults": 2, "children": 1, "guests_count": 3}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"adults": 4, "guests_count": 99},
        )
        assert result["guests_count"] == 5

    async def test_legacy_n_synced_when_present(self):
        svc = self._service()
        existing = {"adults": 2, "children": 1, "guests_count": 3, "n": 3}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"adults": 5},
        )
        assert result["guests_count"] == 6
        assert result["n"] == 6

    async def test_legacy_n_not_added_when_absent(self):
        svc = self._service()
        existing = {"adults": 2, "children": 1, "guests_count": 3}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"adults": 5},
        )
        assert "n" not in result

    async def test_no_guest_count_change_without_adults_or_children(self):
        svc = self._service()
        existing = {"adults": 2, "children": 1, "guests_count": 3}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"special_requests": "late checkout"},
        )
        assert result == {"special_requests": "late checkout"}
        assert "guests_count" not in result

    async def test_guests_count_floor_is_one(self):
        svc = self._service()
        existing = {"adults": 2, "children": 0, "guests_count": 2}
        result = await svc._build_update_data(
            tenant_id="t1",
            booking_id="b1",
            existing_booking=existing,
            booking_data={"adults": 0},
        )
        assert result["guests_count"] == 1
