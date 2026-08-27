import hashlib
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from routers.room_qr_requests import router

# 3. Controlled JSON errors: application exception handler
app = FastAPI()
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )
app.include_router(router)

@pytest.fixture
def test_app():
    return app

@pytest.fixture
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)

# Fake in-memory messages collection to test public_get_guest_thread query behavior
fake_messages_db = [
    {"id": "msg_b1_guest", "tenant_id": "t1", "property_id": "p1", "room_id": "r1", "booking_id": "b1", "body": "Guest msg", "created_at": datetime(2026, 8, 1, 10, 0, 0, tzinfo=UTC)},
    {"id": "msg_b1_staff", "tenant_id": "t1", "property_id": "p1", "room_id": "r1", "booking_id": "b1", "body": "Staff reply", "created_at": datetime(2026, 8, 1, 11, 0, 0, tzinfo=UTC)},
    {"id": "msg_b_none", "tenant_id": "t1", "property_id": "p1", "room_id": "r1", "booking_id": None, "body": "None booking", "created_at": datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)},
    {"id": "msg_b_other", "tenant_id": "t1", "property_id": "p1", "room_id": "r1", "booking_id": "b2", "body": "Other booking msg", "created_at": datetime(2026, 8, 1, 13, 0, 0, tzinfo=UTC)},
    {"id": "msg_diff_prop", "tenant_id": "t1", "property_id": "p2", "room_id": "r1", "booking_id": "b1", "body": "Diff prop", "created_at": datetime(2026, 8, 1, 14, 0, 0, tzinfo=UTC)},
    {"id": "msg_diff_room", "tenant_id": "t1", "property_id": "p1", "room_id": "r2", "booking_id": "b1", "body": "Diff room", "created_at": datetime(2026, 8, 1, 15, 0, 0, tzinfo=UTC)},
    {"id": "msg_diff_tenant", "tenant_id": "t2", "property_id": "p1", "room_id": "r1", "booking_id": "b1", "body": "Diff tenant", "created_at": datetime(2026, 8, 1, 16, 0, 0, tzinfo=UTC)},
]

@pytest.fixture
def mock_db():
    mock_collections = {}
    def get_collection(name):
        if name not in mock_collections:
            mock_collections[name] = MagicMock()
        return mock_collections[name]

    with patch("routers.room_qr_requests.raw_db") as db, \
         patch("domains.guest.messaging.guest_requests.raw_db") as gr_db, \
         patch("domains.guest.messaging.guest_requests_router.raw_db") as router_db:

        db.__getitem__.side_effect = get_collection
        gr_db.__getitem__.side_effect = get_collection
        router_db.__getitem__.side_effect = get_collection

        async def mock_rooms_find_one(query, *args, **kwargs):
            if query.get("id") == "r_missing_prop":
                return {"id": "r_missing_prop", "is_active": True, "room_number": "999"}
            if query.get("id") == "r_both_missing_prop":
                return {"id": "r_both_missing_prop", "is_active": True, "room_number": "998"}
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
            if room_id == "r_both_missing_prop":
                return {"id": "b_both_missing", "property_id": None}

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

        # Fake cursor for guest_room_messages find()
        class FakeCursor:
            def __init__(self, items):
                self.items = items
            def sort(self, *args, **kwargs): return self
            def limit(self, *args, **kwargs): return self
            def __aiter__(self):
                self.iter = iter(self.items)
                return self
            async def __anext__(self):
                try:
                    return next(self.iter)
                except StopIteration:
                    raise StopAsyncIteration

        def mock_messages_find(query, *args, **kwargs):
            results = []
            for m in fake_messages_db:
                match = True
                for k, v in query.items():
                    if m.get(k) != v:
                        match = False
                        break
                if match:
                    results.append(m)
            return FakeCursor(results)

        db["rooms"].find_one = AsyncMock(side_effect=mock_rooms_find_one)
        db["bookings"].find_one = AsyncMock(side_effect=mock_bookings_find_one)
        db["room_guest_sessions"].find_one = AsyncMock(side_effect=mock_sessions_find_one)
        db["room_guest_sessions"].insert_one = AsyncMock()
        db["properties"].find_one = AsyncMock(side_effect=mock_properties_find_one)
        db["room_qr_requests"].insert_one = AsyncMock()
        gr_db["guest_room_messages"].insert_one = AsyncMock()

        # Patch the GR_COLL find for the new thread isolated queries
        gr_db["guest_room_messages"].find = MagicMock(side_effect=mock_messages_find)

        yield db

