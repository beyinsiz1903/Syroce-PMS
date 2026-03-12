import sys
from pathlib import Path
import pytest
import asyncio

BACKEND_ROOT = Path(__file__).resolve().parent.parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


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
