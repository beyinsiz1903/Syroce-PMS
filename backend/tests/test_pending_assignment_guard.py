"""
Test: Pending-Assignment Defensive Guard (v106 Bug DAE follow-up)
==================================================================
Regression tests for `core.atomic_booking.assert_pending_assignment()`.

Background:
  After v106 Bug DAE, 4 user-facing booking routes were migrated from direct
  `db.bookings.insert_one()` to `create_booking_atomic()`. Three OTA fallback
  paths (celery_tasks, reservation_import_service, exely/auto_import) still
  use the direct insert when atomic raises `BookingConflictError`, but only
  with `room_id=None` + `allocation_source="pending_assignment"`.

  These tests guarantee that the shared `assert_pending_assignment()` guard
  raises `RuntimeError` if any caller forgets to reset `room_id` to None,
  which would re-introduce the atomic-guard bypass that caused Bug DAE.

  Uses explicit `raise RuntimeError` (not `assert`) so the check survives
  Python `-O` (optimized) runs.
"""
import pytest

from core.atomic_booking import assert_pending_assignment


def test_passes_when_room_id_is_none():
    booking = {"booking_id": "b1", "room_id": None, "allocation_source": "pending_assignment"}
    assert_pending_assignment(booking) is None


def test_passes_when_room_id_key_missing():
    booking = {"booking_id": "b1", "allocation_source": "pending_assignment"}
    assert_pending_assignment(booking) is None


def test_raises_when_room_id_is_truthy_string():
    booking = {"booking_id": "b1", "room_id": "room-101", "allocation_source": "pending_assignment"}
    with pytest.raises(RuntimeError, match="pending_assignment fallback must have room_id=None"):
        assert_pending_assignment(booking)


def test_raises_when_room_id_is_zero_int():
    booking = {"booking_id": "b1", "room_id": 0}
    with pytest.raises(RuntimeError, match="pending_assignment fallback must have room_id=None"):
        assert_pending_assignment(booking)


def test_raises_when_room_id_is_empty_string():
    booking = {"booking_id": "b1", "room_id": ""}
    with pytest.raises(RuntimeError, match="pending_assignment fallback must have room_id=None"):
        assert_pending_assignment(booking)


def test_callers_use_shared_helper():
    """Lock-in: each known fallback path source-file must reference the shared guard.

    Reads files directly (no module import) so the assertion holds even in
    environments where heavy deps like `celery` aren't installed.
    """
    from pathlib import Path

    backend_root = Path(__file__).resolve().parent.parent
    targets = {
        "celery_tasks.py": backend_root / "celery_tasks.py",
        "reservation_import_service.py": backend_root / "channel_manager" / "application" / "reservation_import_service.py",
        "exely/auto_import.py": backend_root / "domains" / "channel_manager" / "providers" / "exely" / "auto_import.py",
    }
    for name, path in targets.items():
        assert path.exists(), f"Expected fallback source missing: {path}"
        src = path.read_text(encoding="utf-8")
        assert "assert_pending_assignment" in src, (
            f"{name} fallback must call assert_pending_assignment() to prevent Bug DAE regression"
        )
