from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.enums import UserRole
from models.schemas import User

# Create a minimal FastAPI app and mount voice_router
app = FastAPI()
from domains.contact_center.voice_router import router as voice_router

app.include_router(voice_router)

# Mock user for testing overrides
mock_current_user = User(
    id="agent_uuid",
    tenant_id="t1",
    email="agent@syroce.com",
    name="Agent User",
    role=UserRole.CALL_CENTER_AGENT,
    granted_permissions=[]
)

# Apply dependency overrides to bypass actual DB/auth checks in unit tests
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_module, require_op

app.dependency_overrides[get_current_user] = lambda: mock_current_user
app.dependency_overrides[require_module("contact_center")] = lambda: None
app.dependency_overrides[require_op("manage_contact_center")] = lambda: None

client = TestClient(app, raise_server_exceptions=True)

@pytest.fixture(autouse=True)
def reset_user():
    global mock_current_user
    mock_current_user = User(
        id="agent_uuid",
        tenant_id="t1",
        email="agent@syroce.com",
        name="Agent User",
        role=UserRole.CALL_CENTER_AGENT,
        granted_permissions=[]
    )

@pytest.fixture
def mock_db(monkeypatch):
    mock_calls = MagicMock()
    mock_calls.find_one = AsyncMock()
    mock_calls.find = MagicMock()
    mock_calls.count_documents = AsyncMock(return_value=0)
    mock_calls.update_one = AsyncMock()

    mock_guests = MagicMock()
    mock_guests.find_one = AsyncMock()
    mock_guests.find = MagicMock()

    mock_bookings = MagicMock()
    mock_bookings.find = MagicMock()

    mock_requests = MagicMock()
    mock_requests.count_documents = AsyncMock(return_value=0)

    db_mock = MagicMock()
    collections = {
        "contact_center_calls": mock_calls,
        "guests": mock_guests,
        "bookings": mock_bookings,
        "guest_requests": mock_requests,
    }

    # Handle dict-like collection access
    db_mock.__getitem__.side_effect = lambda x: collections.get(x, MagicMock())

    # Handle attribute access
    db_mock.contact_center_calls = mock_calls
    db_mock.guests = mock_guests
    db_mock.bookings = mock_bookings
    db_mock.guest_requests = mock_requests

    import domains.contact_center.voice_router as vr
    monkeypatch.setattr(vr, "db", db_mock)
    return db_mock

@pytest.fixture
def mock_audit_log(monkeypatch):
    mock_log = AsyncMock()
    monkeypatch.setattr("shared_kernel.audit_helper.audit_log", mock_log)
    return mock_log

@pytest.fixture
def mock_comms_provider(monkeypatch):
    mock_provider = MagicMock()
    mock_provider.send_whatsapp = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(
        "domains.contact_center.provider.get_communication_provider",
        MagicMock(return_value=mock_provider)
    )
    return mock_provider

def test_transfer_live_call_not_found(mock_db):
    mock_db.contact_center_calls.find_one.return_value = None
    response = client.post(
        "/api/contact-center/voice/live/CA123/transfer",
        json={"target": "+905555555555"}
    )
    assert response.status_code == 404
    assert "Aktif çağrı bulunamadı" in response.json()["detail"]

def test_transfer_live_call_invalid_target(mock_db):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "provider_call_sid": "CA123",
        "tenant_id": "t1",
        "status": "answered"
    }
    response = client.post(
        "/api/contact-center/voice/live/CA123/transfer",
        json={"target": "invalid_format_123"}
    )
    assert response.status_code == 400
    assert "Geçersiz aktarım hedefi" in response.json()["detail"]

def test_send_whatsapp_call_not_found(mock_db):
    mock_db.contact_center_calls.find_one.return_value = None
    response = client.post(
        "/api/contact-center/voice/live/CA123/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 404
    assert "Çağrı bulunamadı" in response.json()["detail"]

def test_send_whatsapp_invalid_template(mock_db):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "provider_call_sid": "CA123",
        "tenant_id": "t1",
        "caller_id_enc": "encrypted_phone"
    }
    response = client.post(
        "/api/contact-center/voice/live/CA123/whatsapp",
        json={"template_name": "invalid_template"}
    )
    assert response.status_code == 400
    assert "Geçersiz şablon ismi" in response.json()["detail"]

