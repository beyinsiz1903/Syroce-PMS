"""
Tests: Internal Message Recall Audit Trail

Validates that:
  1. Calling `recall_internal_message` writes a dedicated entry to the
     `audit_logs` collection (kim sildi, ne zaman, hangi mesaj, eski içerik
     özeti, alarm temizlendi mi) so admins can review who deleted what.
  2. The corresponding read endpoint (`GET /api/security/audit-logs`) is
     restricted to tenant admins — regular users get 403.
  3. Task #36: window-expired recall attempts (HTTP 400) ALSO produce an
     audit row (action=recall_internal_message_denied) so admins can spot
     users who repeatedly bump into the 5-minute limit.
"""
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastapi import HTTPException as _HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.enums import UserRole
from models.schemas import User


def _make_user(*, role: UserRole = UserRole.FRONT_DESK, user_id: str = "user-sender-1") -> User:
    return User(
        id=user_id,
        tenant_id="tenant-abc",
        email=f"{role.value}@example.com",
        username=f"{role.value}-1",
        name=f"Test {role.value}",
        role=role,
    )


def _make_existing_message(
    *,
    priority: str = "normal",
    deleted: bool = False,
    body: str = "Yanlışlıkla yazdığım mesaj.",
):
    return {
        "id": "msg-123",
        "tenant_id": "tenant-abc",
        "from_user_id": "user-sender-1",
        "from_user_name": "Test front_desk",
        "from_department": "Reception",
        "to_user_id": "user-target-9",
        "to_user_name": "Tek Hedef",
        "to_department": None,
        "message": body,
        "priority": priority,
        "message_type": "text",
        "created_at": datetime.now(UTC).isoformat(),
        "deleted": deleted,
    }


def _make_mock_db(existing_message):
    mock_db = MagicMock()
    mock_db.internal_messages = MagicMock()
    mock_db.internal_messages.find_one = AsyncMock(return_value=existing_message)
    mock_db.internal_messages.update_one = AsyncMock()
    mock_db.alerts = MagicMock()
    alarm_result = MagicMock()
    alarm_result.modified_count = 1
    mock_db.alerts.update_many = AsyncMock(return_value=alarm_result)
    mock_db.audit_logs = MagicMock()
    mock_db.audit_logs.insert_one = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# 1) Audit-write tests for recall_internal_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_writes_audit_log_entry():
    """A successful recall must produce an audit_logs entry capturing actor,
    target message, recipient, timestamp and a snapshot of the original body."""
    from domains.guest.messaging import router as messaging_router

    msg = _make_existing_message(body="Yanlışlıkla gönderdim, geri alıyorum.")
    mock_db = _make_mock_db(msg)
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await messaging_router.recall_internal_message(
            message_id="msg-123",
            current_user=user,
        )

    assert result["success"] is True
    assert result["message_id"] == "msg-123"

    mock_db.internal_messages.update_one.assert_awaited_once()
    mock_db.audit_logs.insert_one.assert_awaited_once()

    audit_entry = mock_db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["tenant_id"] == "tenant-abc"
    assert audit_entry["actor_id"] == user.id
    assert audit_entry["user_id"] == user.id
    assert audit_entry["action"] == "recall_internal_message"
    assert audit_entry["operation_name"] == "recall_internal_message"
    assert audit_entry["entity_type"] == "internal_message"
    assert audit_entry["target_type"] == "internal_message"
    assert audit_entry["entity_id"] == "msg-123"
    assert audit_entry["target_id"] == "msg-123"
    assert audit_entry["timestamp"]

    before = audit_entry["before_snapshot"]
    assert before["message_id"] == "msg-123"
    assert before["from_user_id"] == user.id
    assert before["to_user_id"] == "user-target-9"
    assert before["to_user_name"] == "Tek Hedef"
    assert before["priority"] == "normal"
    assert "Yanlışlıkla gönderdim" in before["message_preview"]
    assert before["message_length"] == len("Yanlışlıkla gönderdim, geri alıyorum.")

    after = audit_entry["after_snapshot"]
    assert after["deleted"] is True
    assert after["deleted_by"] == user.id
    assert after["deleted_by_name"] == user.name
    assert after["deleted_at"]
    assert after["alarm_cleared"] is False  # non-urgent → no alarm to clear


@pytest.mark.asyncio
async def test_recall_audit_records_alarm_cleared_for_urgent_message():
    """When recalling an urgent message, the audit entry must report that the
    associated alarm was dismissed."""
    from domains.guest.messaging import router as messaging_router

    msg = _make_existing_message(priority="urgent", body="Yangın!")
    mock_db = _make_mock_db(msg)
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await messaging_router.recall_internal_message(
            message_id="msg-123",
            current_user=user,
        )

    assert result["alarm_cleared"] is True
    mock_db.alerts.update_many.assert_awaited_once()
    mock_db.audit_logs.insert_one.assert_awaited_once()

    audit_entry = mock_db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["before_snapshot"]["priority"] == "urgent"
    assert audit_entry["after_snapshot"]["alarm_cleared"] is True


