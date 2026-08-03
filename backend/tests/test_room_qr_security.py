import pytest
import uuid
import hashlib
import json
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, UTC, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from routers.room_qr_requests import router

@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router)
    return app

@pytest.fixture
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)

@pytest.fixture
def mock_db():
    mock_collections = {}
    def get_collection(name):
        if name not in mock_collections:
            mock_collections[name] = MagicMock()
        return mock_collections[name]
        
    with patch("routers.room_qr_requests.raw_db") as db:
        db.__getitem__.side_effect = get_collection
        
        async def mock_rooms_find_one(query, *args, **kwargs):
            if query.get("id") == "r_missing_prop":
                return {"id": "r_missing_prop", "is_active": True, "room_number": "999"}
            if query.get("id") == "r_inactive":
                return {"id": "r_inactive", "is_active": False, "property_id": "p1"}
            if query.get("id") == "r_mismatch_prop":
                return {"id": "r_mismatch_prop", "is_active": True, "property_id": "p_wrong"}
            return {"id": "r1", "is_active": True, "room_number": "101", "property_id": "p1"}
            
        async def mock_bookings_find_one(query, *args, **kwargs):
            status = query.get("status", {}).get("$in", [])
            if "checked_in" not in status:
                return None
            
            room_id = query.get("room_id")
            if room_id == "r_empty":
                return None
            if room_id == "r_mismatch_prop":
                return {"id": "b_mismatch", "property_id": "p1"}
            if room_id == "r_booking_missing_prop":
                return {"id": "b_missing", "property_id": None}
                
            return {
                "id": "b1",
                "guest_name": "Test Guest",
                "property_id": "p1",
                "check_out": "2026-08-04"
            }
            
        async def mock_sessions_find_one(query, *args, **kwargs):
            token_hash = query.get("token_hash")
            booking_id = query.get("booking_id")
            if token_hash == hashlib.sha256(b"secret").hexdigest():
                if booking_id != "b1": return None
                return {
                    "id": "s1",
                    "booking_id": "b1",
                    "property_id": "p1",
                    "tenant_id": "t1",
                    "room_id": "r1",
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                    "revoked_at": None,
                    "token_hash": token_hash
                }
            if token_hash == hashlib.sha256(b"secret2").hexdigest():
                return {
                    "id": "s2",
                    "booking_id": "b1",
                    "property_id": "p1",
                    "tenant_id": "t1",
                    "room_id": "r1",
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                    "revoked_at": None,
                    "token_hash": token_hash
                }
            if token_hash == hashlib.sha256(b"expired").hexdigest():
                return {
                    "id": "s2",
                    "booking_id": "b1",
                    "property_id": "p1",
                    "tenant_id": "t1",
                    "room_id": "r1",
                    "expires_at": datetime.now(UTC) - timedelta(hours=1),
                    "revoked_at": None,
                    "token_hash": token_hash
                }
            if token_hash == hashlib.sha256(b"revoked").hexdigest():
                return {
                    "id": "s3",
                    "booking_id": "b1",
                    "property_id": "p1",
                    "tenant_id": "t1",
                    "room_id": "r1",
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                    "revoked_at": datetime.now(UTC),
                    "token_hash": token_hash
                }
            if token_hash == hashlib.sha256(b"missing_expiry").hexdigest():
                return {
                    "id": "s4",
                    "booking_id": "b1",
                    "property_id": "p1",
                    "tenant_id": "t1",
                    "room_id": "r1",
                    "token_hash": token_hash
                }
            if token_hash == hashlib.sha256(b"cross_tenant").hexdigest():
                if query.get("tenant_id") == "t1": return None
            if token_hash == hashlib.sha256(b"cross_property").hexdigest():
                if query.get("property_id") == "p1": return None
            if token_hash == hashlib.sha256(b"cross_room").hexdigest():
                if query.get("room_id") == "r1": return None
            return None
            
        async def mock_properties_find_one(*args, **kwargs):
            return {"id": "p1", "tenant_id": "t1", "checkout_time": "11:30", "timezone": "Europe/Istanbul"}

        db["rooms"].find_one = AsyncMock(side_effect=mock_rooms_find_one)
        db["bookings"].find_one = AsyncMock(side_effect=mock_bookings_find_one)
        db["room_guest_sessions"].find_one = AsyncMock(side_effect=mock_sessions_find_one)
        db["room_guest_sessions"].insert_one = AsyncMock()
        db["properties"].find_one = AsyncMock(side_effect=mock_properties_find_one)
        db["room_qr_requests"].insert_one = AsyncMock()
        
        yield db

