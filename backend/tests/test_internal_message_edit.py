"""
Tests: Internal Message Edit Endpoint (PATCH /messaging/internal/{id})

Validates the edit flow that lets the original sender correct an internal
message within a 5-minute window:

- Only the original sender may edit their own message.
- Edits are rejected after the 5-minute window.
- Recalled (deleted) messages can no longer be edited.
- Each edit appends a snapshot of the previous text to `edit_history` so the
  original wording is never lost, and sets the `edited` / `edited_at` flags
  so both parties see the "düzenlendi" badge.
- Identical text submission is a no-op (no extra history entry).
"""
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

from fastapi import HTTPException

from models.enums import UserRole
from models.schemas import User


def _make_user(user_id: str = "user-sender-1") -> User:
    return User(
        id=user_id,
        tenant_id="tenant-abc",
        email="reception@example.com",
        username="reception1",
        name="Recep Reception",
        role=UserRole.FRONT_DESK,
    )


def _make_db_with_message(msg: dict) -> MagicMock:
    mock_db = MagicMock()
    mock_db.internal_messages = MagicMock()
    mock_db.internal_messages.find_one = AsyncMock(return_value=msg)
    mock_db.internal_messages.update_one = AsyncMock()
    # Audit-log writes (Task #40) target this collection — provide a stub
    # so log_audit_event can complete without hitting the real cluster.
    mock_db.audit_logs = MagicMock()
    mock_db.audit_logs.insert_one = AsyncMock()
    return mock_db


def _make_body(text: str):
    from domains.guest.messaging.router import _EditInternalMessageBody

    return _EditInternalMessageBody(message=text)


