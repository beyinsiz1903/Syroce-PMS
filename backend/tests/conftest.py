import sys
from pathlib import Path
import pytest
import asyncio
import os
import requests

BACKEND_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="session")
def demo_auth_token():
    """Shared demo admin auth token for all tests."""
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    if resp.status_code != 200:
        pytest.skip("Authentication failed for demo@hotel.com")
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def demo_auth_headers(demo_auth_token):
    """Shared auth headers dict."""
    return {"Authorization": f"Bearer {demo_auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session.
    This is required because Motor client binds to the event loop at import time.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Re-initialize motor client on this loop
    from core import database
    from motor.motor_asyncio import AsyncIOMotorClient
    import os
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT / '.env')
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/hotel_pms')
    db_name = os.environ.get('DB_NAME', 'hotel_pms')
    database.client = AsyncIOMotorClient(mongo_url)
    database.db = database.client[db_name]

    yield loop
    loop.close()
