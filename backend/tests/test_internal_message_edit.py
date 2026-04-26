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