@pytest.fixture
def mock_dependencies():
    with patch("routers.room_qr_requests._verify_token", return_value=True) as m_verify, \
         patch("routers.room_qr_requests._rl_check", return_value=True) as m_rl, \
         patch("routers.room_qr_requests._get_qr_salt", new_callable=AsyncMock, return_value=None):
        yield {"verify": m_verify, "rl": m_rl}

# === General Success Cases ===
def test_valid_qr_active_booking(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r1/session?t=valid")
    assert r.status_code == 200
    assert "session_token" in r.json()
    rate_limit_key = mock_dependencies["rl"].call_args.args[0]
    assert rate_limit_key.startswith("t1:r1:")
    assert rate_limit_key.endswith(":session")

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
def test_valid_session_submission(client, mock_db, mock_dependencies):
    # No need to mock add_guest_message because it just errors if GR_COLL insert is missing, we can mock it
    with patch("domains.guest.messaging.guest_requests.add_guest_message", new_callable=AsyncMock) as _:
        r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "Need towels"}, headers={"X-Guest-Session": "secret"})
        assert r.status_code == 200
        rate_limit_key = mock_dependencies["rl"].call_args.args[0]
        assert rate_limit_key.startswith("t1:r1:")
        assert rate_limit_key.endswith(":submit")

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

def test_failed_validation_persists_no_records(client, mock_db, mock_dependencies):
    with patch("domains.guest.messaging.guest_requests.add_guest_message", new_callable=AsyncMock) as m_add:
        client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "need"}, headers={"X-Guest-Session": "forged"})
        m_add.assert_not_called()

