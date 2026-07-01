"""
Tests: Urgent Internal Message Audit Trail

Validates that every urgent-priority internal message produces a dedicated
entry in the `audit_logs` collection (kim, kime, ne zaman, mesaj kimliği)
so managers can later review possible abuse / unnecessary alarms.

Non-urgent messages must NOT create an audit entry — the audit log is
specifically scoped to the urgent-priority flow.
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

from models.enums import UserRole
from models.schemas import User


def _make_user() -> User:
    # Task #18: urgent priority artık ayrı bir izinle (`send_urgent_message`)
    # korunuyor — sadece SUPERVISOR/ADMIN/SUPER_ADMIN bu kanalı kullanabilir.
    # Audit testlerinin spec'i "urgent gönderildiğinde audit yazılır" üzerine
    # kurulu, dolayısıyla fixture user'ı urgent gönderebilen bir role
    # (SUPERVISOR -> "Management" departmanı) yükseltildi.
    return User(
        id="user-sender-1",
        tenant_id="tenant-abc",
        email="supervisor@example.com",
        username="sup1",
        name="Sup Ervisor",
        role=UserRole.SUPERVISOR,
    )


def _make_mock_db() -> MagicMock:
    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)
    mock_db.internal_messages = MagicMock()
    mock_db.internal_messages.insert_one = AsyncMock()
    mock_db.alerts = MagicMock()
    mock_db.alerts.insert_one = AsyncMock()
    mock_db.audit_logs = MagicMock()
    mock_db.audit_logs.insert_one = AsyncMock()
    return mock_db


@pytest.mark.asyncio
async def test_urgent_message_creates_audit_log_entry():
    """Urgent priority must write a single audit_logs entry with sender,
    recipient, timestamp and message_id."""
    from domains.guest.messaging import router as messaging_router

    mock_db = _make_mock_db()
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await messaging_router.send_internal_message(
            message="Yangın alarmı! Hemen kontrol edin.",
            to_department="Housekeeping",
            to_user_id=None,
            priority="urgent",
            message_type="alert",
            current_user=user,
            _perm=True,
        )

    assert result["success"] is True
    message_id = result["message_id"]

    # Alert + audit must each have been called exactly once.
    mock_db.alerts.insert_one.assert_awaited_once()
    mock_db.audit_logs.insert_one.assert_awaited_once()

    audit_entry = mock_db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["tenant_id"] == "tenant-abc"
    assert audit_entry["actor_id"] == user.id
    assert audit_entry["user_id"] == user.id
    assert audit_entry["action"] == "send_urgent_internal_message"
    assert audit_entry["operation_name"] == "send_urgent_internal_message"
    assert audit_entry["entity_type"] == "internal_message"
    assert audit_entry["target_type"] == "internal_message"
    assert audit_entry["entity_id"] == message_id
    assert audit_entry["target_id"] == message_id
    # Task #27: acil mesaj kayıtları yüksek öncelikli işaretlenir.
    assert audit_entry["severity"] == "warning"
    assert "timestamp" in audit_entry and audit_entry["timestamp"]

    after = audit_entry["after_snapshot"]
    assert after["message_id"] == message_id
    assert after["from_user_id"] == user.id
    assert after["from_user_name"] == user.name
    assert after["from_department"] == "Management"
    assert after["to_department"] == "Housekeeping"
    assert after["priority"] == "urgent"
    assert "Yangın alarmı" in after["message_preview"]


@pytest.mark.asyncio
async def test_log_audit_event_default_severity_unchanged():
    """Geriye dönük uyum: severity argümanı verilmezse varsayılan
    "info" olmalı; mevcut çağıranlar etkilenmemeli."""
    from core import audit as audit_module

    mock_db = MagicMock()
    mock_db.audit_logs = MagicMock()
    mock_db.audit_logs.insert_one = AsyncMock()

    await audit_module.log_audit_event(
        tenant_id="t1",
        user_id="u1",
        action="some.action",
        entity_type="thing",
        entity_id="e1",
        details="ne olduğu önemli değil",
        db=mock_db,
    )

    entry = mock_db.audit_logs.insert_one.call_args[0][0]
    assert entry["severity"] == "info"


@pytest.mark.asyncio
async def test_normal_priority_message_does_not_create_audit_log():
    """Non-urgent messages must NOT create alert or audit entries."""
    from domains.guest.messaging import router as messaging_router

    mock_db = _make_mock_db()
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await messaging_router.send_internal_message(
            message="Sıradan bir not.",
            to_department="Maintenance",
            to_user_id=None,
            priority="normal",
            message_type="text",
            current_user=user,
            _perm=True,
        )

    assert result["success"] is True
    mock_db.internal_messages.insert_one.assert_awaited_once()
    mock_db.alerts.insert_one.assert_not_awaited()
    mock_db.audit_logs.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_urgent_message_to_specific_user_records_recipient():
    """When sent to a specific user the audit entry must capture
    recipient user id + name."""
    from domains.guest.messaging import router as messaging_router

    mock_db = _make_mock_db()
    mock_db.users.find_one = AsyncMock(return_value={
        "id": "user-target-9",
        "name": "Tek Hedef",
        "tenant_id": "tenant-abc",
    })
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await messaging_router.send_internal_message(
            message="Acil destek lazım.",
            to_department=None,
            to_user_id="user-target-9",
            priority="urgent",
            message_type="alert",
            current_user=user,
            _perm=True,
        )

    assert result["success"] is True
    mock_db.audit_logs.insert_one.assert_awaited_once()

    after = mock_db.audit_logs.insert_one.call_args[0][0]["after_snapshot"]
    assert after["to_user_id"] == "user-target-9"
    assert after["to_user_name"] == "Tek Hedef"
    assert after["to_department"] is None
