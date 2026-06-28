"""Targeted tests for the human-Concierge task tracking module.

Pinned contract (Kademe 1):
  * Creating a task with an assignee starts in 'assigned', else 'open'.
  * Status transitions follow the defensive guard; invalid transitions -> 409.
  * Assignment never reopens a terminal task (completed/cancelled -> 409).
  * Mutations are RBAC-gated to staff roles; delete is admin-tier.
  * All queries are tenant-scoped (no cross-tenant read/mutation).

Mirrors tests/test_laundry_orders.py's in-memory fake-DB approach so they run
without a live Mongo.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms import concierge_router as cr


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        out = [{kk: vv for kk, vv in d.items() if kk != "_id"} for d in self._docs]
        return out[:n] if n else out


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []
        self.insert_calls = 0

    def find(self, flt=None, proj=None):
        flt = flt or {}
        return _Cursor([d for d in self.docs if _match(d, flt)])

    async def find_one(self, flt, proj=None, sort=None):
        matches = [d for d in self.docs if _match(d, flt)]
        if not matches:
            return None
        return {kk: vv for kk, vv in matches[0].items() if kk != "_id"}

    async def insert_one(self, doc):
        self.insert_calls += 1
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.concierge_tasks = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


TENANT = "tenant-A"


def _user(role="concierge", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role,
        is_super_admin=super_admin, name="Staff", email="s@example.com",
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(cr, "db", fake)
    return fake


async def _create(fake, user, **kw):
    payload = cr.TaskIn(**kw)
    return (await cr.create_task(payload=payload, current_user=user))["task"]


async def _patch_status(task_id, status, user, note=None):
    return await cr.update_task_status(
        task_id=task_id,
        payload=cr.StatusUpdate(status=status, resolution_note=note),
        current_user=user,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_create_unassigned_is_open(_patch):
    task = await _create(_patch, _user(), task_type="luggage", title="Bagaj indir")
    assert task["status"] == "open"
    assert task["assigned_to"] is None
    assert task["task_type"] == "luggage"
    assert task["tenant_id"] == TENANT


async def test_create_with_assignee_is_assigned(_patch):
    task = await _create(
        _patch, _user(), title="Çiçek gönder", task_type="flowers",
        assigned_to="staff-7", assigned_to_name="Ayşe",
    )
    assert task["status"] == "assigned"
    assert task["assigned_to"] == "staff-7"
    assert task["assigned_at"] is not None


async def test_unknown_type_falls_back_to_general(_patch):
    task = await _create(_patch, _user(), title="X", task_type="nope")
    assert task["task_type"] == "general"


async def test_valid_transition_open_to_completed(_patch):
    task = await _create(_patch, _user(), title="Hatırlatma", task_type="reminder")
    res = await _patch_status(task["id"], "in_progress", _user())
    assert res["status"] == "in_progress"
    res = await _patch_status(task["id"], "completed", _user(), note="bitti")
    assert res["status"] == "completed"
    doc = _patch.concierge_tasks.docs[0]
    assert doc["completed_at"] is not None
    assert doc["resolution_note"] == "bitti"


async def test_invalid_transition_rejected(_patch):
    task = await _create(_patch, _user(), title="t")
    _patch.concierge_tasks.docs[0]["status"] = "completed"
    with pytest.raises(HTTPException) as exc:
        await _patch_status(task["id"], "in_progress", _user())
    assert exc.value.status_code == 409


async def test_assign_terminal_task_rejected(_patch):
    task = await _create(_patch, _user(), title="t")
    _patch.concierge_tasks.docs[0]["status"] = "cancelled"
    with pytest.raises(HTTPException) as exc:
        await cr.assign_task(
            task_id=task["id"],
            payload=cr.AssignIn(assigned_to="s2"),
            current_user=_user(),
        )
    assert exc.value.status_code == 409


async def test_assign_open_sets_assigned(_patch):
    task = await _create(_patch, _user(), title="t")
    out = await cr.assign_task(
        task_id=task["id"],
        payload=cr.AssignIn(assigned_to="s9", assigned_to_name="Veli"),
        current_user=_user(),
    )
    assert out["task"]["status"] == "assigned"
    assert out["task"]["assigned_to"] == "s9"


async def test_status_update_rbac_denies_guest(_patch):
    task = await _create(_patch, _user(), title="t")
    with pytest.raises(HTTPException) as exc:
        await _patch_status(task["id"], "in_progress", _user("guest"))
    assert exc.value.status_code == 403


async def test_create_rbac_denies_guest(_patch):
    with pytest.raises(HTTPException) as exc:
        await _create(_patch, _user("guest"), title="t")
    assert exc.value.status_code == 403


async def test_delete_denies_front_desk_allows_admin(_patch):
    task = await _create(_patch, _user("front_desk"), title="t")
    with pytest.raises(HTTPException) as exc:
        await cr.delete_task(task_id=task["id"], current_user=_user("front_desk"))
    assert exc.value.status_code == 403
    out = await cr.delete_task(task_id=task["id"], current_user=_user("admin"))
    assert out["ok"] is True
    assert _patch.concierge_tasks.docs == []


async def test_tenant_isolation_on_get(_patch):
    task = await _create(_patch, _user(tenant="tenant-A"), title="t")
    with pytest.raises(HTTPException) as exc:
        await cr.get_task(task_id=task["id"], current_user=_user(tenant="tenant-B"))
    assert exc.value.status_code == 404


async def test_completed_is_terminal(_patch):
    task = await _create(_patch, _user(), title="t")
    r1 = await _patch_status(task["id"], "completed", _user())
    assert r1["status"] == "completed"
    # Re-completing short-circuits (same status) without raising.
    r2 = await _patch_status(task["id"], "completed", _user())
    assert r2["status"] == "completed"
    # Any non-self transition out of terminal -> 409.
    with pytest.raises(HTTPException) as exc:
        await _patch_status(task["id"], "in_progress", _user())
    assert exc.value.status_code == 409
