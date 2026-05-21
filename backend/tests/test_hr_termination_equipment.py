"""
Tests: Off-boarding equipment soft-block on POST /hr/staff/{id}/terminate.

Covers Task #270's safety net (asset-loss protection) so a future refactor of
the 6.4k-line HR router cannot silently re-allow termination while equipment
is still assigned to the staff member.

Scenarios:
  a. Outstanding equipment → 409 with detail.code == 'outstanding_equipment'
     and the assigned items echoed back.
  b. force_release=true → termination proceeds and equipment rows are NOT
     mutated (returns are explicit operations, not implicit side-effects).
  c. No equipment assigned → termination succeeds as normal.
  d. Tenant scoping → equipment owned by another tenant for a staff id with
     the same value does not block termination.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.enums import UserRole
from models.schemas import User


TENANT_A = "tenant-aaa"
TENANT_B = "tenant-bbb"
STAFF_ID = "staff-1"


def _make_admin(tenant_id: str = TENANT_A) -> User:
    return User(
        id="user-admin-1",
        tenant_id=tenant_id,
        email="admin@hotel.com",
        username="admin1",
        name="Admin One",
        role=UserRole.ADMIN,
    )


def _payload():
    from domains.hr.router import TerminationPayload

    return TerminationPayload(
        reason="resign",
        last_day="2026-06-30",
        notice_period_days=14,
        exit_interview_notes="Test exit",
        eligible_for_rehire=True,
    )


def _make_staff(tenant_id: str = TENANT_A):
    return {
        "id": STAFF_ID,
        "tenant_id": tenant_id,
        "name": "Ali Personel",
        "department": "housekeeping",
        "hire_date": "2024-01-01",
        "monthly_hours": 225,
        "hourly_rate": 100,
    }


def _make_db(*, equipment_rows: list[dict], staff: dict):
    """Build an AsyncMock db whose `staff_equipment.find(filter, proj)` returns
    rows matching the filter's tenant_id / staff_id / status keys.

    The router calls `db.staff_equipment.find(q).sort(...).to_list(N)` so we
    return a chain object with `.sort()` returning self and `.to_list()` an
    awaitable. Filtering is applied at find() time so tenant-scoping is
    actually exercised."""

    def _find(q, _proj=None):
        rows = [
            r for r in equipment_rows
            if r.get("tenant_id") == q.get("tenant_id")
            and r.get("staff_id") == q.get("staff_id")
            and (q.get("status") is None or r.get("status") == q["status"])
        ]
        chain = MagicMock()
        chain.sort = MagicMock(return_value=chain)
        chain.to_list = AsyncMock(return_value=rows)
        return chain

    mock_db = MagicMock()
    mock_db.staff_equipment = MagicMock()
    mock_db.staff_equipment.find = MagicMock(side_effect=_find)
    mock_db.staff_equipment.update_one = AsyncMock()
    mock_db.staff_equipment.delete_one = AsyncMock()

    mock_db.staff_members = MagicMock()
    mock_db.staff_members.find_one = AsyncMock(return_value=staff)
    mock_db.staff_members.update_one = AsyncMock()

    mock_db.users = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)

    mock_db.tenant_settings = MagicMock()
    mock_db.tenant_settings.find_one = AsyncMock(return_value=None)

    mock_db.staff_terminations = MagicMock()
    mock_db.staff_terminations.insert_one = AsyncMock()

    return mock_db


@pytest.mark.asyncio
async def test_terminate_blocked_when_outstanding_equipment():
    """Scenario (a): assigned equipment → 409 outstanding_equipment with list."""
    from domains.hr import router as hr_router

    assigned = [
        {"id": "eq-1", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
         "item": "Laptop Dell XPS", "status": "assigned",
         "assigned_at": "2025-01-01T00:00:00+00:00"},
        {"id": "eq-2", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
         "item": "Telsiz", "status": "assigned",
         "assigned_at": "2025-02-01T00:00:00+00:00"},
    ]
    mock_db = _make_db(equipment_rows=assigned, staff=_make_staff())
    user = _make_admin()

    with patch.object(hr_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc_info:
            await hr_router.terminate_staff(
                staff_id=STAFF_ID,
                payload=_payload(),
                force_release=False,
                current_user=user,
            )

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "outstanding_equipment"
    assert len(detail["outstanding_equipment"]) == 2
    items = {row["id"] for row in detail["outstanding_equipment"]}
    assert items == {"eq-1", "eq-2"}

    # Critical: termination side-effects MUST NOT have fired.
    mock_db.staff_terminations.insert_one.assert_not_awaited()
    mock_db.staff_members.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminate_force_release_proceeds_and_leaves_equipment_untouched():
    """Scenario (b): force_release=true → terminate; equipment rows NOT mutated."""
    from domains.hr import router as hr_router

    assigned = [
        {"id": "eq-9", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
         "item": "Anahtarlık", "status": "assigned",
         "assigned_at": "2025-03-01T00:00:00+00:00"},
    ]
    mock_db = _make_db(equipment_rows=assigned, staff=_make_staff())
    user = _make_admin()

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.terminate_staff(
            staff_id=STAFF_ID,
            payload=_payload(),
            force_release=True,
            current_user=user,
        )

    assert result["success"] is True
    assert "termination" in result
    mock_db.staff_terminations.insert_one.assert_awaited_once()
    mock_db.staff_members.update_one.assert_awaited_once()
    # Equipment rows are intentionally untouched — returns must be explicit.
    mock_db.staff_equipment.update_one.assert_not_awaited()
    mock_db.staff_equipment.delete_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminate_succeeds_when_no_equipment_assigned():
    """Scenario (c): zero outstanding rows → normal termination."""
    from domains.hr import router as hr_router

    mock_db = _make_db(equipment_rows=[], staff=_make_staff())
    user = _make_admin()

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.terminate_staff(
            staff_id=STAFF_ID,
            payload=_payload(),
            force_release=False,
            current_user=user,
        )

    assert result["success"] is True
    assert result["termination"]["staff_id"] == STAFF_ID
    assert result["termination"]["reason"] == "resign"
    mock_db.staff_terminations.insert_one.assert_awaited_once()
    mock_db.staff_members.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_ignores_other_tenants_equipment():
    """Scenario (d): equipment with same staff_id but a foreign tenant_id
    must NOT block termination — proves tenant scoping on the soft-block."""
    from domains.hr import router as hr_router

    foreign_only = [
        {"id": "eq-foreign", "tenant_id": TENANT_B, "staff_id": STAFF_ID,
         "item": "Foreign Laptop", "status": "assigned",
         "assigned_at": "2025-04-01T00:00:00+00:00"},
    ]
    mock_db = _make_db(equipment_rows=foreign_only, staff=_make_staff(TENANT_A))
    user = _make_admin(TENANT_A)

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.terminate_staff(
            staff_id=STAFF_ID,
            payload=_payload(),
            force_release=False,
            current_user=user,
        )

    assert result["success"] is True
    mock_db.staff_terminations.insert_one.assert_awaited_once()
    # Verify the find filter actually used the caller's tenant_id (not TENANT_B).
    call_args = mock_db.staff_equipment.find.call_args
    assert call_args.args[0]["tenant_id"] == TENANT_A
    assert call_args.args[0]["staff_id"] == STAFF_ID
    assert call_args.args[0]["status"] == "assigned"
