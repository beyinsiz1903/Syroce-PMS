"""
Battle tests conftest — test isolation fixtures.
Ensures stale data from previous test runs doesn't cause flaky failures.
"""
import os
import pytest


@pytest.fixture(scope="session", autouse=True)
def clean_stale_test_locks():
    """Remove stale room_night_locks from previous test runs.
    Test bookings use future years (> 2040) to avoid conflicting with real data.
    """
    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv
        from pathlib import Path

        load_dotenv(Path(__file__).resolve().parent.parent.parent / '.env')
        mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/hotel_pms')
        db_name = os.environ.get('DB_NAME', 'hotel_pms')
        client = MongoClient(mongo_url)
        db = client[db_name]

        # Delete all locks with night_date year > 2040 (test data only)
        result = db.room_night_locks.delete_many(
            {'night_date': {'$regex': '^20[4-9]|^2[1-9]|^[3-9]'}}
        )
        if result.deleted_count > 0:
            print(f"\n[battle-conftest] Cleaned {result.deleted_count} stale test locks")

        client.close()
    except Exception as e:
        print(f"\n[battle-conftest] Cleanup warning (non-fatal): {e}")

    yield
