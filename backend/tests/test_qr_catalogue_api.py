import pytest
from fastapi.testclient import TestClient
from datetime import datetime, UTC
import asyncio

from core.database import _raw_db as raw_db
from pydantic import ValidationError
from models.schemas.qr_catalogue import (
    QuantityConfig, ChoiceConfig, ChoiceOption, GuestServiceDepartment, GuestServiceItem, DateConstraints, TimeConstraints, DateTimeConstraints
)
from fastapi import FastAPI
from routers.room_qr_requests import router

app = FastAPI()
app.include_router(router)


TEST_TENANT = "test_tenant_cat"
TEST_PROPERTY = "test_prop_cat"
TEST_ROOM = "test_room_101"

client = TestClient(app)

@pytest.fixture(autouse=True)
def safe_db_cleanup():
    """Ensure clean state for test tenant ONLY."""
    async def _clear():
        await raw_db["guest_service_catalogue_settings"].delete_many({"tenant_id": TEST_TENANT})
        await raw_db["guest_service_departments"].delete_many({"tenant_id": TEST_TENANT})
        await raw_db["guest_service_items"].delete_many({"tenant_id": TEST_TENANT})
    
    asyncio.run(_clear())
    yield
    asyncio.run(_clear())

@pytest.fixture
def mock_session(monkeypatch):
    """Mock the guest session verification."""
    async def mock_verify(tenant_id, room_id, token):
        if not token or token != "valid_token":
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid session")
        if tenant_id != TEST_TENANT or room_id != TEST_ROOM:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid scope")
        return {"property_id": TEST_PROPERTY}, {"session": "ok"}
        
    import routers.room_qr_requests
    monkeypatch.setattr(routers.room_qr_requests, "_verify_guest_session", mock_verify)

def test_schema_validations():
    # QuantityConfig bounds
    with pytest.raises(ValidationError):
        QuantityConfig(min=0, max=10) # min < 1
    with pytest.raises(ValidationError):
        QuantityConfig(min=5, max=1, default=3) # max < min
    with pytest.raises(ValidationError):
        QuantityConfig(min=1, max=25) # max > 20
    with pytest.raises(ValidationError):
        QuantityConfig(min=1, max=5, default=10) # default outside bounds

    # ChoiceConfig
    with pytest.raises(ValidationError):
        ChoiceConfig(options=[], min_selections=1, max_selections=1) # empty
    with pytest.raises(ValidationError):
        ChoiceConfig(
            options=[
                ChoiceOption(code="opt1", labels={"en": "One"}),
                ChoiceOption(code="opt1", labels={"en": "Two"})
            ]
        ) # duplicate codes
    with pytest.raises(ValidationError):
        ChoiceConfig(
            options=[ChoiceOption(code="opt1", labels={"en": "One"})],
            min_selections=2, max_selections=1
        ) # min > max
    with pytest.raises(ValidationError):
        ChoiceConfig(
            options=[ChoiceOption(code="opt1", labels={"en": "One"})],
            max_selections=2
        ) # max > len(options)
        
    # Date/Time/DateTime Constraints
    with pytest.raises(ValidationError):
        DateConstraints(min_days_ahead=-1)
    with pytest.raises(ValidationError):
        TimeConstraints(interval_minutes=4) # < 5
    with pytest.raises(ValidationError):
        TimeConstraints(interval_minutes=17) # 60 % 17 != 0
    with pytest.raises(ValidationError):
        DateTimeConstraints(min_days_ahead=5, max_days_ahead=2, interval_minutes=15) # min > max
        
    # Multilingual validation
    with pytest.raises(ValidationError):
        GuestServiceDepartment(
            tenant_id="t", property_id="p", department_code="d",
            labels={"english_very_long_invalid_code": "l"}, icon="icon", created_at=datetime.now(), updated_at=datetime.now()
        )
    with pytest.raises(ValidationError):
        GuestServiceDepartment(
            tenant_id="t", property_id="p", department_code="d",
            labels={"en": "   "}, icon="icon", created_at=datetime.now(), updated_at=datetime.now()
        )

def test_api_session_security(mock_session):
    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    
    # Missing session
    res = client.get(url)
    assert res.status_code == 403
    
    # Invalid session
    res = client.get(url, headers={"X-Guest-Session": "invalid"})
    assert res.status_code == 403
    
    # Wrong tenant/room scope mapping
    res2 = client.get(f"/api/public/room-qr/wrong_tenant/{TEST_ROOM}/catalogue", headers={"X-Guest-Session": "valid_token"})
    assert res2.status_code == 403

def test_api_modes_default(mock_session):
    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200
    data = res.json()
    assert data["catalogue_version"] == 1
    assert "departments" in data
    assert "services" in data
    
    # No sensitive data leakage
    assert "_id" not in str(data)
    assert "tenant_id" not in str(data)
    assert "guest" not in str(data)

def test_api_modes_disabled(mock_session):
    async def setup():
        await raw_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "disabled"
        })
    asyncio.run(setup())
    
    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"