# === Property Consistency Tests ===
def test_legacy_room_property_missing_uses_booking_property(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_missing_prop/session?t=valid")
    assert r.status_code == 200
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    assert doc["property_id"] == "p1"

def test_legacy_booking_property_missing_uses_room_property(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_booking_missing_prop/session?t=valid")
    assert r.status_code == 200
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    assert doc["property_id"] == "p1"

def test_legacy_room_and_booking_property_missing_use_tenant_scope(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_both_missing_prop/session?t=valid")
    assert r.status_code == 200
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
    assert doc["property_id"] == "t1"

def test_room_booking_property_mismatch(client, mock_db, mock_dependencies):
    r = client.post("/api/public/room-qr/t1/r_mismatch_prop/session?t=valid")
    assert r.status_code == 403

# === Strict Thread Scope Tests ===
def test_guest_and_staff_reply_visible(client, mock_db, mock_dependencies):
    # The actual behavior of public_get_guest_thread is executed since we patched raw_db only
    r = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret"})
    assert r.status_code == 200
    msgs = r.json()["messages"]

    # We should see exactly 2 messages: "msg_b1_guest" and "msg_b1_staff"
    assert len(msgs) == 2
    ids = [m["id"] for m in msgs]
    assert "msg_b1_guest" in ids
    assert "msg_b1_staff" in ids

    # booking_id=None, other booking, diff prop/room/tenant are ALL excluded naturally!
    assert "msg_b_none" not in ids
    assert "msg_b_other" not in ids
    assert "msg_diff_prop" not in ids
    assert "msg_diff_room" not in ids
    assert "msg_diff_tenant" not in ids

def test_renewed_session_sees_same_thread(client, mock_db, mock_dependencies):
    r1 = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret"})
    r2 = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret2"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(r1.json()["messages"]) == 2
    assert len(r2.json()["messages"]) == 2

def test_later_booking_cannot_see_previous_thread(client, mock_db, mock_dependencies):
    async def mock_bookings_new(*args, **kwargs):
        return {"id": "b_new", "property_id": "p1", "status": "checked_in"}
    mock_db["bookings"].find_one.side_effect = mock_bookings_new
    r = client.get("/api/public/room-qr/t1/r1/thread", headers={"X-Guest-Session": "secret"})
    assert r.status_code == 401

# === Expiry Parsing & Logic Tests ===

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

    client.post("/api/public/room-qr/t1/r1/session?t=valid")
    doc = mock_db["room_guest_sessions"].insert_one.call_args[0][0]
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

        r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "Need towels"}, headers={"X-Guest-Session": "super_secret_token_value_xyz"})

        assert r.status_code == 500
        assert r.headers["content-type"] == "application/json"
        assert r.json()["detail"] == "Internal Server Error"

        assert "super_secret_token_value_xyz" not in caplog.text
        assert hashlib.sha256(b"super_secret_token_value_xyz").hexdigest() not in caplog.text

# === Staff Reply Compatibility Test ===

from domains.guest.messaging.guest_requests_router import router as staff_router

app.include_router(staff_router)

def test_integrated_guest_and_staff_reply(client, mock_db, mock_dependencies):
    # 1. Guest creates a message
    r = client.post("/api/public/room-qr/t1/r1/submit", json={"category": "towels", "description": "Need towels"}, headers={"X-Guest-Session": "secret"})
    assert r.status_code == 200

    # Check that guest message insertion contains property_id
    args = mock_db["guest_room_messages"].insert_one.call_args[0][0]
    assert args["property_id"] == "p1"
    assert args["sender_type"] == "guest"

    # 2. Mock auth dependency for staff endpoint
    from unittest.mock import patch

    class FakeUser:
        tenant_id = "t1"
        id = "u1"
        name = "Admin"

    # We must patch get_current_user in guest_requests_router
    with patch("domains.guest.messaging.guest_requests_router.get_current_user", return_value=FakeUser),          patch("domains.guest.messaging.guest_requests_router.require_auth", return_value=FakeUser, create=True):
        # We override dependency globally for this app
        app.dependency_overrides[staff_router.dependencies[0].dependency if staff_router.dependencies else lambda: None] = lambda: FakeUser()

        # Staff replies
        async def mock_last_guest(*args, **kwargs):
            return {"booking_id": "b1", "room_number": "101", "property_id": "p1"}
        mock_db["guest_room_messages"].find_one = AsyncMock(side_effect=mock_last_guest)

        # In reality, FastAPI dependency_overrides needs exact function matching. Let's just bypass HTTP for staff if it's too complex,
        # OR test the domain logic directly. Actually, the user asked for an endpoint/domain test.
        import asyncio

        from domains.guest.messaging.guest_requests_router import reply_guest_request_thread
        class FakeBody:
            message = "Hello Guest"

        asyncio.run(reply_guest_request_thread(
            room_id="r1",
            body=FakeBody(),
            current_user=FakeUser()
        ))

        staff_args = mock_db["guest_room_messages"].insert_one.call_args[0][0]
        assert staff_args["property_id"] == "p1"
        assert staff_args["sender_type"] == "staff"

def test_staff_reply_missing_property_fail_closed(client, mock_db, mock_dependencies):
    import asyncio

    from domains.guest.messaging.guest_requests_router import reply_guest_request_thread

    class FakeUser:
        tenant_id = "t1"
        id = "u1"
        name = "Admin"

    class FakeBody:
        message = "Hello Guest"

    # Missing property in both room and last message
    async def mock_last_guest(*args, **kwargs):
        return {"booking_id": "b1", "room_number": "101", "property_id": None}
    mock_db["guest_room_messages"].find_one = AsyncMock(side_effect=mock_last_guest)

    async def mock_room_missing(*args, **kwargs):
        return {"id": "r1", "property_id": None}
    mock_db["rooms"].find_one = AsyncMock(side_effect=mock_room_missing)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(reply_guest_request_thread(
            room_id="r1",
            body=FakeBody(),
            current_user=FakeUser()
        ))

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Hizmet şu anda kullanılamıyor"