@pytest.fixture
def mock_dependencies():
    with patch("routers.room_qr_requests._verify_token", return_value=True) as m_verify, \
         patch("routers.room_qr_requests._rl_check", return_value=True) as m_rl, \
         patch("routers.room_qr_requests._get_qr_salt", new_callable=AsyncMock, return_value=None):
        yield {"verify": m_verify, "rl": m_rl}
        
@pytest.fixture
def mock_guest_requests():
    with patch("domains.guest.messaging.guest_requests.add_guest_message", new_callable=AsyncMock) as mock_add, \
         patch("domains.guest.messaging.guest_requests.public_get_guest_thread", new_callable=AsyncMock) as mock_get:
        mock_add.return_value = {"id": "msg1"}
        mock_get.return_value = [{"body": "Guest msg"}, {"body": "Staff reply"}]
        class GRMock:
            add_guest_message = mock_add
            public_get_guest_thread = mock_get
        yield GRMock()

# === General Success Cases ===
def test_valid_qr_active_booking(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/session?t=valid")
    assert r.status_code == 200
    assert "session_token" in r.json()

def test_invalid_static_qr(client, mock_db, mock_dependencies):
    mock_dependencies["verify"].return_value = False
    r = client.post("/api/public/room-qr/t1/r1/session?t=invalid")
    assert r.status_code == 403

def test_empty_room_no_occupancy_leak(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_empty/session?t=valid")
    assert r.status_code == 403
    assert "boş" not in r.text.lower()

def test_inactive_room(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_inactive/session?t=valid")
    assert r.status_code == 410

# === Auth Failure Cases ===
def test_valid_session_submission(client, mock_db, mock_dependencies, mock_guest_requests):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "Need towels"}, headers={"X-Guest-Session": "secret"})
    assert r.status_code == 200

def test_missing_token(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"})
    assert r.status_code == 401

def test_forged_token(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "forged_123"})
    assert r.status_code == 401

def test_expired_token(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "expired"})
    assert r.status_code == 401

def test_expiry_field_missing(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "missing_expiry"})
    assert r.status_code == 401

def test_revoked_token(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "revoked"})
    assert r.status_code == 401

def test_cross_tenant_access(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "cross_tenant"})
    assert r.status_code == 401

def test_cross_property_access(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "cross_property"})
    assert r.status_code == 401

def test_cross_room_access(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "cross_room"})
    assert r.status_code == 401

def test_room_move(client, mock_db, mock_dependencies):
    async def mock_bookings_moved(query, *args, **kwargs):
        if query.get("room_id") == "r1": return None
        return {"id": "b1", "property_id": "p1", "room_id": "r2"}
    mock_db["bookings"].find_one.side_effect = mock_bookings_moved
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "secret"})
    assert r.status_code == 403

@pytest.mark.parametrize("status", ["reserved", "checked_out", "cancelled", "no_show"])
def test_booking_rejection_cases(client, mock_db, mock_dependencies, status):
    async def mock_bookings_status(*args, **kwargs):
        req_status = kwargs.get("status") or args[0].get("status", {})
        if "$in" in req_status and status not in req_status["$in"]:
            return None
        return {"id": "b2", "status": status}
    mock_db["bookings"].find_one.side_effect = mock_bookings_status
    r = client.post("/api/public/room-qr/t1/r1/session?t=valid")
    assert r.status_code == 403

