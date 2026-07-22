import pytest
import os
import sys
from pathlib import Path

# Make sure we can import from backend
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.seed_pilot_demo_hotel import TENANT_ID, run_seed, enforce_guards
from core.database import _raw_db

@pytest.mark.asyncio
async def test_pilot_demo_guards_syntax():
    # Test syntax/import check without hitting mongo (unless run_seed runs, but we only run enforce_guards here)
    # The enforce_guards should fail if DEMO_MODE isn't set, but let's mock it for the test
    os.environ["DEMO_MODE"] = "1"
    os.environ["ENV"] = "test"
    try:
        enforce_guards()
    except SystemExit:
        pytest.fail("Guards failed even with DEMO_MODE=1 and ENV=test")


@pytest.mark.asyncio
@pytest.mark.live_mongo
async def test_pilot_demo_seed_data_generation():
    # Ensure guard allows execution
    os.environ["DEMO_MODE"] = "1"
    os.environ["ENV"] = "test"

    # 1. Run the seed
    await run_seed()

    # 2. Verify data counts
    tenant = await _raw_db.tenants.find_one({"_id": TENANT_ID})
    assert tenant is not None
    assert tenant["name"] == "Syroce Pilot Demo Hotel"

    users_count = await _raw_db.users.count_documents({"tenant_id": TENANT_ID})
    assert users_count == 4  # GM, FrontDesk, Housekeeping, Finance

    rooms_count = await _raw_db.rooms.count_documents({"tenant_id": TENANT_ID})
    assert rooms_count == 42  # 20 Standard + 15 Deluxe + 5 Family + 2 Suite

    guests_count = await _raw_db.guests.count_documents({"tenant_id": TENANT_ID})
    assert guests_count == 20

    bookings_count = await _raw_db.bookings.count_documents({"tenant_id": TENANT_ID})
    assert bookings_count >= 9  # 9 scenarios defined in script

    folios_count = await _raw_db.folios.count_documents({"tenant_id": TENANT_ID})
    assert folios_count >= 9

    payments_count = await _raw_db.payments.count_documents({"tenant_id": TENANT_ID})
    assert payments_count > 0

    tasks_count = await _raw_db.housekeeping_tasks.count_documents({"tenant_id": TENANT_ID})
    assert tasks_count >= 4

    maintenance_count = await _raw_db.housekeeping_tasks.count_documents({"tenant_id": TENANT_ID, "task_type": "maintenance"})
    assert maintenance_count >= 1

    cleaning_count = await _raw_db.housekeeping_tasks.count_documents({"tenant_id": TENANT_ID, "task_type": "cleaning"})
    assert cleaning_count >= 3


@pytest.mark.asyncio
@pytest.mark.live_mongo
async def test_seed_idempotency_and_tenant_isolation():
    # Ensure guard allows execution
    os.environ["DEMO_MODE"] = "1"
    os.environ["ENV"] = "test"

    # Run the seed twice to ensure it deletes before inserting
    await run_seed()
    await run_seed()

    # The counts should still be exactly the same, not doubled
    rooms_count = await _raw_db.rooms.count_documents({"tenant_id": TENANT_ID})
    assert rooms_count == 42

    collections = ["users", "rooms", "guests", "bookings", "folios", "payments", "housekeeping_tasks"]
    
    # Let's get the timestamp from the test start to only check records created by us
    for coll_name in collections:
        # Check that there are no documents in this collection with a missing tenant_id 
        # (Only checking docs that have a tenant_id but it's null, or doesn't exist)
        missing_tenant = await _raw_db[coll_name].count_documents({"tenant_id": {"$exists": False}})
        assert missing_tenant == 0, f"Found records with missing tenant_id in {coll_name}"

        # Fetch records created by our seed (we can't easily isolate if others are running, 
        # but we know our records MUST exactly match TENANT_ID)
        # So we assert that the count of docs with our TENANT_ID hasn't doubled.
        tenant_docs = await _raw_db[coll_name].count_documents({"tenant_id": TENANT_ID})
        
        if coll_name == "users":
            assert tenant_docs == 4
        elif coll_name == "rooms":
            assert tenant_docs == 42
        elif coll_name == "guests":
            assert tenant_docs == 20
        elif coll_name == "bookings":
            assert tenant_docs == 9
        elif coll_name == "folios":
            assert tenant_docs == 9
        elif coll_name == "housekeeping_tasks":
            assert tenant_docs >= 4
