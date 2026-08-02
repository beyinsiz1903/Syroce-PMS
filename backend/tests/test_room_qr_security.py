import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.room_qr_requests import router

@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router)
    return app

@pytest.fixture
def client(test_app):
    return TestClient(test_app)

from unittest.mock import MagicMock
@pytest.fixture
def mock_db():
    mock_collections = {}
    def get_collection(name):
        if name not in mock_collections:
            mock_collections[name] = MagicMock()
        return mock_collections[name]
        
    with patch("routers.room_qr_requests.raw_db") as db:
        db.__getitem__.side_effect = get_collection
        
        async def mock_rooms_find_one(*args, **kwargs):
            return {"id": "r1", "is_active": True, "room_number": "101"}
        async def mock_bookings_find_one(*args, **kwargs):
            return {"id": "b1", "guest_name": "Test", "property_id": "p1", "departure_date": "2026-08-04T12:00:00Z"}
        async def mock_sessions_find_one(*args, **kwargs):
            return {"booking_id": "b1", "expires_at": None, "revoked_at": None}
            
        db["rooms"].find_one = AsyncMock(side_effect=mock_rooms_find_one)
        db["bookings"].find_one = AsyncMock(side_effect=mock_bookings_find_one)
        db["room_guest_sessions"].find_one = AsyncMock(side_effect=mock_sessions_find_one)
        db["room_guest_sessions"].insert_one = AsyncMock()
        db["room_qr_requests"].insert_one = AsyncMock()
        db["service_complaints"].insert_one = AsyncMock()
        
        yield db

@pytest.fixture
def mock_dependencies():
    with patch("routers.room_qr_requests._verify_token", return_value=True), \
         patch("routers.room_qr_requests._rl_check", return_value=True), \
         patch("routers.room_qr_requests._get_qr_salt", new_callable=AsyncMock, return_value=None):
        yield

def test_session_creation_success(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/session?t=valid")
    assert r.status_code == 200
    assert "session_token" in r.json()
    assert mock_db["room_guest_sessions"].insert_one.called

def test_session_creation_fails_empty_room(client, mock_db, mock_dependencies):
    async def mock_bookings_find_one_empty(*args, **kwargs):
        return None
    mock_db["bookings"].find_one.side_effect = mock_bookings_find_one_empty
    
    r = client.post("/api/public/room-qr/t1/r1/session?t=valid")
    assert r.status_code == 403
    assert r.json()["detail"] == "Hizmet şu anda kullanılamıyor"

def test_session_creation_fails_inactive_room(client, mock_db, mock_dependencies):
    async def mock_rooms_find_one_inactive(*args, **kwargs):
        return {"id": "r1", "is_active": False}
    mock_db["rooms"].find_one.side_effect = mock_rooms_find_one_inactive
    
    r = client.post("/api/public/room-qr/t1/r1/session?t=valid")
    assert r.status_code == 410

def test_protected_endpoint_success(client, mock_db, mock_dependencies):
    payload = {
        "category": "towels",
        "description": "Need towels",
        "priority": "normal",
        "language": "en"
    }
    
    r = client.post("/api/public/room-qr/t1/r1/submit", json=payload, headers={"X-Guest-Session": "secret"})
    assert r.status_code == 200
    assert mock_db["room_qr_requests"].insert_one.called

def test_protected_endpoint_fails_invalid_session(client, mock_db, mock_dependencies):
    async def mock_sessions_find_one_empty(*args, **kwargs):
        return None
    mock_db["room_guest_sessions"].find_one.side_effect = mock_sessions_find_one_empty
    
    payload = {
        "category": "towels",
        "description": "Need towels",
        "priority": "normal",
        "language": "en"
    }
    
    r = client.post("/api/public/room-qr/t1/r1/submit", json=payload, headers={"X-Guest-Session": "invalid"})
    assert r.status_code == 401
    assert "Geçersiz oturum" in r.json()["detail"]
