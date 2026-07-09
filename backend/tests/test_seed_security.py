import os
import uuid
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from core.database import _raw_db
from seed.channels import seed_channels

class MockDB:
    def __init__(self, db):
        self.db = db
        
    def __getattr__(self, name):
        return getattr(self.db, name)

@pytest.fixture
async def db():
    # Use a specific test db for seed testing
    test_db_name = f"hotel_pms_seed_test_{uuid.uuid4().hex}"
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"))
    
    # Clean before test
    await client.drop_database(test_db_name)
    
    motor_db = client[test_db_name]
    mock_db = MockDB(motor_db)
    
    yield mock_db
    
    # Clean after test
    await client.drop_database(test_db_name)
    client.close()

@pytest.mark.asyncio
async def test_channel_seed_defaults_to_fail_closed(db, monkeypatch):
    # Ensure environment is clean of secrets
    monkeypatch.delenv("SEED_HOTELRUNNER_TOKEN", raising=False)
    monkeypatch.delenv("SEED_HOTELRUNNER_HR_ID", raising=False)
    monkeypatch.delenv("SEED_EXELY_USERNAME", raising=False)
    monkeypatch.delenv("SEED_EXELY_PASSWORD", raising=False)
    monkeypatch.delenv("SEED_EXELY_HOTEL_CODE", raising=False)
    
    ctx = {"tenant_id": "test-tenant-123"}
    await seed_channels(db, ctx)
    
    # Verify fail-closed behavior
    hr_conn = await db.hotelrunner_connections.find_one()
    exely_conn = await db.exely_connections.find_one()
    prov_hr = await db.provider_connections.find_one({"provider": "hotelrunner"})
    prov_ex = await db.provider_connections.find_one({"provider": "exely"})
    cm_hr = await db.cm_connectors.find_one({"provider": "hotelrunner"})
    
    assert hr_conn.get("is_active") is False
    assert exely_conn.get("is_active") is False
    assert prov_hr.get("status") == "inactive"
    assert prov_ex.get("status") == "inactive"
    assert cm_hr.get("status") == "inactive"
    assert cm_hr.get("sync_enabled") is False
    
    for provider in ("hotelrunner", "exely"):
        flags = await db.connector_flags.find_one({"provider": provider})
        assert flags.get("connector_enabled") is False
        assert flags.get("write_enabled") is False
        assert flags.get("shadow_mode") is True
        
        # Mappings checks
        rm = await db.room_mappings.find_one({"provider": provider})
        assert rm.get("is_active") is False
        assert rm.get("validation_status") == "unverified"
        
        rp = await db.rate_plan_mappings.find_one({"provider": provider})
        assert rp.get("is_active") is False

@pytest.mark.asyncio
async def test_channel_seed_does_not_persist_plaintext_secrets(db, monkeypatch):
    # Set explicit fake secrets
    fake_token = "FAKE_TEST_TOKEN_DO_NOT_USE"
    fake_pass = "FAKE_PASSWORD_DO_NOT_USE"
    fake_user = "FAKE_USER"
    
    monkeypatch.setenv("SEED_HOTELRUNNER_TOKEN", fake_token)
    monkeypatch.setenv("SEED_HOTELRUNNER_HR_ID", "DEMO-HR-ID")
    monkeypatch.setenv("SEED_EXELY_USERNAME", fake_user)
    monkeypatch.setenv("SEED_EXELY_PASSWORD", fake_pass)
    monkeypatch.setenv("SEED_EXELY_HOTEL_CODE", "DEMO-EXELY")
    
    ctx = {"tenant_id": "test-tenant-123"}
    await seed_channels(db, ctx)
    
    # Assert secrets do not exist anywhere in collections
    collections = [
        "hotelrunner_connections", "exely_connections", 
        "provider_connections", "cm_connectors",
        "room_mappings", "rate_plan_mappings", "connector_flags"
    ]
    
    for coll_name in collections:
        cursor = db.db[coll_name].find({})
        async for doc in cursor:
            doc_str = str(doc)
            assert fake_token not in doc_str, f"Plaintext token leaked in {coll_name}!"
            assert fake_pass not in doc_str, f"Plaintext password leaked in {coll_name}!"
            assert fake_user not in doc_str, f"Plaintext user leaked in {coll_name}!"
            
            # Recursive check for forbidden keys
            def check_keys(d):
                if isinstance(d, dict):
                    for k, v in d.items():
                        assert k not in ["credentials", "token", "password", "username", "hr_token"], f"Forbidden key '{k}' found in {coll_name}!"
                        check_keys(v)
                elif isinstance(d, list):
                    for item in d:
                        check_keys(item)
            
            check_keys(doc)