def test_send_whatsapp_success(mock_db, mock_comms_provider, mock_audit_log):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "provider_call_sid": "CA123",
        "tenant_id": "t1",
        "caller_id_enc": "encrypted_phone"
    }

    # Mock decryption
    mock_svc = MagicMock()
    mock_svc.decrypt_value.return_value = "+905555555555"
    import domains.contact_center.voice_router as vr
    vr.get_field_encryption_service = MagicMock(return_value=mock_svc)

    response = client.post(
        "/api/contact-center/voice/live/CA123/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    mock_svc.decrypt_value.assert_called_with("encrypted_phone")
    mock_comms_provider.send_whatsapp.assert_called_once()
    assert mock_comms_provider.send_whatsapp.call_args[1]["recipient"] == "+905555555555"
    mock_audit_log.assert_called_once()

def test_recording_access_denied_for_non_owner_agent(mock_db):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "recording_ref": "some_ref",
        "agent_id": "another_agent_uuid"
    }

    global mock_current_user
    mock_current_user = User(
        id="agent_uuid",
        tenant_id="t1",
        email="agent@syroce.com",
        name="Agent User",
        role=UserRole.CALL_CENTER_AGENT,
        granted_permissions=[]
    )

    response = client.get("/api/contact-center/calls/c1/recording")
    assert response.status_code == 403
    assert "dinleme yetkiniz yok" in response.json()["detail"]

def test_recording_access_allowed_for_supervisor(mock_db, monkeypatch):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "recording_ref": "some_ref",
        "agent_id": "another_agent_uuid"
    }

    monkeypatch.setattr(
        "domains.contact_center.recording_storage.load_recording_bytes",
        lambda *args, **kwargs: b"fake_audio_stream"
    )

    global mock_current_user
    mock_current_user = User(
        id="supervisor_uuid",
        tenant_id="t1",
        email="sup@syroce.com",
        name="Supervisor User",
        role=UserRole.SUPERVISOR,
        granted_permissions=[]
    )

    response = client.get("/api/contact-center/calls/c1/recording")
    assert response.status_code == 200
    assert response.content == b"fake_audio_stream"


def test_transfer_live_call_other_tenant(mock_db):
    mock_db.contact_center_calls.find_one.return_value = None
    response = client.post(
        "/api/contact-center/voice/live/CA123/transfer",
        json={"target": "+905555555555"}
    )
    assert response.status_code == 404
    mock_db.contact_center_calls.find_one.assert_called()
    query = mock_db.contact_center_calls.find_one.call_args_list[0][0][0]
    assert query["tenant_id"] == "t1"


def test_send_whatsapp_other_tenant(mock_db):
    mock_db.contact_center_calls.find_one.return_value = None
    response = client.post(
        "/api/contact-center/voice/live/CA123/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 404
    mock_db.contact_center_calls.find_one.assert_called()
    query = mock_db.contact_center_calls.find_one.call_args_list[0][0][0]
    assert query["tenant_id"] == "t1"


def test_recording_access_other_tenant(mock_db):
    mock_db.contact_center_calls.find_one.return_value = None
    response = client.get("/api/contact-center/calls/c1/recording")
    assert response.status_code == 404


def test_guest_360_other_tenant(mock_db):
    mock_db.contact_center_calls.find_one.return_value = None
    response = client.get("/api/contact-center/calls/c1/guest-360")
    assert response.status_code == 404


def test_guest_360_no_match(mock_db, monkeypatch):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "tenant_id": "t1",
        "caller_id_enc": "enc_phone"
    }

    mock_guests_cursor = MagicMock()
    mock_guests_cursor.to_list = AsyncMock(return_value=[])
    mock_db.guests.find.return_value = mock_guests_cursor

    mock_svc = MagicMock()
    mock_svc.decrypt_value.return_value = "+905555555555"
    import domains.contact_center.voice_router as vr
    vr.get_field_encryption_service = MagicMock(return_value=mock_svc)

    monkeypatch.setattr(
        "security.encrypted_lookup.decrypt_guest_doc",
        lambda d: d
    )

    response = client.get("/api/contact-center/calls/c1/guest-360")
    assert response.status_code == 200
    assert response.json()["matched"] is False


