import pytest
from fastapi.testclient import TestClient
from datetime import datetime, UTC
import asyncio

from core.database import _raw_db as raw_db
from pydantic import ValidationError
from models.schemas.qr_catalogue import (
    QuantityConfig, ChoiceConfig, ChoiceOption, GuestServiceDepartment, GuestServiceItem, DateConstraints, TimeConstraints, DateTimeConstraints, GuestServiceCatalogueSettings
)
from fastapi import FastAPI
from routers.room_qr_requests import router

app = FastAPI()
app.include_router(router)

TEST_TENANT = "test_tenant_cat"
TEST_PROPERTY = "test_prop_cat"
TEST_ROOM = "test_room_101"

client = TestClient(app)

class FakeAsyncCursor:
    def __init__(self, items):
        self.items = items
    async def to_list(self, length=None):
        return [dict(i) for i in self.items]

class FakeAsyncCollection:
    def __init__(self):
        self.data = []
        self.indexes = {}

    async def insert_one(self, doc):
        self.data.append(dict(doc))

    async def find_one_and_update(self, query, update, upsert=False, return_document=None):
        doc = await self.find_one(query)
        if doc is None and upsert:
            new_doc = query.copy()
            new_doc.update(update.get("$setOnInsert", {}))
            new_doc.update(update.get("$set", {}))
            if "_id" not in new_doc:
                new_doc["_id"] = "fake_id"
            self.data.append(new_doc)
            return new_doc
        elif doc:
            doc.update(update.get("$set", {}))
            return doc
        return None

    async def count_documents(self, query):
        print("DEBUG COUNT_DOCUMENTS QUERY:", query)
        print("DEBUG COUNT_DOCUMENTS DATA:", self.data)
        count = 0
        for item in self.data:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

    async def update_one(self, query, update):
        class Result:
            matched_count = 0
            modified_count = 0
        res = Result()

        for item in self.data:
            match = True
            for k, v in query.items():
                # For dot notation, just simple dict get is not enough, but our query doesn't use dot notation for top-level search here
                if item.get(k) != v:
                    match = False
                    break
            if match:
                item.update(update.get("$set", {}))
                res.matched_count = 1
                res.modified_count = 1
                break
        return res

    async def insert_many(self, docs):
        for doc in docs:
            await self.insert_one(doc)

    async def find_one(self, query):
        for item in self.data:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                return dict(item)
        return None

    def find(self, query):
        results = []
        for item in self.data:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                results.append(item)
        return FakeAsyncCursor(results)

    async def delete_many(self, query):
        new_data = []
        for item in self.data:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if not match:
                new_data.append(item)
        self.data = new_data

    async def create_index(self, keys, **kwargs):
        name = kwargs.get("name", "idx_fake")
        self.indexes[name] = {"key": keys, **kwargs}

    async def index_information(self):
        return self.indexes


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    import routers.room_qr_requests
    fake_settings = FakeAsyncCollection()
    fake_depts = FakeAsyncCollection()
    fake_items = FakeAsyncCollection()
    fake_props = FakeAsyncCollection()
    fake_rooms = FakeAsyncCollection()
    fake_submissions = FakeAsyncCollection()
    fake_qr_requests = FakeAsyncCollection()

    # Pre-populate property
    asyncio.run(fake_props.insert_one({
        "id": TEST_PROPERTY,
        "tenant_id": TEST_TENANT,
        "timezone": "UTC",
        "default_language": "en"
    }))

    class FakeDB(dict):
        pass

    db = FakeDB()
    db["guest_service_catalogue_settings"] = fake_settings
    db["guest_service_departments"] = fake_depts
    db["guest_service_items"] = fake_items
    db["properties"] = fake_props
    db["rooms"] = fake_rooms
    db["guest_service_submissions"] = fake_submissions
    db["qr_requests"] = fake_qr_requests

    monkeypatch.setattr(routers.room_qr_requests, "raw_db", db)
    import domains.guest.qr_catalogue_service
    monkeypatch.setattr(domains.guest.qr_catalogue_service, "raw_db", db)
    import domains.guest.qr_submission_service
    monkeypatch.setattr(domains.guest.qr_submission_service, "raw_db", db)
    return db

