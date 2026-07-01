"""
Load & Chaos Test Fixtures
--------------------------
Uses get_system_db() for raw DB access (bypasses tenant scoping)
since load tests need cross-tenant admin queries for verification.
"""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

LOAD_TEST_SOURCE = "load_test_framework"


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
def api_url():
    return os.environ.get("LOAD_TEST_API_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
async def auth_token(api_url):
    async with httpx.AsyncClient(base_url=api_url, timeout=10) as client:
        resp = await client.post(
            "/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


@pytest.fixture(scope="session")
async def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def raw_db():
    """Raw MongoDB access bypassing tenant isolation (for test verification)."""
    from core.tenant_db import get_system_db
    return get_system_db()


@pytest.fixture
async def tenant_id(raw_db):
    user = await raw_db.users.find_one(
        {"email": "demo@hotel.com"}, {"_id": 0, "tenant_id": 1}
    )
    return user["tenant_id"] if user else "default-tenant"


@pytest.fixture
async def load_test_room_factory(raw_db, tenant_id):
    created_ids: List[str] = []

    async def _create(room_type: str = "STD", count: int = 1):
        rooms = []
        for _ in range(count):
            room = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "room_number": f"LT-{uuid.uuid4().hex[:6]}",
                "room_type": room_type,
                "floor": 1,
                "status": "available",
                "housekeeping_status": "clean",
                "source": LOAD_TEST_SOURCE,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await raw_db.rooms.insert_one(room)
            created_ids.append(room["id"])
            rooms.append(room)
        return rooms

    yield _create

    if created_ids:
        await raw_db.rooms.delete_many({"id": {"$in": created_ids}})


@pytest.fixture
async def load_test_booking_factory(raw_db, tenant_id):
    created_ids: List[str] = []

    async def _create(
        room_id: str,
        check_in: str = None,
        check_out: str = None,
        status: str = "confirmed",
    ):
        ci = check_in or (date.today() + timedelta(days=60)).isoformat()
        co = check_out or (date.today() + timedelta(days=62)).isoformat()
        booking = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "room_id": room_id,
            "guest_id": str(uuid.uuid4()),
            "guest_name": "Load Test Guest",
            "check_in": ci,
            "check_out": co,
            "status": status,
            "total_amount": 500.0,
            "source": LOAD_TEST_SOURCE,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await raw_db.bookings.insert_one(booking)
        created_ids.append(booking["id"])
        return booking

    yield _create

    if created_ids:
        await raw_db.bookings.delete_many({"id": {"$in": created_ids}})


@pytest.fixture(autouse=True)
async def cleanup_load_test_data(raw_db):
    yield
    for coll in ["bookings", "rooms", "room_blocks", "room_queue",
                 "staff_tasks", "rate_override_logs", "guests",
                 "allotment_contracts", "group_reservations"]:
        try:
            await raw_db[coll].delete_many({"source": LOAD_TEST_SOURCE})
        except Exception:
            pass
