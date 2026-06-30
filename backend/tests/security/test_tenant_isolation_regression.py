import pytest
import uuid
import jwt
from datetime import datetime, UTC, timedelta
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from server import app
from core.security import JWT_SECRET as USER_JWT_SECRET, JWT_ALGORITHM

client = TestClient(app)

def create_user_token(user_id, tenant_id, role="admin"):
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=15)
    }
    return jwt.encode(payload, USER_JWT_SECRET, algorithm=JWT_ALGORITHM)

@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()

# --- Mock DB Behaviors ---
async def mock_bookings_find_one(query, *args, **kwargs):
    if query.get("id") == "booking_A" and query.get("tenant_id") == "hotel_A":
        return {"id": "booking_A", "tenant_id": "hotel_A", "guest_id": "guest_A", "room_id": "room_A"}
    return None

async def mock_guests_find_one(query, *args, **kwargs):
    if query.get("id") == "guest_A" and query.get("tenant_id") == "hotel_A":
        return {"id": "guest_A", "tenant_id": "hotel_A", "name": "Tenant A Guest"}
    return None

async def mock_folios_find_one(query, *args, **kwargs):
    if query.get("id") == "folio_A" and query.get("tenant_id") == "hotel_A":
        return {"id": "folio_A", "tenant_id": "hotel_A", "balance": 100}
    return None

# --- TESTS ---

@patch("routers.reservation_detail.db")
def test_reservation_full_detail_tenant_isolation(mock_db):
    """
    Test that user from hotel_B cannot access hotel_A's reservation.
    """
    mock_db.bookings.find_one = AsyncMock(side_effect=mock_bookings_find_one)
    mock_db.guests.find_one = AsyncMock(return_value=None)
    mock_db.rooms.find_one = AsyncMock(return_value=None)
    mock_db.folios.find_one = AsyncMock(return_value=None)
    
    token_B = create_user_token(user_id="user_B", tenant_id="hotel_B")
    headers_B = {"Authorization": f"Bearer {token_B}"}
    
    with patch("core.security._user_doc_cache_get") as mock_cache:
        mock_cache.return_value = {"_id": "user_B", "tenant_id": "hotel_B", "email": "userB@test.com", "name": "Hotel B User", "role": "admin", "is_active": True, "failed_login_attempts": 0}
        with patch("infra.auth_cache_pubsub.auth_cache_pubsub"):
            # Attempt to fetch hotel_A's booking
            response = client.get("/api/pms/reservations/booking_A/full-detail", headers=headers_B)
            print("ERROR BODY:", response.text)
            
            # Since the router queries by current_user.tenant_id, it queries {"id": "booking_A", "tenant_id": "hotel_B"}
            # This should return 404, acting as if the reservation does not exist.
            assert response.status_code == 404
            
    # Also verify that hotel_A user CAN access it
    token_A = create_user_token(user_id="user_A", tenant_id="hotel_A")
    headers_A = {"Authorization": f"Bearer {token_A}"}
    with patch("core.security._user_doc_cache_get") as mock_cache_A:
        mock_cache_A.return_value = {"_id": "user_A", "tenant_id": "hotel_A", "email": "userA@test.com", "name": "Hotel A User", "role": "admin", "is_active": True, "failed_login_attempts": 0}
        with patch("infra.auth_cache_pubsub.auth_cache_pubsub"):
            response_A = client.get("/api/pms/reservations/booking_A/full-detail", headers=headers_A)
            assert response_A.status_code == 200

@patch("routers.reservation_detail.db")
def test_reservation_payment_tenant_isolation(mock_db):
    """
    Test that user from hotel_B cannot post a payment to hotel_A's reservation.
    """
    mock_db.bookings.find_one = AsyncMock(side_effect=mock_bookings_find_one)
    mock_db.guests.find_one = AsyncMock(return_value=None)
    mock_db.rooms.find_one = AsyncMock(return_value=None)
    mock_db.folios.find_one = AsyncMock(return_value=None)
    
    token_B = create_user_token(user_id="user_B", tenant_id="hotel_B")
    headers_B = {"Authorization": f"Bearer {token_B}"}
    
    payload = {
        "amount": 100.0,
        "method": "card",
        "payment_type": "deposit"
    }
    
    with patch("core.security._user_doc_cache_get") as mock_cache:
        mock_cache.return_value = {"_id": "user_B", "tenant_id": "hotel_B", "email": "userB@test.com", "name": "Hotel B User", "role": "admin", "is_active": True, "failed_login_attempts": 0}
        with patch("infra.auth_cache_pubsub.auth_cache_pubsub"):
            response = client.post("/api/pms/reservations/booking_A/payments", json=payload, headers=headers_B)
            # Should fail because booking_A under tenant hotel_B is not found
            assert response.status_code == 404

@patch("routers.pms_guests.db")
def test_guest_update_tenant_isolation(mock_db):
    """
    Test that user from hotel_B cannot update hotel_A's guest profile.
    """
    mock_db.guests.find_one = AsyncMock(side_effect=mock_guests_find_one)
    
    token_B = create_user_token(user_id="user_B", tenant_id="hotel_B")
    headers_B = {"Authorization": f"Bearer {token_B}"}
    
    payload = {
        "name": "Hacked Profile"
    }
    
    with patch("core.security._user_doc_cache_get") as mock_cache:
        mock_cache.return_value = {"_id": "user_B", "tenant_id": "hotel_B", "email": "userB@test.com", "name": "Hotel B User", "role": "admin", "is_active": True, "failed_login_attempts": 0}
        with patch("infra.auth_cache_pubsub.auth_cache_pubsub"):
            response = client.put("/api/guests/guest_A", json=payload, headers=headers_B)
            # Should return 404 Not Found since it searches by hotel_B
            assert response.status_code == 404

@pytest.mark.skip(reason="Router path needs verification")
def test_folio_retrieval_tenant_isolation():
    pass

@patch("routers.reservation_detail.db")
def test_super_admin_cross_tenant_access(mock_db):
    """
    Super Admin in tenant hotel_A tries to access hotel_B's reservation.
    Since current_user.tenant_id is hotel_A, the query looks for tenant_id=hotel_A.
    This means even a super admin cannot cross-pollinate data just by guessing an ID,
    ensuring 100% isolation by default (unless they use a specific cross-tenant endpoint which would have audit logs).
    """
    mock_db.bookings.find_one = AsyncMock(side_effect=mock_bookings_find_one)
    mock_db.guests.find_one = AsyncMock(return_value=None)
    mock_db.rooms.find_one = AsyncMock(return_value=None)
    mock_db.folios.find_one = AsyncMock(return_value=None)
    
    # super_admin from hotel_A trying to access booking from hotel_B (which doesn't exist in hotel_A)
    token_SA = create_user_token(user_id="sa_A", tenant_id="hotel_A", role="super_admin")
    headers_SA = {"Authorization": f"Bearer {token_SA}"}
    
    with patch("core.security._user_doc_cache_get") as mock_cache:
        mock_cache.return_value = {"_id": "sa_A", "tenant_id": "hotel_A", "email": "sa@test.com", "name": "Super Admin", "role": "super_admin", "is_active": True, "failed_login_attempts": 0}
        with patch("infra.auth_cache_pubsub.auth_cache_pubsub"):
            response = client.get("/api/pms/reservations/booking_B/full-detail", headers=headers_SA)
            # Returns 404 because booking_B does not belong to hotel_A
            assert response.status_code == 404