@pytest.fixture
def mock_session(monkeypatch):
    """Mock the guest session verification to simulate exceptions accurately."""
    async def mock_verify(tenant_id, room_id, token):
        from fastapi import HTTPException
        if not token:
            raise HTTPException(status_code=401, detail="Yetkisiz: Misafir oturumu eksik")
        if token == "expired":
            raise HTTPException(status_code=401, detail="Yetkisiz: Oturum süresi dolmuş")
        if token == "revoked":
            raise HTTPException(status_code=401, detail="Yetkisiz: Oturum iptal edilmiş")
        if token == "checkout":
            raise HTTPException(status_code=403, detail="Misafir çıkış yapmış")
        if token == "room_moved":
            raise HTTPException(status_code=403, detail="Oda değiştirildi")
        if token == "missing_prop":
            return {"property_id": None, "id": "test_booking_123", "guest_id": "test_guest_123"}, {"id": "test_session_123", "token_hash": "mocked_token_hash", "session_hash": "mocked_session_hash"}
        if token == "different_prop":
            return {"property_id": "other_prop", "id": "test_booking_123", "guest_id": "test_guest_123"}, {"id": "test_session_123", "property_id": "other_prop", "token_hash": "mocked_token_hash", "session_hash": "mocked_session_hash"}
        if token == "session_booking_mismatch":
            # Session exists for this booking but different property scope
            return {"property_id": TEST_PROPERTY, "id": "test_booking_123", "guest_id": "test_guest_123"}, {"id": "test_session_123", "property_id": "different_prop", "token_hash": "mocked_token_hash", "session_hash": "mocked_session_hash"}

        if token != "valid_token":
             raise HTTPException(status_code=401, detail="Yetkisiz: Geçersiz oturum")
        if tenant_id != TEST_TENANT or room_id != TEST_ROOM:
            raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")
        return {"property_id": TEST_PROPERTY, "id": "test_booking_123", "guest_id": "test_guest_123"}, {"id": "test_session_123", "property_id": TEST_PROPERTY, "token_hash": "mocked_token_hash", "session_hash": "mocked_session_hash"}

    import routers.room_qr_requests
    monkeypatch.setattr(routers.room_qr_requests, "_verify_guest_session", mock_verify)