def test_api_service_filtering(mock_session):
    async def setup():
        await raw_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        await raw_db["guest_service_departments"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "enabled.dept",
                "labels": {"en": "Enabled"}, "icon": "check", "enabled": True, "display_order": 1,
                "created_at": datetime.now(), "updated_at": datetime.now()
            },
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "disabled.dept",
                "labels": {"en": "Disabled"}, "icon": "x", "enabled": False, "display_order": 2,
                "created_at": datetime.now(), "updated_at": datetime.now()
            }
        ])
        await raw_db["guest_service_items"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "enabled.dept",
                "service_code": "srv.1", "labels": {"en": "Srv1"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "display_order": 1, "created_at": datetime.now(), "updated_at": datetime.now()
            },
            { # Disabled service
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "enabled.dept",
                "service_code": "srv.disabled", "labels": {"en": "Srv2"}, "icon": "s2", "enabled": False,
                "input_type": "one_tap", "input_config": {},
                "display_order": 2, "created_at": datetime.now(), "updated_at": datetime.now()
            },
            { # Orphan service (in disabled dept)
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "disabled.dept",
                "service_code": "srv.orphan", "labels": {"en": "Srv3"}, "icon": "s3", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "display_order": 3, "created_at": datetime.now(), "updated_at": datetime.now()
            }
        ])
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200
    data = res.json()
    
    dept_codes = [d["department_code"] for d in data["departments"]]
    assert "enabled.dept" in dept_codes
    assert "disabled.dept" not in dept_codes
    
    srv_codes = [s["service_code"] for s in data["services"]]
    assert "srv.1" in srv_codes
    assert "srv.disabled" not in srv_codes
    assert "srv.orphan" not in srv_codes

def test_api_malformed_records(mock_session):
    async def setup():
        await raw_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        await raw_db["guest_service_departments"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "good.dept",
                "labels": {"en": "Good"}, "icon": "check", "enabled": True, "display_order": 1,
                "created_at": datetime.now(), "updated_at": datetime.now()
            },
            { # Malformed dept (missing required labels)
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "bad.dept",
                "icon": "x", "enabled": True, "display_order": 2,
                "created_at": datetime.now(), "updated_at": datetime.now()
            }
        ])
        await raw_db["guest_service_items"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "good.dept",
                "service_code": "srv.good", "labels": {"en": "GoodSrv"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "display_order": 1, "created_at": datetime.now(), "updated_at": datetime.now()
            },
            { # Malformed service (invalid input type combo)
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "good.dept",
                "service_code": "srv.bad", "labels": {"en": "BadSrv"}, "icon": "s2", "enabled": True,
                "input_type": "quantity", "input_config": {"min": -5}, # min must be >= 1
                "display_order": 2, "created_at": datetime.now(), "updated_at": datetime.now()
            }
        ])
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200
    data = res.json()
    
    dept_codes = [d["department_code"] for d in data["departments"]]
    assert dept_codes == ["good.dept"]
    
    srv_codes = [s["service_code"] for s in data["services"]]
    assert srv_codes == ["srv.good"]

def test_api_configured_empty(mock_session):
    async def setup():
        await raw_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        # No valid items inserted
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"

def test_ensure_indexes_exact():
    # Bypass _INDEXES_READY if it was set, or just run it directly
    from routers.room_qr_requests import _ensure_indexes
    async def _run():
        import routers.room_qr_requests
        routers.room_qr_requests._INDEXES_READY = False
        await _ensure_indexes()
        
        # Verify settings unique lookup
        settings_idx = await raw_db["guest_service_catalogue_settings"].index_information()
        assert "gsc_settings_lookup" in settings_idx
        assert settings_idx["gsc_settings_lookup"]["unique"] == True
        assert settings_idx["gsc_settings_lookup"]["key"] == [("tenant_id", 1), ("property_id", 1)]
        
        # Verify department indexes
        dept_idx = await raw_db["guest_service_departments"].index_information()
        assert "gsc_dept_unique" in dept_idx
        assert dept_idx["gsc_dept_unique"]["unique"] == True
        assert dept_idx["gsc_dept_unique"]["key"] == [("tenant_id", 1), ("property_id", 1), ("department_code", 1)]
        
        assert "gsc_dept_order" in dept_idx
        assert dept_idx["gsc_dept_order"].get("unique") is None # false
        assert dept_idx["gsc_dept_order"]["key"] == [("tenant_id", 1), ("property_id", 1), ("enabled", 1), ("display_order", 1)]
        
        # Verify items indexes
        items_idx = await raw_db["guest_service_items"].index_information()
        assert "gsc_item_unique" in items_idx
        assert items_idx["gsc_item_unique"]["unique"] == True
        assert items_idx["gsc_item_unique"]["key"] == [("tenant_id", 1), ("property_id", 1), ("service_code", 1)]
        
        assert "gsc_item_order" in items_idx
        assert items_idx["gsc_item_order"].get("unique") is None
        assert items_idx["gsc_item_order"]["key"] == [("tenant_id", 1), ("property_id", 1), ("department_code", 1), ("enabled", 1), ("display_order", 1)]
        
    asyncio.run(_run())
