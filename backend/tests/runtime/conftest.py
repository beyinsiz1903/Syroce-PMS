import pytest
import os


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="function")
async def db():
    """Fresh Motor client per test function, bound to the current event loop."""
    import motor.motor_asyncio
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "hotel_management")
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    database = client[db_name]
    yield database
    client.close()