def test_guest_360_one_match(mock_db, monkeypatch):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "tenant_id": "t1",
        "caller_id_enc": "enc_phone",
        "caller_id_hash": "hash_phone"
    }

    mock_guests_cursor = MagicMock()
    mock_guests_cursor.to_list = AsyncMock(return_value=[
        {"id": "g1", "name": "Jane Doe", "vip_level": "VIP 1", "phone": "+905555555555"}
    ])
    mock_db.guests.find.return_value = mock_guests_cursor

    mock_svc = MagicMock()
    mock_svc.decrypt_value.return_value = "+905555555555"
    import domains.contact_center.voice_router as vr
    vr.get_field_encryption_service = MagicMock(return_value=mock_svc)

    mock_bookings_cursor = MagicMock()
    mock_bookings_cursor.to_list = AsyncMock(return_value=[
        {"id": "b1", "status": "checked_in", "room_number": "101", "check_out": datetime(2026, 7, 10)}
    ])
    mock_db.bookings.find.return_value = mock_bookings_cursor

    mock_recent_cursor = MagicMock()
    mock_recent_cursor.sort.return_value = mock_recent_cursor
    mock_recent_cursor.limit.return_value = mock_recent_cursor
    mock_recent_cursor.to_list = AsyncMock(return_value=[])
    mock_db.contact_center_calls.find.return_value = mock_recent_cursor

    monkeypatch.setattr(
        "security.encrypted_lookup.decrypt_guest_doc",
        lambda d: d
    )

    response = client.get("/api/contact-center/calls/c1/guest-360")
    assert response.status_code == 200
    data = response.json()
    assert data["matched"] is True
    assert data["name"] == "Jane Doe"
    assert data["vip_level"] == "VIP 1"
    assert data["room_number"] == "101"


def test_guest_360_multiple_matches(mock_db, monkeypatch):
    mock_db.contact_center_calls.find_one.return_value = {
        "id": "c1",
        "tenant_id": "t1",
        "caller_id_enc": "enc_phone",
        "caller_id_hash": "hash_phone"
    }

    mock_guests_cursor = MagicMock()
    mock_guests_cursor.to_list = AsyncMock(return_value=[
        {"id": "g1", "name": "Jane Doe", "vip_level": "VIP 1"},
        {"id": "g2", "name": "John Doe", "vip_level": "VIP 2"}
    ])
    mock_db.guests.find.return_value = mock_guests_cursor

    mock_svc = MagicMock()
    mock_svc.decrypt_value.return_value = "+905555555555"
    import domains.contact_center.voice_router as vr
    vr.get_field_encryption_service = MagicMock(return_value=mock_svc)

    monkeypatch.setattr(
        "security.encrypted_lookup.decrypt_guest_doc",
        lambda d: d
    )

    response = client.get("/api/contact-center/calls/c1/guest-360")
    assert response.status_code == 200
    data = response.json()
    assert data["matched"] is True
    assert data["multiple"] is True
    assert len(data["possible_matches"]) == 2
    assert data["possible_matches"][0]["name"] == "Jane Doe"
    assert data["possible_matches"][0]["vip_level"] == "Masked (Multiple Matches)"


