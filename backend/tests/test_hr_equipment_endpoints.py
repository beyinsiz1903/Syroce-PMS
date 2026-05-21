"""
Tests: HR equipment lifecycle endpoints (assign / list / return / delete).

Task #277 — guards the contract that Task #274's off-boarding soft-block
depends on: rows must be inserted with `status='assigned'` and tenant_id,
and the return endpoint must flip status away from 'assigned'. A regression
in either path would silently weaken the off-boarding block while #274's
own tests still pass.

Scenarios:
  assign:  inserts row with status='assigned', tenant_id, staff_id, and id;
           404 when staff is foreign-tenant.
  list:    returns only rows matching tenant_id + staff_id; cross-tenant
           rows never leak; status filter narrows further.
  return:  flips assigned → returned with returned_at timestamp; lost/damaged
           condition routes to matching status; 409 when already non-assigned;
           404 when row is in another tenant.
  delete:  deletes own-tenant row; 404 when row belongs to another tenant
           (no cross-tenant deletion).
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


def _make_staff(tenant_id: str = TENANT_A, staff_id: str = STAFF_ID):
    return {
        "id": staff_id,
        "tenant_id": tenant_id,
        "name": "Ali Personel",
        "department": "housekeeping",
        "hire_date": "2024-01-01",
        "monthly_hours": 225,
        "hourly_rate": 100,
    }


def _make_db(*, equipment_rows: list[dict], staff_by_tenant: dict[tuple, dict]):
    """Mock db whose staff_equipment supports find/find_one/insert_one/
    update_one/delete_one with real tenant_id + staff_id + id + status
    filtering, and whose staff_members.find_one is tenant-scoped."""

    rows = list(equipment_rows)  # mutable for insert/update/delete

    def _match(row, q):
        for k, v in q.items():
            if row.get(k) != v:
                return False
        return True

    def _find(q, _proj=None):
        matched = [dict(r) for r in rows if _match(r, q)]
        chain = MagicMock()
        chain.sort = MagicMock(return_value=chain)
        chain.to_list = AsyncMock(return_value=matched)
        return chain

    async def _find_one(q, _proj=None):
        for r in rows:
            if _match(r, q):
                return dict(r)
        return None

    async def _insert_one(doc):
        rows.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id"))

    async def _update_one(q, update):
        for r in rows:
            if _match(r, q):
                r.update(update.get("$set", {}))
                res = MagicMock()
                res.matched_count = 1
                res.modified_count = 1
                return res
        res = MagicMock()
        res.matched_count = 0
        res.modified_count = 0
        return res

    async def _delete_one(q):
        for i, r in enumerate(rows):
            if _match(r, q):
                rows.pop(i)
                res = MagicMock()
                res.deleted_count = 1
                return res
        res = MagicMock()
        res.deleted_count = 0
        return res

    mock_db = MagicMock()
    mock_db._equipment_rows = rows  # for assertions
    mock_db.staff_equipment = MagicMock()
    mock_db.staff_equipment.find = MagicMock(side_effect=_find)
    mock_db.staff_equipment.find_one = AsyncMock(side_effect=_find_one)
    mock_db.staff_equipment.insert_one = AsyncMock(side_effect=_insert_one)
    mock_db.staff_equipment.update_one = AsyncMock(side_effect=_update_one)
    mock_db.staff_equipment.delete_one = AsyncMock(side_effect=_delete_one)

    async def _sm_find_one(q, _proj=None):
        sid = q.get("id")
        tid = q.get("tenant_id")
        return staff_by_tenant.get((tid, sid))

    mock_db.staff_members = MagicMock()
    mock_db.staff_members.find_one = AsyncMock(side_effect=_sm_find_one)

    mock_db.users = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)

    return mock_db


# ---------------------------------------------------------------- assign ----

@pytest.mark.asyncio
async def test_assign_equipment_inserts_assigned_row_with_tenant_scope():
    from domains.hr import router as hr_router

    mock_db = _make_db(
        equipment_rows=[],
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff()},
    )

    payload = hr_router.EquipmentAssignPayload(
        item_type="laptop",
        item_label="Dell XPS 13",
        serial_no="SN-001",
        notes="ilk teslim",
    )

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.assign_equipment(
            staff_id=STAFF_ID,
            payload=payload,
            current_user=_make_admin(),
        )

    assert result["success"] is True
    eq = result["equipment"]
    assert eq["status"] == "assigned"
    assert eq["tenant_id"] == TENANT_A
    assert eq["staff_id"] == STAFF_ID
    assert eq["item_type"] == "laptop"
    assert eq["item_label"] == "Dell XPS 13"
    assert eq["returned_at"] is None
    assert eq["id"]  # uuid present
    assert eq["assigned_at"]  # default-fills today

    mock_db.staff_equipment.insert_one.assert_awaited_once()
    inserted = mock_db.staff_equipment.insert_one.call_args.args[0]
    assert inserted["tenant_id"] == TENANT_A
    assert inserted["staff_id"] == STAFF_ID
    assert inserted["status"] == "assigned"


@pytest.mark.asyncio
async def test_assign_equipment_404_when_staff_belongs_to_other_tenant():
    from domains.hr import router as hr_router

    # Staff exists only in TENANT_B; caller is TENANT_A admin.
    mock_db = _make_db(
        equipment_rows=[],
        staff_by_tenant={(TENANT_B, STAFF_ID): _make_staff(TENANT_B)},
    )

    payload = hr_router.EquipmentAssignPayload(
        item_type="key", item_label="Oda anahtarı",
    )

    with patch.object(hr_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await hr_router.assign_equipment(
                staff_id=STAFF_ID,
                payload=payload,
                current_user=_make_admin(TENANT_A),
            )

    assert exc.value.status_code == 404
    mock_db.staff_equipment.insert_one.assert_not_awaited()


# ------------------------------------------------------------------ list ----

@pytest.mark.asyncio
async def test_list_staff_equipment_returns_only_own_tenant_rows():
    from domains.hr import router as hr_router

    rows = [
        {"id": "eq-a1", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
         "item_type": "laptop", "item_label": "Dell", "status": "assigned",
         "assigned_at": "2025-01-01"},
        {"id": "eq-a2", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
         "item_type": "key", "item_label": "Anahtar", "status": "returned",
         "assigned_at": "2025-02-01", "returned_at": "2025-03-01"},
        # cross-tenant row with the same staff_id must not leak
        {"id": "eq-foreign", "tenant_id": TENANT_B, "staff_id": STAFF_ID,
         "item_type": "laptop", "item_label": "Foreign", "status": "assigned",
         "assigned_at": "2025-01-15"},
        # same tenant, different staff
        {"id": "eq-other", "tenant_id": TENANT_A, "staff_id": "staff-other",
         "item_type": "radio", "item_label": "Telsiz", "status": "assigned",
         "assigned_at": "2025-01-20"},
    ]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff()},
    )

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.list_staff_equipment(
            staff_id=STAFF_ID,
            status=None,
            current_user=_make_admin(),
        )

    ids = {it["id"] for it in result["items"]}
    assert ids == {"eq-a1", "eq-a2"}
    assert result["total"] == 2
    assert result["active"] == 1
    assert result["returned"] == 1
    assert result["lost_or_damaged"] == 0

    # And the find filter must have been tenant-scoped
    call_q = mock_db.staff_equipment.find.call_args.args[0]
    assert call_q["tenant_id"] == TENANT_A
    assert call_q["staff_id"] == STAFF_ID


@pytest.mark.asyncio
async def test_list_staff_equipment_status_filter_narrows_results():
    from domains.hr import router as hr_router

    rows = [
        {"id": "eq-1", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
         "item_type": "laptop", "item_label": "Dell", "status": "assigned",
         "assigned_at": "2025-01-01"},
        {"id": "eq-2", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
         "item_type": "key", "item_label": "Anahtar", "status": "returned",
         "assigned_at": "2025-02-01"},
    ]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff()},
    )

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.list_staff_equipment(
            staff_id=STAFF_ID,
            status="assigned",
            current_user=_make_admin(),
        )

    assert {it["id"] for it in result["items"]} == {"eq-1"}
    call_q = mock_db.staff_equipment.find.call_args.args[0]
    assert call_q["status"] == "assigned"


# ---------------------------------------------------------------- return ----

@pytest.mark.asyncio
async def test_return_equipment_flips_assigned_to_returned_with_timestamp():
    """Critical for Task #274: return endpoint MUST flip status away from
    'assigned' or the off-boarding soft-block silently weakens."""
    from domains.hr import router as hr_router

    rows = [{
        "id": "eq-1", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
        "item_type": "laptop", "item_label": "Dell", "status": "assigned",
        "assigned_at": "2025-01-01", "notes": "ilk teslim",
    }]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff()},
    )

    payload = hr_router.EquipmentReturnPayload(
        returned_at="2026-06-30",
        condition_on_return="good",
        notes="temiz iade",
    )

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.return_equipment(
            equipment_id="eq-1",
            payload=payload,
            current_user=_make_admin(),
        )

    assert result["success"] is True
    assert result["status"] == "returned"

    mock_db.staff_equipment.update_one.assert_awaited_once()
    q, update = mock_db.staff_equipment.update_one.call_args.args
    assert q == {"tenant_id": TENANT_A, "id": "eq-1"}
    set_doc = update["$set"]
    assert set_doc["status"] == "returned"
    assert set_doc["returned_at"] == "2026-06-30"
    assert set_doc["condition_on_return"] == "good"

    # And the in-memory row was actually mutated (full path: assigned → returned)
    assert mock_db._equipment_rows[0]["status"] == "returned"


@pytest.mark.asyncio
async def test_return_equipment_lost_condition_routes_to_lost_status():
    from domains.hr import router as hr_router

    rows = [{
        "id": "eq-1", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
        "item_type": "key", "item_label": "Anahtar", "status": "assigned",
        "assigned_at": "2025-01-01",
    }]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff()},
    )

    payload = hr_router.EquipmentReturnPayload(condition_on_return="lost")

    with patch.object(hr_router, "db", mock_db):
        result = await hr_router.return_equipment(
            equipment_id="eq-1",
            payload=payload,
            current_user=_make_admin(),
        )

    assert result["status"] == "lost"
    assert mock_db._equipment_rows[0]["status"] == "lost"


@pytest.mark.asyncio
async def test_return_equipment_409_when_already_returned():
    from domains.hr import router as hr_router

    rows = [{
        "id": "eq-1", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
        "item_type": "laptop", "item_label": "Dell", "status": "returned",
        "assigned_at": "2025-01-01", "returned_at": "2025-02-01",
    }]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff()},
    )

    payload = hr_router.EquipmentReturnPayload(condition_on_return="good")

    with patch.object(hr_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await hr_router.return_equipment(
                equipment_id="eq-1",
                payload=payload,
                current_user=_make_admin(),
            )

    assert exc.value.status_code == 409
    mock_db.staff_equipment.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_return_equipment_404_when_row_belongs_to_other_tenant():
    from domains.hr import router as hr_router

    rows = [{
        "id": "eq-1", "tenant_id": TENANT_B, "staff_id": STAFF_ID,
        "item_type": "laptop", "item_label": "Foreign", "status": "assigned",
        "assigned_at": "2025-01-01",
    }]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff(TENANT_A)},
    )

    payload = hr_router.EquipmentReturnPayload(condition_on_return="good")

    with patch.object(hr_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await hr_router.return_equipment(
                equipment_id="eq-1",
                payload=payload,
                current_user=_make_admin(TENANT_A),
            )

    assert exc.value.status_code == 404
    mock_db.staff_equipment.update_one.assert_not_awaited()
    # Foreign row untouched
    assert mock_db._equipment_rows[0]["status"] == "assigned"


# ---------------------------------------------------------------- delete ----

@pytest.mark.asyncio
async def test_delete_equipment_removes_own_tenant_row():
    from domains.hr import router as hr_router

    rows = [{
        "id": "eq-1", "tenant_id": TENANT_A, "staff_id": STAFF_ID,
        "item_type": "laptop", "item_label": "Dell", "status": "assigned",
        "assigned_at": "2025-01-01",
    }]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff()},
    )

    # `_audit` is best-effort and call-site-quirky across this 6.4k-line
    # router; stub it out so these tests assert route behavior, not the
    # audit transport.
    with patch.object(hr_router, "db", mock_db), \
         patch.object(hr_router, "_audit", new=AsyncMock()):
        result = await hr_router.delete_equipment(
            equipment_id="eq-1",
            current_user=_make_admin(),
        )

    assert result == {"success": True}
    mock_db.staff_equipment.delete_one.assert_awaited_once()
    q = mock_db.staff_equipment.delete_one.call_args.args[0]
    assert q == {"tenant_id": TENANT_A, "id": "eq-1"}
    assert mock_db._equipment_rows == []


@pytest.mark.asyncio
async def test_delete_equipment_404_when_row_belongs_to_other_tenant():
    from domains.hr import router as hr_router

    rows = [{
        "id": "eq-1", "tenant_id": TENANT_B, "staff_id": STAFF_ID,
        "item_type": "laptop", "item_label": "Foreign", "status": "assigned",
        "assigned_at": "2025-01-01",
    }]
    mock_db = _make_db(
        equipment_rows=rows,
        staff_by_tenant={(TENANT_A, STAFF_ID): _make_staff(TENANT_A)},
    )

    with patch.object(hr_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await hr_router.delete_equipment(
                equipment_id="eq-1",
                current_user=_make_admin(TENANT_A),
            )

    assert exc.value.status_code == 404
    # Foreign-tenant row MUST still exist
    assert len(mock_db._equipment_rows) == 1
    assert mock_db._equipment_rows[0]["tenant_id"] == TENANT_B