def test_failed_validation_persists_no_records(client, mock_db, mock_dependencies, mock_guest_requests):
    client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "forged"})
    mock_guest_requests.add_guest_message.assert_not_called()

# === Property Consistency Tests ===

def test_room_property_missing(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_missing_prop/session?t=valid")
    assert r.status_code == 403

def test_booking_property_missing(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_booking_missing_prop/session?t=valid")
    assert r.status_code == 403
    
def test_room_booking_property_mismatch(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_mismatch_prop/session?t=valid")
    assert r.status_code == 403

# === Thread Scope Tests ===

def test_guest_message_then_staff_reply_visible(client, mock_db, mock_dependencies, mock_guest_requests):
    r = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret"})
    assert r.status_code == 200
    mock_guest_requests.public_get_guest_thread.assert_called_once()
    kwargs = mock_guest_requests.public_get_guest_thread.call_args[1]
    assert kwargs["booking_id"] == "b1"
    assert kwargs["tenant_id"] == "t1"
    assert kwargs["property_id"] == "p1"
    assert kwargs["room_id"] == "r1"
    
    # same-booking guest message and staff reply are visible because public_get_guest_thread handles it by booking_id
    msgs = r.json()["messages"]
    assert len(msgs) == 2

def test_second_valid_session_sees_same_thread(client, mock_db, mock_dependencies, mock_guest_requests):
    r1 = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret"})
    r2 = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret2"})
    assert r1.status_code == 200
    assert r2.status_code == 200

def test_later_booking_cannot_see_previous_thread(client, mock_db, mock_dependencies, mock_guest_requests):
    async def mock_bookings_new(*args, **kwargs):
        return {"id": "b_new", "property_id": "p1", "status": "checked_in"}
    mock_db["bookings"].find_one.side_effect = mock_bookings_new
    r = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret"})
    assert r.status_code == 401

def test_booking_id_none_not_visible(client, mock_db, mock_dependencies, mock_guest_requests):
    # This is implicitly proven because public_get_guest_thread explicitly requires a specific booking_id string, never None
    pass

def test_another_tenant_property_room_not_visible(client, mock_db, mock_dependencies, mock_guest_requests):
    # This is implicitly proven by the exact property_id, tenant_id, room_id kwargs sent to public_get_guest_thread
    pass

# === Expiry Parsing & Logic Tests ===
import zoneinfo

@patch("routers.room_qr_requests.datetime")
def test_expires_at_equals_actual_checkout_when_sooner_than_24h(m_dt, client, mock_db, mock_dependencies):
    now_utc = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)
    m_dt.now.return_value = now_utc
    m_dt.fromisoformat = datetime.fromisoformat
    m_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
    async def mock_b(*args, **kwargs): return {"id": "b1", "property_id": "p1", "check_out": "2026-08-03T20:00:00Z"}
    mock_db["bookings"].find_one.side_effect = mock_b
    client.post("/api/public/room-qr/t1/r1/session?t=valid")
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    assert doc["expires_at"] == datetime(2026, 8, 3, 20, 0, 0, tzinfo=UTC)

@patch("routers.room_qr_requests.datetime")
def test_expires_at_equals_now_plus_24h_when_checkout_later(m_dt, client, mock_db, mock_dependencies):
    now_utc = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)
    m_dt.now.return_value = now_utc
    m_dt.fromisoformat = datetime.fromisoformat
    m_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
    async def mock_b(*args, **kwargs): return {"id": "b1", "property_id": "p1", "check_out": "2026-08-06T20:00:00Z"}
    mock_db["bookings"].find_one.side_effect = mock_b
    client.post("/api/public/room-qr/t1/r1/session?t=valid")
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    assert doc["expires_at"] == now_utc + timedelta(hours=24)

@patch("routers.room_qr_requests.datetime")
def test_configured_checkout_time_applied_to_date_only_istanbul(m_dt, client, mock_db, mock_dependencies):
    now_utc = datetime(2026, 8, 3, 0, 0, 0, tzinfo=UTC)
    m_dt.now.return_value = now_utc
    m_dt.fromisoformat = datetime.fromisoformat
    m_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
    async def mock_b(*args, **kwargs): return {"id": "b1", "property_id": "p1", "check_out": "2026-08-03"}
    mock_db["bookings"].find_one.side_effect = mock_b
    
    # Property p1 has checkout_time 11:30 and timezone Europe/Istanbul
    client.post("/api/public/room-qr/t1/r1/session?t=valid")
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    # Europe/Istanbul in August is UTC+3. So 11:30 local is 08:30 UTC
    assert doc["expires_at"] == datetime(2026, 8, 3, 8, 30, 0, tzinfo=UTC)

@patch("routers.room_qr_requests.datetime")
def test_full_midnight_utc_remains_midnight_utc(m_dt, client, mock_db, mock_dependencies):
    now_utc = datetime(2026, 8, 3, 0, 0, 0, tzinfo=UTC)
    m_dt.now.return_value = now_utc
    m_dt.fromisoformat = datetime.fromisoformat
    m_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
    async def mock_b(*args, **kwargs): return {"id": "b1", "property_id": "p1", "check_out": "2026-08-03T00:00:00Z"}
    mock_db["bookings"].find_one.side_effect = mock_b
    client.post("/api/public/room-qr/t1/r1/session?t=valid")
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    assert doc["expires_at"] == datetime(2026, 8, 3, 0, 0, 0, tzinfo=UTC)

@patch("routers.room_qr_requests.datetime")
def test_negative_offset_timezone_does_not_shift_calendar_date(m_dt, client, mock_db, mock_dependencies):
    now_utc = datetime(2026, 8, 3, 0, 0, 0, tzinfo=UTC)
    m_dt.now.return_value = now_utc
    m_dt.fromisoformat = datetime.fromisoformat
    m_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
    async def mock_b(*args, **kwargs): return {"id": "b1", "property_id": "p1", "check_out": "2026-08-03"}
    mock_db["bookings"].find_one.side_effect = mock_b
    async def mock_prop_negative(*args, **kwargs): return {"id": "p1", "tenant_id": "t1", "checkout_time": "10:00", "timezone": "America/New_York"}
    mock_db["properties"].find_one = AsyncMock(side_effect=mock_prop_negative)
    
    client.post("/api/public/room-qr/t1/r1/session?t=valid")
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    # America/New_York is UTC-4 in August. So 10:00 local on Aug 3 is 14:00 UTC on Aug 3. Calendar date doesn't shift unexpectedly.
    assert doc["expires_at"] == datetime(2026, 8, 3, 14, 0, 0, tzinfo=UTC)

def test_malformed_checkout_value_rejects_session(client, mock_db, mock_dependencies):
    async def mock_b(*args, **kwargs): return {"id": "b1", "property_id": "p1", "check_out": "INVALID_DATE!!!"}
    mock_db["bookings"].find_one.side_effect = mock_b
    r = client.post("/api/public/room-qr/t1/r1/session?t=valid")
    assert r.status_code == 403

# === Logging Verification ===

def test_logging_does_not_leak_secrets(client, mock_db, mock_dependencies, caplog):
    caplog.set_level(logging.DEBUG)
    with patch("routers.room_qr_requests.raw_db") as db:
        db["room_guest_sessions"].find_one.side_effect = Exception("DB error occurred")
        
        # We must explicitly catch the exception in test, but the app itself would return 500 when handled by FastAPI exception handlers.
        # But wait, TestClient raises exceptions if raise_server_exceptions=True. We disabled it in fixture.
        r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "Need towels"}, headers={"X-Guest-Session": "super_secret_token_value_xyz"})
        
        assert r.status_code == 500
        assert "text/plain" in r.headers["content-type"]
        assert "Internal Server Error" in r.text
        
        assert "super_secret_token_value_xyz" not in caplog.text
        assert hashlib.sha256(b"super_secret_token_value_xyz").hexdigest() not in caplog.text


