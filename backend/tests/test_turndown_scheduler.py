"""Targeted tests for Turndown automatic scheduling (T008).

Pinned contract (Kademe 3):
  * Only checked_in reservations generate turndown tasks; vip_only filters to
    reservations with a non-empty vip_status.
  * Idempotent per (tenant, room, day): the partial-unique compound index
    rejects a second insert -> skipped, never a duplicate task.
  * VIP rooms get priority=high; checklist attached; task_type='turndown'.
  * Tenant-scoped + housekeeping-tier RBAC.

In-memory fake-DB; the housekeeping_tasks coll enforces the
(tenant_id, room_id, task_type, turndown_date) unique key so the dedup path runs.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.pms import turndown_router as td


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
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
    def __init__(self, name, unique_key=None):
        self.name = name
        self.docs: list[dict] = []
        self._unique_key = unique_key

    def find(self, flt=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, flt or {})])

    async def insert_one(self, doc):
        if self._unique_key:
            if all(doc.get(k) is not None for k in self._unique_key):
                for d in self.docs:
                    if all(d.get(k) == doc.get(k) for k in self._unique_key):
                        raise DuplicateKeyError("dup")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))


class _FakeDB:
    def __init__(self):
        self.reservations = _Coll("reservations")
        self.housekeeping_tasks = _Coll(
            "housekeeping_tasks",
            unique_key=("tenant_id", "room_id", "task_type", "turndown_date"),
        )


TENANT = "tenant-A"


def _user(role="housekeeping", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role,
        is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(td, "db", fake)

    async def _noop():
        return None

    monkeypatch.setattr(td, "_ensure_turndown_index", _noop)
    return fake


def _seed_res(fake, *, res_id, room_id, status="checked_in", vip=None, tenant=TENANT):
    fake.reservations.docs.append({
        "id": res_id, "tenant_id": tenant, "room_id": room_id,
        "room_number": room_id, "status": status, "vip_status": vip,
    })


# ---------------------------------------------------------------------------
async def test_rbac_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await td.schedule_turndown(td.ScheduleIn(service_date="2026-06-28"),
                                   current_user=_user("front_desk"))
    assert exc.value.status_code == 403


async def test_only_checked_in_rooms(_patch):
    _seed_res(_patch, res_id="r1", room_id="101", status="checked_in")
    _seed_res(_patch, res_id="r2", room_id="102", status="confirmed")
    out = await td.schedule_turndown(
        td.ScheduleIn(service_date="2026-06-28"), current_user=_user())
    assert out["created"] == 1
    assert out["rooms_considered"] == 1


async def test_vip_only_filter(_patch):
    _seed_res(_patch, res_id="r1", room_id="101", vip="gold")
    _seed_res(_patch, res_id="r2", room_id="102", vip=None)
    out = await td.schedule_turndown(
        td.ScheduleIn(service_date="2026-06-28", vip_only=True), current_user=_user())
    assert out["created"] == 1
    task = _patch.housekeeping_tasks.docs[0]
    assert task["room_id"] == "101"
    assert task["priority"] == "high"
    assert task["vip"] is True


async def test_non_vip_normal_priority(_patch):
    _seed_res(_patch, res_id="r1", room_id="101", vip=None)
    await td.schedule_turndown(td.ScheduleIn(service_date="2026-06-28"),
                               current_user=_user())
    task = _patch.housekeeping_tasks.docs[0]
    assert task["priority"] == "normal"
    assert task["task_type"] == "turndown"
    assert task["checklist"]


async def test_idempotent_same_day(_patch):
    _seed_res(_patch, res_id="r1", room_id="101")
    first = await td.schedule_turndown(td.ScheduleIn(service_date="2026-06-28"),
                                       current_user=_user())
    second = await td.schedule_turndown(td.ScheduleIn(service_date="2026-06-28"),
                                        current_user=_user())
    assert first["created"] == 1
    assert second["created"] == 0
    assert second["skipped_existing"] == 1
    assert len(_patch.housekeeping_tasks.docs) == 1


async def test_dedup_multiple_reservations_same_room(_patch):
    _seed_res(_patch, res_id="r1", room_id="101")
    _seed_res(_patch, res_id="r2", room_id="101")
    out = await td.schedule_turndown(td.ScheduleIn(service_date="2026-06-28"),
                                     current_user=_user())
    assert out["created"] == 1
    assert len(_patch.housekeeping_tasks.docs) == 1


async def test_tenant_isolation(_patch):
    _seed_res(_patch, res_id="r1", room_id="101", tenant="other")
    out = await td.schedule_turndown(td.ScheduleIn(service_date="2026-06-28"),
                                     current_user=_user())
    assert out["created"] == 0


async def test_invalid_date_rejected(_patch):
    with pytest.raises(HTTPException) as exc:
        await td.schedule_turndown(td.ScheduleIn(service_date="28-06-2026"),
                                   current_user=_user())
    assert exc.value.status_code == 400


async def test_list_turndown_tasks(_patch):
    _seed_res(_patch, res_id="r1", room_id="101")
    await td.schedule_turndown(td.ScheduleIn(service_date="2026-06-28"),
                               current_user=_user())
    out = await td.list_turndown_tasks(service_date="2026-06-28", current_user=_user())
    assert out["count"] == 1
    assert out["items"][0]["task_type"] == "turndown"


async def test_super_admin_bypass(_patch):
    _seed_res(_patch, res_id="r1", room_id="101")
    out = await td.schedule_turndown(
        td.ScheduleIn(service_date="2026-06-28"),
        current_user=_user("nobody", super_admin=True))
    assert out["created"] == 1