def test_analytics_parent_child_dedup(mock_db):
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "id": "call1_parent",
            "provider_call_sid": "CA_PARENT",
            "parent_call_sid": None,
            "tenant_id": "t1",
            "direction": "inbound",
            "status": "completed",
            "duration_seconds": 30,
            "started_at": datetime(2026, 7, 7, 10, 0, 0),
            "answered_at": datetime(2026, 7, 7, 10, 0, 5)
        },
        {
            "id": "call1_child",
            "provider_call_sid": "CA_CHILD",
            "parent_call_sid": "CA_PARENT",
            "tenant_id": "t1",
            "direction": "inbound",
            "status": "completed",
            "duration_seconds": 15,
            "started_at": datetime(2026, 7, 7, 10, 0, 10),
            "answered_at": datetime(2026, 7, 7, 10, 0, 15)
        }
    ])
    mock_db.contact_center_calls.find.return_value = mock_cursor

    mock_db.tenant_settings.find_one = AsyncMock(return_value={"timezone": "Europe/Istanbul"})

    response = client.get("/api/contact-center/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_calls"] == 1
    assert data["summary"]["answered_calls"] == 1


def test_send_whatsapp_provider_call_sid_match_succeeds(mock_db, mock_comms_provider, mock_audit_log):
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "id": "c1",
            "provider_call_sid": "CA123",
            "parent_call_sid": None,
            "tenant_id": "t1",
            "caller_id_enc": "encrypted_phone"
        }
    ])
    mock_db.contact_center_calls.find.return_value = mock_cursor

    mock_svc = MagicMock()
    mock_svc.decrypt_value.return_value = "+905555555555"
    import domains.contact_center.voice_router as vr
    vr.get_field_encryption_service = MagicMock(return_value=mock_svc)

    response = client.post(
        "/api/contact-center/voice/live/CA123/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_send_whatsapp_parent_call_sid_match_succeeds(mock_db, mock_comms_provider, mock_audit_log):
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "id": "c1",
            "provider_call_sid": "CA_CHILD",
            "parent_call_sid": "CA_PARENT",
            "tenant_id": "t1",
            "caller_id_enc": "encrypted_phone"
        }
    ])
    mock_db.contact_center_calls.find.return_value = mock_cursor

    mock_svc = MagicMock()
    mock_svc.decrypt_value.return_value = "+905555555555"
    import domains.contact_center.voice_router as vr
    vr.get_field_encryption_service = MagicMock(return_value=mock_svc)

    response = client.post(
        "/api/contact-center/voice/live/CA_PARENT/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_send_whatsapp_another_tenant_sid_returns_404(mock_db, mock_comms_provider):
    mock_db.contact_center_calls.find_one.return_value = None

    response = client.post(
        "/api/contact-center/voice/live/CA_PARENT/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 404


def test_send_whatsapp_prefer_leg_with_caller_id_enc(mock_db, mock_comms_provider, mock_audit_log):
    async def mock_find_one(query, *args, **kwargs):
        if "caller_id_enc" in query:
            return {
                "id": "c1_parent",
                "provider_call_sid": "CA_PARENT",
                "parent_call_sid": None,
                "tenant_id": "t1",
                "caller_id_enc": "encrypted_phone"
            }
        else:
            return {
                "id": "c1_child",
                "provider_call_sid": "CA_CHILD",
                "parent_call_sid": "CA_PARENT",
                "tenant_id": "t1",
                "caller_id_enc": None
            }

    mock_db.contact_center_calls.find_one.side_effect = mock_find_one

    mock_svc = MagicMock()
    mock_svc.decrypt_value.return_value = "+905555555555"
    import domains.contact_center.voice_router as vr
    vr.get_field_encryption_service = MagicMock(return_value=mock_svc)

    response = client.post(
        "/api/contact-center/voice/live/CA_PARENT/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 200
    mock_svc.decrypt_value.assert_called_with("encrypted_phone")


def test_send_whatsapp_no_call_record_returns_404(mock_db):
    mock_db.contact_center_calls.find_one.return_value = None

    response = client.post(
        "/api/contact-center/voice/live/CA_NONE/whatsapp",
        json={"template_name": "hello_world"}
    )
    assert response.status_code == 404
