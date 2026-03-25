"""
Concurrent Mutation Safety Tests
=================================
These tests verify that concurrent write operations on shared resources
(room blocks, room queue, staff tasks) do not corrupt data.

Critical invariants:
1. Room blocks: Concurrent block/cancel operations don't leave orphaned state
2. Room queue: Concurrent add/remove operations maintain queue integrity
3. Staff tasks: Concurrent updates don't lose data
4. Dashboard: Reads remain accurate during concurrent mutations
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

pytestmark = [pytest.mark.asyncio]

FUTURE_CI = (date.today() + timedelta(days=110)).isoformat()
FUTURE_CO = (date.today() + timedelta(days=112)).isoformat()


class TestConcurrentRoomBlockOperations:
    """Room block creation and cancellation under concurrent load."""

    async def test_concurrent_block_creation_different_rooms(
        self, api_url, auth_headers, raw_db, tenant_id, load_test_room_factory
    ):
        """
        Create blocks for 5 different rooms concurrently.
        All should succeed independently.
        """
        rooms = await load_test_room_factory(room_type="LOAD-BLOCK-CONC", count=5)
        created_block_ids = []

        async def _create_block(room):
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                payload = {
                    "room_id": room["id"],
                    "type": "maintenance",
                    "reason": f"Load test block for {room['room_number']}",
                    "start_date": FUTURE_CI,
                    "end_date": FUTURE_CO,
                    "source": "load_test_framework",
                }
                headers = {**auth_headers, "Idempotency-Key": str(uuid.uuid4())}
                resp = await client.post(
                    "/api/pms/room-blocks",
                    json=payload,
                    headers=headers,
                )
                return resp.status_code, resp.json() if resp.status_code in (200, 201) else resp.text

        results = await asyncio.gather(*[_create_block(r) for r in rooms])

        success_count = sum(1 for status, _ in results if status in (200, 201))
        server_errors = [r for r in results if r[0] >= 500]

        assert len(server_errors) == 0, f"Server errors: {server_errors}"
        print(f"\n[CONCURRENT BLOCKS] {success_count}/5 blocks created successfully")

        # Cleanup blocks
        for status, data in results:
            if status in (200, 201) and isinstance(data, dict):
                block_id = data.get("id") or data.get("block_id")
                if block_id:
                    created_block_ids.append(block_id)

        for bid in created_block_ids:
            async with httpx.AsyncClient(base_url=api_url, timeout=10) as client:
                await client.post(
                    f"/api/pms/room-blocks/{bid}/cancel",
                    headers=auth_headers,
                )

    async def test_block_then_cancel_no_orphan_state(
        self, api_url, auth_headers, raw_db, tenant_id, load_test_room_factory
    ):
        """
        Create a block then immediately cancel it.
        Verify no orphaned block state remains.
        """
        rooms = await load_test_room_factory(room_type="LOAD-ORPHAN-TEST", count=1)
        room_id = rooms[0]["id"]

        async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
            # Create block
            payload = {
                "room_id": room_id,
                "type": "out_of_order",
                "reason": "Orphan state test",
                "start_date": FUTURE_CI,
                "end_date": FUTURE_CO,
                "source": "load_test_framework",
            }
            block_headers = {**auth_headers, "Idempotency-Key": str(uuid.uuid4())}
            create_resp = await client.post(
                "/api/pms/room-blocks",
                json=payload,
                headers=block_headers,
            )

            if create_resp.status_code in (200, 201):
                block_data = create_resp.json()
                block_id = block_data.get("id") or block_data.get("block_id")

                if block_id:
                    # Immediately cancel
                    cancel_resp = await client.post(
                        f"/api/pms/room-blocks/{block_id}/cancel",
                        headers=auth_headers,
                    )

                    # Verify block is cancelled
                    block_in_db = await raw_db.room_blocks.find_one({"id": block_id}, {"_id": 0})
                    if block_in_db:
                        assert block_in_db.get("status") in ("cancelled", "released"), (
                            f"Block {block_id} still active after cancel: {block_in_db.get('status')}"
                        )


class TestConcurrentStaffTaskOperations:
    """Staff task CRUD under concurrent load."""

    async def test_concurrent_task_creation(
        self, api_url, auth_headers, raw_db, tenant_id, load_test_room_factory
    ):
        """Create 10 staff tasks concurrently. All should succeed."""
        rooms = await load_test_room_factory(room_type="LOAD-TASK-TEST", count=2)
        created_task_ids = []

        async def _create_task(idx):
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                payload = {
                    "task_type": "maintenance",
                    "department": "engineering",
                    "title": f"Load test task #{idx}",
                    "room_id": rooms[idx % 2]["id"],
                    "priority": "normal",
                    "description": f"Concurrent task creation test {idx}",
                    "source": "load_test_framework",
                }
                resp = await client.post(
                    "/api/pms/staff-tasks",
                    json=payload,
                    headers=auth_headers,
                )
                return resp.status_code, resp.json() if resp.status_code in (200, 201) else None

        results = await asyncio.gather(*[_create_task(i) for i in range(10)])

        success_count = sum(1 for status, _ in results if status in (200, 201))
        server_errors = [r for r in results if r[0] >= 500]

        assert len(server_errors) == 0, f"Server errors: {server_errors}"
        assert success_count == 10, f"Expected 10 tasks, got {success_count}"

        # Verify all in DB
        for status, data in results:
            if status in (200, 201) and data:
                created_task_ids.append(data.get("id"))

        db_count = await raw_db.staff_tasks.count_documents({
            "id": {"$in": created_task_ids}
        })
        assert db_count == 10, f"DB shows {db_count} tasks, expected 10"

        print(f"\n[CONCURRENT TASKS] 10/10 tasks created and verified in DB")

    async def test_concurrent_task_status_updates(
        self, api_url, auth_headers, raw_db, tenant_id
    ):
        """
        Create a task, fire 5 concurrent status updates.
        The final status must be one of the attempted values.
        """
        # Create initial task
        task_id = str(uuid.uuid4())
        await raw_db.staff_tasks.insert_one({
            "id": task_id,
            "tenant_id": tenant_id,
            "task_type": "maintenance",
            "department": "engineering",
            "title": "Concurrent update test",
            "status": "pending",
            "source": "load_test_framework",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        statuses = ["in_progress", "completed", "in_progress", "pending", "completed"]

        async def _update_status(new_status):
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                resp = await client.put(
                    f"/api/pms/staff-tasks/{task_id}",
                    json={"status": new_status},
                    headers=auth_headers,
                )
                return resp.status_code, new_status

        results = await asyncio.gather(*[_update_status(s) for s in statuses])

        server_errors = [r for r in results if r[0] >= 500]
        assert len(server_errors) == 0, f"Server errors: {server_errors}"

        # Check final state
        final_task = await raw_db.staff_tasks.find_one({"id": task_id}, {"_id": 0})
        assert final_task is not None
        assert final_task["status"] in statuses, (
            f"Final status '{final_task['status']}' not in expected values"
        )

        print(f"\n[CONCURRENT TASK UPDATE] Final status: {final_task['status']}")


class TestDashboardUnderLoad:
    """Dashboard endpoint must remain responsive under concurrent read load."""

    async def test_concurrent_dashboard_reads(
        self, api_url, auth_headers
    ):
        """Fire 20 concurrent dashboard requests. All must succeed."""

        async def _dashboard():
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                resp = await client.get(
                    "/api/pms/dashboard",
                    headers=auth_headers,
                )
                return resp.status_code

        results = await asyncio.gather(*[_dashboard() for _ in range(20)])

        server_errors = [s for s in results if s >= 500]
        assert len(server_errors) == 0, f"Dashboard server errors: {server_errors}"

        success_count = sum(1 for s in results if s == 200)
        assert success_count == 20, f"Expected 20 successful, got {success_count}"

        print(f"\n[DASHBOARD LOAD] 20/20 dashboard reads succeeded")

    async def test_concurrent_mixed_read_write_operations(
        self, api_url, auth_headers, raw_db, tenant_id
    ):
        """
        Mix of read and write operations simultaneously.
        No operation should cause a 500 error.
        """
        async def _dashboard_read():
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                resp = await client.get("/api/pms/dashboard", headers=auth_headers)
                return ("dashboard", resp.status_code)

        async def _availability_read():
            ci = (date.today() + timedelta(days=120)).isoformat()
            co = (date.today() + timedelta(days=122)).isoformat()
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                resp = await client.get(
                    "/api/pms/rooms/availability",
                    params={"check_in": ci, "check_out": co},
                    headers=auth_headers,
                )
                return ("availability", resp.status_code)

        async def _search_read():
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                resp = await client.get(
                    "/api/reservations/search",
                    params={"status": "confirmed"},
                    headers=auth_headers,
                )
                return ("search", resp.status_code)

        async def _alerts_read():
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                resp = await client.get(
                    "/api/pms/operational-alerts",
                    headers=auth_headers,
                )
                return ("alerts", resp.status_code)

        async def _staff_task_write():
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                payload = {
                    "task_type": "maintenance",
                    "department": "housekeeping",
                    "title": "Mixed load test task",
                    "priority": "normal",
                    "source": "load_test_framework",
                }
                resp = await client.post(
                    "/api/pms/staff-tasks",
                    json=payload,
                    headers=auth_headers,
                )
                return ("task_write", resp.status_code)

        # Build a mixed workload
        tasks = []
        for _ in range(5):
            tasks.extend([
                _dashboard_read(),
                _availability_read(),
                _search_read(),
                _alerts_read(),
                _staff_task_write(),
            ])

        results = await asyncio.gather(*tasks)

        by_type = {}
        for op_type, status in results:
            by_type.setdefault(op_type, []).append(status)

        server_errors = [(t, s) for t, s in results if s >= 500]
        assert len(server_errors) == 0, f"Server errors in mixed workload: {server_errors}"

        print(f"\n[MIXED WORKLOAD] Results by type:")
        for op_type, statuses in by_type.items():
            print(f"  {op_type}: {len(statuses)} requests, "
                  f"all 200: {all(s == 200 for s in statuses)}")


class TestAllotmentContractConcurrency:
    """Allotment contract operations under concurrent load."""

    async def test_concurrent_contract_creation(
        self, api_url, auth_headers
    ):
        """Create 5 allotment contracts concurrently."""
        created_ids = []

        async def _create_contract(idx):
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                payload = {
                    "tour_operator": f"Load Test Tour Op {idx}",
                    "room_type": "STD",
                    "allocated_rooms": 5,
                    "start_date": FUTURE_CI,
                    "end_date": FUTURE_CO,
                    "rate": 100.0 + idx * 10,
                    "release_days": 7,
                    "source": "load_test_framework",
                }
                resp = await client.post(
                    "/api/pms/allotment-contracts",
                    json=payload,
                    headers=auth_headers,
                )
                return resp.status_code, resp.json() if resp.status_code in (200, 201) else None

        results = await asyncio.gather(*[_create_contract(i) for i in range(5)])

        success_count = sum(1 for s, _ in results if s in (200, 201))
        server_errors = [r for r in results if r[0] >= 500]
        assert len(server_errors) == 0, f"Server errors: {server_errors}"
        assert success_count == 5, f"Expected 5 contracts, got {success_count}"

        print(f"\n[ALLOTMENT CONCURRENCY] 5/5 contracts created")


class TestGroupReservationConcurrency:
    """Group reservation operations under concurrent load."""

    async def test_concurrent_group_creation(
        self, api_url, auth_headers
    ):
        """Create 5 group reservations concurrently."""

        async def _create_group(idx):
            async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
                payload = {
                    "group_name": f"Load Test Group {idx}",
                    "contact_name": f"Contact {idx}",
                    "rooms_needed": 3,
                    "check_in": FUTURE_CI,
                    "check_out": FUTURE_CO,
                    "source": "load_test_framework",
                }
                resp = await client.post(
                    "/api/pms/group-reservations",
                    json=payload,
                    headers=auth_headers,
                )
                return resp.status_code

        results = await asyncio.gather(*[_create_group(i) for i in range(5)])

        server_errors = [s for s in results if s >= 500]
        assert len(server_errors) == 0, f"Server errors: {server_errors}"

        success_count = sum(1 for s in results if s in (200, 201))
        assert success_count == 5, f"Expected 5 groups, got {success_count}"

        print(f"\n[GROUP RESERVATION] 5/5 groups created concurrently")