def test_api_session_security(mock_session, mock_db):
    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"

    # Missing session
    res = client.get(url)
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"

    # Expired session
    res = client.get(url, headers={"X-Guest-Session": "expired"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"

    # Revoked session
    res = client.get(url, headers={"X-Guest-Session": "revoked"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"

    # Checkout session
    res = client.get(url, headers={"X-Guest-Session": "checkout"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"

    # Room-moved session
    res = client.get(url, headers={"X-Guest-Session": "room_moved"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"

    # Wrong tenant/room scope mapping
    res2 = client.get(f"/api/public/room-qr/wrong_tenant/{TEST_ROOM}/catalogue", headers={"X-Guest-Session": "valid_token"})
    assert res2.status_code == 403

    # Scope: Missing property_id
    res_miss = client.get(url, headers={"X-Guest-Session": "missing_prop"})
    assert res_miss.status_code == 403

    # Scope: Different property_id (testing that route ignores any request-controlled property and uses booking's property, which is other_prop. We get 200 since it defaults to standard catalogue)
    res_diff = client.get(url + "?property_id=hacked_prop", headers={"X-Guest-Session": "different_prop"})
    assert res_diff.status_code == 200

    # Scope: Session/booking scope mismatch
    res_mis = client.get(url, headers={"X-Guest-Session": "session_booking_mismatch"})
    assert res_mis.status_code == 403

def assert_privacy(data):
    """Recursively inspect data to ensure forbidden keys and concrete fixture values do not exist."""
    forbidden_keys = {
        "_id", "tenant_id", "property_id", "booking_id", "guest_id", "guest_name",
        "guest_session_id", "token", "token_hash", "session_hash", "checkout_at", "occupancy"
    }
    forbidden_values = {
        TEST_TENANT, TEST_PROPERTY, TEST_ROOM, "valid_token", "fake_id",
        "test_booking_123", "test_guest_123", "test_session_123", "mocked_token_hash", "mocked_session_hash"
    }

    if isinstance(data, dict):
        for k, v in data.items():
            if k in forbidden_keys:
                raise AssertionError(f"Privacy leak: found forbidden key {k}")
            if isinstance(v, str) and v in forbidden_values:
                raise AssertionError(f"Privacy leak: found forbidden value {v} in key {k}")
            assert_privacy(v)
    elif isinstance(data, list):
        for item in data:
            assert_privacy(item)


def test_api_modes_default(mock_session, mock_db):
    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["catalogue_version"] == 1
    assert "departments" in data
    assert "services" in data
    assert_privacy(data)

def test_api_modes_disabled(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "disabled"
        })
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"
    assert_privacy(res.json())

def test_malformed_settings_fails_closed(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "invalid_mode_here"
        })
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"
    assert_privacy(res.json())

def test_settings_with_mongo_id_accepted(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "_id": "some_mongo_id", "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "default"
        })
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200, res.text
    assert_privacy(res.json())

def test_settings_with_unknown_field_fails_closed(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured",
            "unknown_extra_field": "hacker_data"
        })
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"
    assert_privacy(res.json())

def test_no_settings_stored_records_returns_default(mock_session, mock_db):
    async def setup():
        # No settings inserted!
        await mock_db["guest_service_departments"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "stored.dept",
            "labels": {"en": "Stored"}, "icon": "check", "enabled": True, "display_order": 1,
            "created_at": datetime.now(), "updated_at": datetime.now()
        })
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200, res.text
    data = res.json()
    dept_codes = [d["department_code"] for d in data["departments"]]
    assert "stored.dept" not in dept_codes # Should be default catalogue!
    assert "housekeeping" in dept_codes # Example default dept

def test_mode_default_stored_records_returns_default(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "default"
        })
        await mock_db["guest_service_departments"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "stored.dept",
            "labels": {"en": "Stored"}, "icon": "check", "enabled": True, "display_order": 1,
            "created_at": datetime.now(), "updated_at": datetime.now()
        })
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200, res.text
    data = res.json()
    dept_codes = [d["department_code"] for d in data["departments"]]
    assert "stored.dept" not in dept_codes # Should be default catalogue!
    assert "housekeeping" in dept_codes # Example default dept


def test_api_service_filtering(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        await mock_db["guest_service_departments"].insert_many([
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
        await mock_db["guest_service_items"].insert_many([
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
    assert res.status_code == 200, res.text
    data = res.json()

    dept_codes = [d["department_code"] for d in data["departments"]]
    assert "enabled.dept" in dept_codes
    assert "disabled.dept" not in dept_codes

    srv_codes = [s["service_code"] for s in data["services"]]
    assert "srv.1" in srv_codes
    assert "srv.disabled" not in srv_codes
    assert "srv.orphan" not in srv_codes
    assert_privacy(data)

def test_configured_department_with_zero_services_is_removed(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        await mock_db["guest_service_departments"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "usable.dept",
                "labels": {"en": "Usable"}, "icon": "check", "enabled": True, "display_order": 1,
                "created_at": datetime.now(), "updated_at": datetime.now()
            },
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "empty.dept",
                "labels": {"en": "Empty"}, "icon": "check", "enabled": True, "display_order": 2,
                "created_at": datetime.now(), "updated_at": datetime.now()
            }
        ])
        await mock_db["guest_service_items"].insert_one(
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "usable.dept",
                "service_code": "srv.usable", "labels": {"en": "Srv1"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "display_order": 1, "created_at": datetime.now(), "updated_at": datetime.now()
            }
        )
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200, res.text
    data = res.json()
    dept_codes = [d["department_code"] for d in data["departments"]]
    assert "usable.dept" in dept_codes
    assert "empty.dept" not in dept_codes

def test_api_configured_empty(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        # Department exists but NO valid services
        await mock_db["guest_service_departments"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "empty.dept",
            "labels": {"en": "Empty"}, "icon": "check", "enabled": True, "display_order": 2,
            "created_at": datetime.now(), "updated_at": datetime.now()
        })
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Hizmet şu anda kullanılamıyor"


def test_deterministic_sorting(mock_session, mock_db):
    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        await mock_db["guest_service_departments"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "b.dept",
                "labels": {"en": "B"}, "icon": "check", "enabled": True, "display_order": 1,
                "created_at": datetime.now(), "updated_at": datetime.now()
            },
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "a.dept",
                "labels": {"en": "A"}, "icon": "check", "enabled": True, "display_order": 1, # Same order
                "created_at": datetime.now(), "updated_at": datetime.now()
            }
        ])
        await mock_db["guest_service_items"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "b.dept",
                "service_code": "z.srv", "labels": {"en": "Z"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "display_order": 5, "created_at": datetime.now(), "updated_at": datetime.now()
            },
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "a.dept",
                "service_code": "y.srv", "labels": {"en": "Y"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "display_order": 5, "created_at": datetime.now(), "updated_at": datetime.now()
            }
        ])
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 200, res.text
    data = res.json()
    dept_codes = [d["department_code"] for d in data["departments"]]
    assert dept_codes == ["a.dept", "b.dept"] # Alphabetical fallback

    srv_codes = [s["service_code"] for s in data["services"]]
    assert srv_codes == ["y.srv", "z.srv"]

