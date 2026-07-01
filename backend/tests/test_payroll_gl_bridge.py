"""Targeted tests for the Payroll -> GL bridge (T007).

Pinned contract (Kademe 2, blocked-by T003):
  * Only a locked payroll run may be posted (draft/missing -> fail-closed).
  * Account mapping must be configured AND every code must exist in the COA.
  * Journal is balanced: debit wage_expense = gross; credit net_payable = net;
    credit withholding = gross - net. Two lines when withholding is zero.
  * idempotency_key=payroll:{run_id} -> second post returns the same entry, no
    double-post.
  * Everything tenant-scoped + accounting-tier RBAC.

In-memory fake-DB mirrors tests/test_gl_ledger.py; the fake enforces the
idempotency unique constraint so the dedup path is exercised end-to-end.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.accounting import gl_router as gl
from domains.accounting import payroll_gl_router as pg
from shared_kernel import gl_posting


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
    def __init__(self, name, unique_key=None):
        self.name = name
        self.docs: list[dict] = []
        self._unique_key = unique_key

    def find(self, flt=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, flt or {})])

    async def find_one(self, flt, proj=None, sort=None):
        for d in self.docs:
            if _match(d, flt):
                return {kk: vv for kk, vv in d.items() if kk != "_id"}
        return None

    async def insert_one(self, doc):
        if self._unique_key:
            a, b = self._unique_key
            if doc.get(a) is not None and doc.get(b) is not None:
                for d in self.docs:
                    if d.get(a) == doc.get(a) and d.get(b) == doc.get(b):
                        raise DuplicateKeyError("dup")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            doc = dict(flt)
            doc.update(update.get("$set", {}))
            self.docs.append(doc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="x")
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeDB:
    def __init__(self):
        self.gl_accounts = _Coll("gl_accounts")
        self.gl_journal_entries = _Coll(
            "gl_journal_entries", unique_key=("tenant_id", "idempotency_key")
        )
        self.payroll_runs = _Coll("payroll_runs")
        self.payroll_gl_mapping = _Coll("payroll_gl_mapping")


TENANT = "tenant-A"


def _user(role="accountant", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role,
        is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(pg, "db", fake)
    monkeypatch.setattr(gl, "db", fake)

    async def _noop(_db):
        return None

    monkeypatch.setattr(gl_posting, "ensure_gl_idem_index", _noop)
    return fake


async def _seed_coa():
    await gl.create_account(gl.AccountIn(code="770", name="Ücret Gideri", type="expense"),
                            current_user=_user("accountant"))
    await gl.create_account(gl.AccountIn(code="335", name="Personele Borç", type="liability"),
                            current_user=_user("accountant"))
    await gl.create_account(gl.AccountIn(code="360", name="Vergi/SGK Yükümlülük", type="liability"),
                            current_user=_user("accountant"))


async def _set_mapping(user=None):
    return await pg.set_mapping(
        pg.MappingIn(
            wage_expense_code="770",
            withholding_payable_code="360",
            net_payable_code="335",
        ),
        current_user=user or _user("accountant"),
    )


def _seed_run(fake, *, run_id="run-1", status="locked", gross=10000.0, net=7500.0,
              period="2026-06", tenant=TENANT):
    fake.payroll_runs.docs.append({
        "id": run_id, "tenant_id": tenant, "status": status,
        "period_month": period,
        "summary": {"total_gross": gross, "total_net": net},
    })


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------
async def test_mapping_rbac_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await _set_mapping(user=_user("front_desk"))
    assert exc.value.status_code == 403


async def test_mapping_rejects_unknown_account(_patch):
    await _seed_coa()
    with pytest.raises(HTTPException) as exc:
        await pg.set_mapping(
            pg.MappingIn(wage_expense_code="770", withholding_payable_code="360",
                         net_payable_code="999"),
            current_user=_user("accountant"),
        )
    assert exc.value.status_code == 400


async def test_mapping_set_and_get(_patch):
    await _seed_coa()
    await _set_mapping()
    out = await pg.get_mapping(current_user=_user("accountant"))
    assert out["mapping"]["wage_expense_code"] == "770"


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------
async def test_post_requires_locked_run(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch, status="draft")
    with pytest.raises(HTTPException) as exc:
        await pg.post_payroll("run-1", current_user=_user("accountant"))
    assert exc.value.status_code == 409


async def test_post_missing_run_404(_patch):
    await _seed_coa()
    await _set_mapping()
    with pytest.raises(HTTPException) as exc:
        await pg.post_payroll("nope", current_user=_user("accountant"))
    assert exc.value.status_code == 404


async def test_post_requires_mapping(_patch):
    await _seed_coa()
    _seed_run(_patch)
    with pytest.raises(HTTPException) as exc:
        await pg.post_payroll("run-1", current_user=_user("accountant"))
    assert exc.value.status_code == 409


async def test_post_rbac_denies_supervisor(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch)
    with pytest.raises(HTTPException) as exc:
        await pg.post_payroll("run-1", current_user=_user("supervisor"))
    assert exc.value.status_code == 403


async def test_post_balanced_three_lines(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch, gross=10000.0, net=7500.0)
    out = await pg.post_payroll("run-1", current_user=_user("accountant"))
    e = out["entry"]
    assert e["total_debit"] == 10000.0
    assert e["total_credit"] == 10000.0
    lines = {ln["account_code"]: ln for ln in e["lines"]}
    assert lines["770"]["debit"] == 10000.0
    assert lines["335"]["credit"] == 7500.0
    assert lines["360"]["credit"] == 2500.0


async def test_post_zero_withholding_two_lines(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch, gross=5000.0, net=5000.0)
    out = await pg.post_payroll("run-1", current_user=_user("accountant"))
    e = out["entry"]
    assert len(e["lines"]) == 2
    assert e["total_debit"] == 5000.0


async def test_post_idempotent_no_double(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch)
    first = await pg.post_payroll("run-1", current_user=_user("accountant"))
    second = await pg.post_payroll("run-1", current_user=_user("accountant"))
    assert first["entry"]["id"] == second["entry"]["id"]
    assert len(_patch.gl_journal_entries.docs) == 1


async def test_post_zero_gross_rejected(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch, gross=0.0, net=0.0)
    with pytest.raises(HTTPException) as exc:
        await pg.post_payroll("run-1", current_user=_user("accountant"))
    assert exc.value.status_code == 400


async def test_post_tenant_isolated(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch, tenant="other")
    with pytest.raises(HTTPException) as exc:
        await pg.post_payroll("run-1", current_user=_user("accountant"))
    assert exc.value.status_code == 404


async def test_status_reports_posted(_patch):
    await _seed_coa()
    await _set_mapping()
    _seed_run(_patch)
    await pg.post_payroll("run-1", current_user=_user("accountant"))
    st = await pg.posting_status("run-1", current_user=_user("accountant"))
    assert st["posted"] is True
    assert st["entry"]["idempotency_key"] == "payroll:run-1"