@pytest.mark.asyncio
async def test_edit_within_window_appends_history_and_marks_edited():
    """Successful edit within 5 min: writes new text, appends history, sets flags."""
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    msg = {
        "id": "msg-1",
        "tenant_id": user.tenant_id,
        "from_user_id": user.id,
        "to_user_id": "user-other",
        "to_department": None,
        "from_department": "Reception",
        "from_user_name": user.name,
        "to_user_name": "Other",
        "message": "Yanlış metin",
        "priority": "normal",
        "message_type": "text",
        "created_at": (datetime.now(UTC) - timedelta(seconds=30)).isoformat(),
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        result = await messaging_router.edit_internal_message(
            message_id="msg-1",
            body=_make_body("Doğru metin"),
            current_user=user,
        )

    assert result["success"] is True
    assert result["edited"] is True
    assert result["message"] == "Doğru metin"
    assert "edited_at" in result and result["edited_at"]

    mock_db.internal_messages.update_one.assert_awaited_once()
    call_args = mock_db.internal_messages.update_one.await_args
    update_doc = call_args[0][1]
    assert update_doc["$set"]["message"] == "Doğru metin"
    assert update_doc["$set"]["edited"] is True
    assert update_doc["$set"]["last_edited_by"] == user.id
    history_entry = update_doc["$push"]["edit_history"]
    # Snapshot of the *previous* text — the audit trail, not the new text.
    assert history_entry["message"] == "Yanlış metin"
    assert history_entry["edited_by"] == user.id
    assert history_entry["edited_by_name"] == user.name
    assert "edited_at" in history_entry


@pytest.mark.asyncio
async def test_edit_by_non_sender_returns_403():
    """A user who is not the original sender cannot edit the message."""
    from domains.guest.messaging import router as messaging_router

    sender = _make_user("user-sender-1")
    intruder = _make_user("user-intruder-9")
    msg = {
        "id": "msg-1",
        "tenant_id": sender.tenant_id,
        "from_user_id": sender.id,
        "message": "Orijinal",
        "created_at": datetime.now(UTC).isoformat(),
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await messaging_router.edit_internal_message(
                message_id="msg-1",
                body=_make_body("Hacked"),
                current_user=intruder,
            )
    assert exc.value.status_code == 403
    mock_db.internal_messages.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_after_window_returns_400():
    """Edits older than EDIT_WINDOW_SECONDS are rejected."""
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    too_old = datetime.now(UTC) - timedelta(
        seconds=messaging_router.EDIT_WINDOW_SECONDS + 60
    )
    msg = {
        "id": "msg-1",
        "tenant_id": user.tenant_id,
        "from_user_id": user.id,
        "message": "Çok eski",
        "created_at": too_old.isoformat(),
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await messaging_router.edit_internal_message(
                message_id="msg-1",
                body=_make_body("Yeni metin"),
                current_user=user,
            )
    assert exc.value.status_code == 400
    assert "dakikadan eski" in exc.value.detail
    mock_db.internal_messages.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_recalled_message_returns_400():
    """A recalled message cannot be edited — once tombstoned it's locked."""
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    msg = {
        "id": "msg-1",
        "tenant_id": user.tenant_id,
        "from_user_id": user.id,
        "message": "",
        "deleted": True,
        "deleted_at": datetime.now(UTC).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await messaging_router.edit_internal_message(
                message_id="msg-1",
                body=_make_body("Yeni"),
                current_user=user,
            )
    assert exc.value.status_code == 400
    assert "Geri alınmış" in exc.value.detail
    mock_db.internal_messages.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_with_identical_text_is_noop():
    """Submitting the same text doesn't bump edited_at or pollute history."""
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    msg = {
        "id": "msg-1",
        "tenant_id": user.tenant_id,
        "from_user_id": user.id,
        "message": "Aynı metin",
        "edited": False,
        "edited_at": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        result = await messaging_router.edit_internal_message(
            message_id="msg-1",
            body=_make_body("Aynı metin"),
            current_user=user,
        )

    assert result["success"] is True
    assert result["noop"] is True
    mock_db.internal_messages.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_missing_message_returns_404():
    """Unknown message_id (or wrong tenant) yields 404."""
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    mock_db = _make_db_with_message(None)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await messaging_router.edit_internal_message(
                message_id="msg-missing",
                body=_make_body("Yeni"),
                current_user=user,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_edit_blank_body_rejected_by_validation():
    """Pydantic body validator must reject empty / whitespace-only payloads."""
    from pydantic import ValidationError
    from domains.guest.messaging.router import _EditInternalMessageBody

    with pytest.raises(ValidationError):
        _EditInternalMessageBody(message="   ")
    with pytest.raises(ValidationError):
        _EditInternalMessageBody(message="")


# ---------------------------------------------------------------------------
# Task #40 — every successful edit appears in `audit_logs`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_writes_audit_log_entry():
    """A successful edit must write an `edit_internal_message` row to
    `audit_logs` capturing actor, target message, recipient and a snapshot
    of both the previous and the new text."""
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    msg = {
        "id": "msg-edit-audit-1",
        "tenant_id": user.tenant_id,
        "from_user_id": user.id,
        "from_user_name": user.name,
        "from_department": "Reception",
        "to_user_id": "user-other",
        "to_user_name": "Other Operator",
        "to_department": None,
        "message": "Eski metin",
        "priority": "normal",
        "message_type": "text",
        "created_at": (datetime.now(UTC) - timedelta(seconds=20)).isoformat(),
        "edit_history": [],
    }
    mock_db = _make_db_with_message(msg)

    # log_audit_event reads the global `db` from core.audit, but our router
    # calls it with `db=db` (the router's local module-level `db`). Patching
    # both keeps the test isolated regardless of which the implementation
    # uses.
    with patch.object(messaging_router, "db", mock_db):
        result = await messaging_router.edit_internal_message(
            message_id="msg-edit-audit-1",
            body=_make_body("Yeni metin"),
            current_user=user,
        )

    assert result["success"] is True
    assert result["edited"] is True
    mock_db.audit_logs.insert_one.assert_awaited_once()
    audit_entry = mock_db.audit_logs.insert_one.call_args[0][0]

    # Core audit-row contract.
    assert audit_entry["action"] == "edit_internal_message"
    assert audit_entry["entity_type"] == "internal_message"
    assert audit_entry["entity_id"] == "msg-edit-audit-1"
    assert audit_entry["tenant_id"] == user.tenant_id
    assert audit_entry["user_id"] == user.id

    before = audit_entry.get("before_value") or {}
    after = audit_entry.get("after_value") or {}
    # Snapshot of the *previous* text so an auditor can reconstruct what
    # the recipient originally saw.
    assert before["message_preview"] == "Eski metin"
    assert before["to_user_id"] == "user-other"
    assert before["from_user_id"] == user.id
    # New text + edited flag for the side-by-side diff in the report screen.
    assert after["message_preview_new"] == "Yeni metin"
    assert after["edited"] is True
    assert after["edited_by"] == user.id
    assert after["edit_count"] == 1


@pytest.mark.asyncio
async def test_edit_window_expired_does_not_write_audit_entry():
    """A rejected edit (out of window) must NOT pollute audit_logs — the
    edit didn't happen, so there is nothing to audit at edit-action level."""
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    too_old = datetime.now(UTC) - timedelta(
        seconds=messaging_router.EDIT_WINDOW_SECONDS + 60
    )
    msg = {
        "id": "msg-edit-audit-2",
        "tenant_id": user.tenant_id,
        "from_user_id": user.id,
        "message": "Çok eski",
        "created_at": too_old.isoformat(),
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException):
            await messaging_router.edit_internal_message(
                message_id="msg-edit-audit-2",
                body=_make_body("Yeni"),
                current_user=user,
            )

    mock_db.audit_logs.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# Task #39 — GET /messaging/internal/{id}/history endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_returns_chronological_versions_for_sender():
    """The history endpoint returns every previous version (oldest first)
    plus the current message text for the sender of the message."""
    from domains.guest.messaging import router as messaging_router

    sender = _make_user()
    msg = {
        "id": "msg-hist-1",
        "tenant_id": sender.tenant_id,
        "from_user_id": sender.id,
        "to_user_id": "user-other",
        "to_department": None,
        "message": "v3 (current)",
        "edited": True,
        "edited_at": "2026-04-27T12:00:30+00:00",
        "created_at": "2026-04-27T11:59:00+00:00",
        "edit_history": [
            {
                "message": "v1 (original)",
                "edited_at": "2026-04-27T11:59:30+00:00",
                "edited_by": sender.id,
                "edited_by_name": sender.name,
            },
            {
                "message": "v2",
                "edited_at": "2026-04-27T12:00:00+00:00",
                "edited_by": sender.id,
                "edited_by_name": sender.name,
            },
        ],
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        out = await messaging_router.get_internal_message_history(
            message_id="msg-hist-1", current_user=sender,
        )

    assert out["success"] is True
    assert out["current_message"] == "v3 (current)"
    assert out["edited"] is True
    history = out["history"]
    assert [h["message"] for h in history] == ["v1 (original)", "v2"]
    assert all(h["edited_by"] == sender.id for h in history)


@pytest.mark.asyncio
async def test_history_returns_empty_list_when_never_edited():
    """For a message that has never been edited, history is an empty list
    and edited=False — the endpoint must not 404 on a non-edited message."""
    from domains.guest.messaging import router as messaging_router

    sender = _make_user()
    msg = {
        "id": "msg-hist-2",
        "tenant_id": sender.tenant_id,
        "from_user_id": sender.id,
        "to_user_id": "user-other",
        "message": "Tek versiyon",
        "edited": False,
        "edited_at": None,
        "created_at": "2026-04-27T11:59:00+00:00",
        "edit_history": [],
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        out = await messaging_router.get_internal_message_history(
            message_id="msg-hist-2", current_user=sender,
        )

    assert out["success"] is True
    assert out["edited"] is False
    assert out["history"] == []
    assert out["current_message"] == "Tek versiyon"


@pytest.mark.asyncio
async def test_history_recipient_can_view():
    """The explicit recipient of a direct message must be able to view its
    history — the popover UI is rendered for them, not just the sender."""
    from domains.guest.messaging import router as messaging_router

    sender = _make_user("user-sender-1")
    recipient = _make_user("user-recipient-1")
    msg = {
        "id": "msg-hist-3",
        "tenant_id": sender.tenant_id,
        "from_user_id": sender.id,
        "to_user_id": recipient.id,
        "message": "current",
        "edited": True,
        "edited_at": "2026-04-27T12:00:30+00:00",
        "created_at": "2026-04-27T11:59:00+00:00",
        "edit_history": [
            {"message": "old", "edited_at": "2026-04-27T11:59:30+00:00",
             "edited_by": sender.id, "edited_by_name": sender.name},
        ],
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        out = await messaging_router.get_internal_message_history(
            message_id="msg-hist-3", current_user=recipient,
        )

    assert out["success"] is True
    assert len(out["history"]) == 1


@pytest.mark.asyncio
async def test_history_department_recipient_can_view():
    """A user whose role maps to the message's `to_department` must be
    able to view its history — department-targeted messages are visible
    to every member of that department, mirroring the inbox visibility.

    Regression for the prior implementation that read a non-existent
    `current_user.department` attribute and over-restricted access.
    """
    from domains.guest.messaging import router as messaging_router

    sender = _make_user("user-sender-1")
    # housekeeping role → 'Housekeeping' department per the role mapping.
    hk_member = User(
        id="user-hk-1",
        tenant_id=sender.tenant_id,
        email="hk@example.com",
        username="hk1",
        name="HK Member",
        role=UserRole.HOUSEKEEPING,
    )
    msg = {
        "id": "msg-hist-dept",
        "tenant_id": sender.tenant_id,
        "from_user_id": sender.id,
        "to_user_id": None,
        "to_department": "Housekeeping",
        "message": "department-wide note",
        "edited": True,
        "edited_at": "2026-04-27T12:00:30+00:00",
        "created_at": "2026-04-27T11:59:00+00:00",
        "edit_history": [
            {"message": "first version",
             "edited_at": "2026-04-27T11:59:30+00:00",
             "edited_by": sender.id,
             "edited_by_name": sender.name},
        ],
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        out = await messaging_router.get_internal_message_history(
            message_id="msg-hist-dept", current_user=hk_member,
        )

    assert out["success"] is True
    assert len(out["history"]) == 1
    assert out["history"][0]["message"] == "first version"


@pytest.mark.asyncio
async def test_history_wrong_department_member_is_403():
    """A user from a *different* department must not see a history meant
    for another department — pinning the negative side of the same rule."""
    from domains.guest.messaging import router as messaging_router

    sender = _make_user("user-sender-1")
    finance_member = User(
        id="user-fin-1",
        tenant_id=sender.tenant_id,
        email="fin@example.com",
        username="fin1",
        name="Finance Member",
        role=UserRole.FINANCE,
    )
    msg = {
        "id": "msg-hist-wrongdept",
        "tenant_id": sender.tenant_id,
        "from_user_id": sender.id,
        "to_user_id": None,
        "to_department": "Housekeeping",
        "message": "for housekeeping only",
        "edit_history": [],
        "created_at": "2026-04-27T11:59:00+00:00",
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await messaging_router.get_internal_message_history(
                message_id="msg-hist-wrongdept", current_user=finance_member,
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_history_unrelated_user_in_same_tenant_is_403():
    """A tenant member who is neither sender, explicit recipient, nor
    department recipient must NOT see the history — visibility mirrors the
    rest of the messaging router."""
    from domains.guest.messaging import router as messaging_router

    sender = _make_user("user-sender-1")
    nosy = _make_user("user-nosy-9")  # different department / not addressed
    msg = {
        "id": "msg-hist-4",
        "tenant_id": sender.tenant_id,
        "from_user_id": sender.id,
        "to_user_id": "user-other-recipient",
        "to_department": None,
        "message": "private",
        "edit_history": [],
        "created_at": "2026-04-27T11:59:00+00:00",
    }
    mock_db = _make_db_with_message(msg)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await messaging_router.get_internal_message_history(
                message_id="msg-hist-4", current_user=nosy,
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_history_missing_message_returns_404():
    from domains.guest.messaging import router as messaging_router

    user = _make_user()
    mock_db = _make_db_with_message(None)

    with patch.object(messaging_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await messaging_router.get_internal_message_history(
                message_id="msg-missing", current_user=user,
            )
    assert exc.value.status_code == 404