def test_time_injection_and_service_hours(mock_session, mock_db, monkeypatch):
    import datetime

    class FrozenTime:
        def __init__(self, dt):
            self.dt = dt
        def astimezone(self, tz):
            return self.dt.astimezone(tz)
        def isoformat(self):
            return self.dt.isoformat()

    def set_time(hour, minute):
        import zoneinfo
        dt = datetime.datetime.now(datetime.UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)

        def mock_utc_now():
            return FrozenTime(dt)

        import routers.room_qr_requests
        monkeypatch.setattr(routers.room_qr_requests, "_utc_now", mock_utc_now)
        import domains.guest.qr_catalogue_service
        monkeypatch.setattr(domains.guest.qr_catalogue_service, "_utc_now", mock_utc_now)

    async def setup():
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        await mock_db["guest_service_departments"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "time.dept",
            "labels": {"en": "Time"}, "icon": "check", "enabled": True, "display_order": 1,
            "created_at": datetime.datetime.now(), "updated_at": datetime.datetime.now()
        })
        await mock_db["guest_service_items"].insert_many([
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "time.dept",
                "service_code": "srv.normal", "labels": {"en": "Normal"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "service_hours": {"start": "10:00", "end": "18:00"},
                "display_order": 1, "created_at": datetime.datetime.now(), "updated_at": datetime.datetime.now()
            },
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "time.dept",
                "service_code": "srv.overnight", "labels": {"en": "Overnight"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "service_hours": {"start": "20:00", "end": "04:00"},
                "display_order": 2, "created_at": datetime.datetime.now(), "updated_at": datetime.datetime.now()
            },
            {
                "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "time.dept",
                "service_code": "srv.malformed", "labels": {"en": "Malformed"}, "icon": "s1", "enabled": True,
                "input_type": "one_tap", "input_config": {},
                "service_hours": {"start": "10:00", "end": "10:00"}, # start == end
                "display_order": 3, "created_at": datetime.datetime.now(), "updated_at": datetime.datetime.now()
            }
        ])
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"

    # Test at 12:00 UTC (Normal is inside, Overnight is outside)
    set_time(12, 0)
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    data = res.json()
    codes = [s["service_code"] for s in data["services"]]
    assert "srv.normal" in codes
    assert "srv.overnight" not in codes
    assert "srv.malformed" not in codes

    # Test at 23:00 UTC (Normal is outside, Overnight is inside (before midnight))
    set_time(23, 0)
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    data = res.json()
    codes = [s["service_code"] for s in data["services"]]
    assert "srv.normal" not in codes
    assert "srv.overnight" in codes

    # Test at 02:00 UTC (Normal is outside, Overnight is inside (after midnight))
    set_time(2, 0)
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    data = res.json()
    codes = [s["service_code"] for s in data["services"]]
    assert "srv.normal" not in codes
    assert "srv.overnight" in codes

    # Test malformed timezone
    async def modify_tz(tz_val):
        props = mock_db["properties"]
        props.data[0]["timezone"] = tz_val

    # Boundary semantics tests (half-open range)
    # normal: 10:00 to 18:00
    # overnight: 20:00 to 04:00

    # exact start (normal) -> inside (normal is open)
    set_time(10, 0)
    res_start = client.get(url, headers={"X-Guest-Session": "valid_token"})
    codes_start = [s["service_code"] for s in res_start.json()["services"]]
    assert "srv.normal" in codes_start

    # exact end (normal) -> outside (half-open). Overnight starts at 20:00, so at 18:00 NO services are open.
    set_time(18, 0)
    res_end = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res_end.status_code == 403
    assert res_end.json()["detail"] == "Hizmet şu anda kullanılamıyor"

    # exact start (overnight) -> inside
    set_time(20, 0)
    res_ov_start = client.get(url, headers={"X-Guest-Session": "valid_token"})
    codes_ov_start = [s["service_code"] for s in res_ov_start.json()["services"]]
    assert "srv.overnight" in codes_ov_start

    # exact end (overnight) -> outside (half-open). Normal starts at 10:00, so at 04:00 NO services are open.
    set_time(4, 0)
    res_ov_end = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res_ov_end.status_code == 403
    assert res_ov_end.json()["detail"] == "Hizmet şu anda kullanılamıyor"

    # Missing / Unknown Timezone -> fails closed
    asyncio.run(modify_tz("Invalid/Timezone"))
    set_time(12, 0)
    res = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res.status_code == 403

    # Absent Timezone -> defaults to UTC, allows services according to UTC
    async def remove_tz():
        props = mock_db["properties"]
        if "timezone" in props.data[0]:
            del props.data[0]["timezone"]

    asyncio.run(remove_tz())
    set_time(12, 0) # 12:00 UTC
    res_absent = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res_absent.status_code == 200
    data_absent = res_absent.json()
    codes_absent = [s["service_code"] for s in data_absent["services"]]
    assert "srv.normal" in codes_absent
    assert "srv.overnight" not in codes_absent

    # No services open (e.g. 19:00 UTC) -> 403
    set_time(19, 0)
    res_empty = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res_empty.status_code == 403
    assert res_empty.json()["detail"] == "Hizmet şu anda kullanılamıyor"

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

    # Settings Validation
    with pytest.raises(ValidationError):
        GuestServiceCatalogueSettings(tenant_id="t", property_id="p", mode="unknown_mode")