@pytest.mark.asyncio
async def test_recall_already_deleted_does_not_write_duplicate_audit():
    """An idempotent re-recall (message already soft-deleted) must NOT write
    an additional audit entry — only the original deletion is recorded."""
    from domains.guest.messaging import router as messaging_router

    msg = _make_existing_message(deleted=True)
    mock_db = _make_mock_db(msg)
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await messaging_router.recall_internal_message(
            message_id="msg-123",
            current_user=user,
        )

    assert result["already_deleted"] is True
    mock_db.internal_messages.update_one.assert_not_awaited()
    mock_db.audit_logs.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# 2) Admin-only readability of audit_logs via /api/security/audit-logs
# ---------------------------------------------------------------------------


def _build_audit_app(current_user: User) -> TestClient:
    """Mount the security/audit-logs route with the given user injected so we
    can assert the role guard from a HTTP-level perspective."""
    from domains.admin import router as admin_router
    from core.security import get_current_user

    app = FastAPI()
    # admin_router.router already declares prefix="/api" — do not double it.
    app.include_router(admin_router.router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


def test_security_audit_logs_rejects_non_admin_user():
    """A FRONT_DESK user must NOT be able to read tenant audit logs."""
    from domains.admin import router as admin_router

    user = _make_user(role=UserRole.FRONT_DESK)
    mock_db = MagicMock()
    mock_db.audit_logs = MagicMock()
    mock_db.audit_logs.find = MagicMock()  # should not be called

    with patch.object(admin_router, "db", mock_db):
        client = _build_audit_app(user)
        resp = client.get("/api/security/audit-logs")

    assert resp.status_code == 403, resp.text
    mock_db.audit_logs.find.assert_not_called()


# ---------------------------------------------------------------------------
# 3) Task #36 — denial audit when the 5-minute window has expired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_window_expired_writes_denial_audit_and_raises_400():
    """An attempt to recall a message older than the 5-min window must:
      - raise HTTPException(400) with the Turkish window-expired message;
      - still produce an audit_logs row with action=recall_internal_message_denied
        so a tenant admin can see who tried, when, and how late they were.
    """
    from domains.guest.messaging import router as messaging_router

    # Build a message whose created_at is well outside the 5-min window.
    old_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    msg = _make_existing_message()
    msg["created_at"] = old_ts

    mock_db = _make_mock_db(msg)
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        with pytest.raises(_HTTPException) as exc:
            await messaging_router.recall_internal_message(
                message_id="msg-123",
                current_user=user,
            )

    assert exc.value.status_code == 400
    assert "geri alınamaz" in str(exc.value.detail)

    # The original soft-delete must NOT have happened.
    mock_db.internal_messages.update_one.assert_not_awaited()

    # The denial audit row must exist.
    mock_db.audit_logs.insert_one.assert_awaited_once()
    audit_entry = mock_db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["action"] == "recall_internal_message_denied"
    assert audit_entry["operation_name"] == "recall_internal_message_denied"
    assert audit_entry["actor_id"] == user.id
    assert audit_entry["entity_id"] == "msg-123"

    before = audit_entry["before_snapshot"]
    assert before["message_id"] == "msg-123"
    assert before["from_user_id"] == user.id
    assert "message_preview" in before  # original wording preserved for context

    after = audit_entry["after_snapshot"]
    assert after["denial_reason"] == "recall_window_expired"
    assert after["elapsed_seconds"] >= 60  # well above zero
    assert after["window_seconds"] > 0


@pytest.mark.asyncio
async def test_recall_within_window_does_not_write_denial_audit():
    """Sanity: a message inside the window proceeds to the success path
    (action=recall_internal_message) — denial audit is NOT written."""
    from domains.guest.messaging import router as messaging_router

    fresh_ts = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    msg = _make_existing_message()
    msg["created_at"] = fresh_ts

    mock_db = _make_mock_db(msg)
    user = _make_user()

    with patch.object(messaging_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await messaging_router.recall_internal_message(
            message_id="msg-123",
            current_user=user,
        )

    assert result["success"] is True
    mock_db.audit_logs.insert_one.assert_awaited_once()
    audit_entry = mock_db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["action"] == "recall_internal_message"  # success, not denial


def test_security_audit_logs_allows_admin_user():
    """An ADMIN user must be able to read the tenant audit log."""
    from domains.admin import router as admin_router

    user = _make_user(role=UserRole.ADMIN, user_id="admin-1")

    fake_cursor = MagicMock()
    fake_cursor.sort.return_value = fake_cursor
    fake_cursor.limit.return_value = fake_cursor
    fake_cursor.to_list = AsyncMock(return_value=[
        {
            "id": "audit-1",
            "tenant_id": "tenant-abc",
            "action": "recall_internal_message",
            "user_id": "user-sender-1",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    ])

    mock_db = MagicMock()
    mock_db.audit_logs = MagicMock()
    mock_db.audit_logs.find = MagicMock(return_value=fake_cursor)

    with patch.object(admin_router, "db", mock_db):
        client = _build_audit_app(user)
        resp = client.get("/api/security/audit-logs")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["logs"][0]["action"] == "recall_internal_message"