def test_ensure_indexes_exact(mock_db):
    """
    Proves exact create_index calls, key ordering and unique flags requested by application code.
    This does NOT prove actual Mongo index installation, as it tests against the FakeAsyncCollection.
    """
    from routers.room_qr_requests import _ensure_indexes
    async def _run():
        import routers.room_qr_requests
        routers.room_qr_requests._INDEXES_READY = False
        await _ensure_indexes()

        # Verify settings unique lookup
        settings_idx = await mock_db["guest_service_catalogue_settings"].index_information()
        assert "gsc_settings_lookup" in settings_idx
        assert settings_idx["gsc_settings_lookup"]["unique"] == True
        assert settings_idx["gsc_settings_lookup"]["key"] == [("tenant_id", 1), ("property_id", 1)]

        # Verify department indexes
        dept_idx = await mock_db["guest_service_departments"].index_information()
        assert "gsc_dept_unique" in dept_idx
        assert dept_idx["gsc_dept_unique"]["unique"] == True
        assert dept_idx["gsc_dept_unique"]["key"] == [("tenant_id", 1), ("property_id", 1), ("department_code", 1)]

        assert "gsc_dept_order" in dept_idx
        assert dept_idx["gsc_dept_order"].get("unique") is None # false
        assert dept_idx["gsc_dept_order"]["key"] == [("tenant_id", 1), ("property_id", 1), ("enabled", 1), ("display_order", 1)]

        # Verify items indexes
        items_idx = await mock_db["guest_service_items"].index_information()
        assert "gsc_item_unique" in items_idx
        assert items_idx["gsc_item_unique"]["unique"] == True
        assert items_idx["gsc_item_unique"]["key"] == [("tenant_id", 1), ("property_id", 1), ("service_code", 1)]

        assert "gsc_item_order" in items_idx
        assert items_idx["gsc_item_order"].get("unique") is None
        assert items_idx["gsc_item_order"]["key"] == [("tenant_id", 1), ("property_id", 1), ("department_code", 1), ("enabled", 1), ("display_order", 1)]

    asyncio.run(_run())


def test_get_and_post_catalogue_shared_dependency(mock_session, mock_db):
    # This regression test proves GET and POST use the same shared DB/resolver dependency.
    # It must fail if GET silently falls back to defaults while configured records exist in the injected db.
    async def setup():
        await mock_db["rooms"].insert_one({"id": TEST_ROOM, "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY})
        await mock_db["guest_service_catalogue_settings"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "mode": "configured"
        })
        await mock_db["guest_service_departments"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "shared.dept",
            "labels": {"en": "Shared"}, "icon": "check", "enabled": True, "display_order": 1,
            "created_at": datetime.now(), "updated_at": datetime.now()
        })
        await mock_db["guest_service_items"].insert_one({
            "tenant_id": TEST_TENANT, "property_id": TEST_PROPERTY, "department_code": "shared.dept",
            "service_code": "shared.srv", "labels": {"en": "Shared Service"}, "icon": "s1", "enabled": True,
            "input_type": "one_tap", "input_config": {},
            "display_order": 1, "created_at": datetime.now(), "updated_at": datetime.now()
        })

    import asyncio
    asyncio.run(setup())

    url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/catalogue"
    res_get = client.get(url, headers={"X-Guest-Session": "valid_token"})
    assert res_get.status_code == 200
    data = res_get.json()
    assert len(data["departments"]) == 1
    assert data["departments"][0]["department_code"] == "shared.dept"

    post_url = f"/api/public/room-qr/{TEST_TENANT}/{TEST_ROOM}/submit"
    payload = {
        "language": "en",
        "idempotency_key": "test_idem_123",
        "items": [
            {
                "service_code": "shared.srv",
                "value": {}
            }
        ]
    }
    res_post = client.post(post_url, headers={"X-Guest-Session": "valid_token"}, json=payload)
    assert res_post.status_code == 200, res_post.text
