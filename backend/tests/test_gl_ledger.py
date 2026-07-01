"""Targeted tests for the General Ledger (chart of accounts + double-entry).

Pinned contract (Kademe 2):
  * Journal entries must balance (sum debit == sum credit > 0); each line is
    debit XOR credit.
  * Every account_code must exist in the tenant's active chart of accounts.
  * idempotency_key dedups posts (DuplicateKeyError -> existing entry returned).
  * Trial balance nets debit/credit per account and stays balanced.
  * COA + journal mutations are accounting-tier RBAC; tenant-scoped throughout.

In-memory fake-DB approach (mirrors tests/test_laundry_orders.py). The fake
enforces the idempotency unique constraint so the dedup path is exercised.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.accounting import gl_router as gl
from shared_kernel import gl_posting


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and ("$gte" in v or "$lte" in v):
            val = doc.get(k)
            if "$gte" in v and (val is None or val < v["$gte"]):
                return False
            if "$lte" in v and (val is None or val > v["$lte"]):
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
        self._unique_key = unique_key  # (field_a, field_b) both non-null

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
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.gl_accounts = _Coll("gl_accounts")
        self.gl_journal_entries = _Coll(
            "gl_journal_entries", unique_key=("tenant_id", "idempotency_key")
        )


TENANT = "tenant-A"


def _user(role="accountant", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role,
        is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(gl, "db", fake)

    async def _noop(_db):
        return None

    monkeypatch.setattr(gl_posting, "ensure_gl_idem_index", _noop)
    return fake


async def _mk_account(code, name, atype, user=None):
    return await gl.create_account(
        gl.AccountIn(code=code, name=name, type=atype),
        current_user=user or _user("accountant"),
    )


async def _seed_basic_coa():
    await _mk_account("100", "Kasa", "asset")
    await _mk_account("600", "Satış Geliri", "revenue")
    await _mk_account("740", "Hizmet Maliyeti", "expense")


def _journal(lines, **kw):
    return gl.JournalIn(
        memo=kw.get("memo", "test"),
        date=kw.get("date", "2026-06-01"),
        lines=[gl.JournalLineIn(**ln) for ln in lines],
        source=kw.get("source", "manual"),
        idempotency_key=kw.get("idempotency_key"),
    )


# ---------------------------------------------------------------------------
# Chart of accounts
# ---------------------------------------------------------------------------
async def test_create_account_rbac_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await _mk_account("100", "Kasa", "asset", user=_user("front_desk"))
    assert exc.value.status_code == 403


async def test_create_account_invalid_type_400(_patch):
    with pytest.raises(HTTPException) as exc:
        await _mk_account("100", "X", "bogus")
    assert exc.value.status_code == 400


async def test_create_account_duplicate_code_400(_patch):
    await _mk_account("100", "Kasa", "asset")
    with pytest.raises(HTTPException) as exc:
        await _mk_account("100", "Kasa 2", "asset")
    assert exc.value.status_code == 400


async def test_account_normal_balance_derived(_patch):
    out = await _mk_account("100", "Kasa", "asset")
    assert out["account"]["normal_balance"] == "debit"
    out2 = await _mk_account("600", "Gelir", "revenue")
    assert out2["account"]["normal_balance"] == "credit"


# ---------------------------------------------------------------------------
# Journal posting
# ---------------------------------------------------------------------------
async def test_balanced_journal_posts(_patch):
    await _seed_basic_coa()
    out = await gl.create_journal(
        _journal([
            {"account_code": "100", "debit": 100},
            {"account_code": "600", "credit": 100},
        ]),
        current_user=_user("accountant"),
    )
    e = out["entry"]
    assert e["total_debit"] == 100.0
    assert e["total_credit"] == 100.0
    assert e["status"] == "posted"
    assert len(_patch.gl_journal_entries.docs) == 1


async def test_unbalanced_journal_rejected(_patch):
    await _seed_basic_coa()
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal([
                {"account_code": "100", "debit": 100},
                {"account_code": "600", "credit": 90},
            ]),
            current_user=_user("accountant"),
        )
    assert exc.value.status_code == 400
    assert _patch.gl_journal_entries.docs == []


async def test_line_debit_xor_credit_enforced(_patch):
    await _seed_basic_coa()
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal([
                {"account_code": "100", "debit": 50, "credit": 50},
                {"account_code": "600", "credit": 50},
            ]),
            current_user=_user("accountant"),
        )
    assert exc.value.status_code == 400


async def test_unknown_account_rejected(_patch):
    await _mk_account("100", "Kasa", "asset")
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal([
                {"account_code": "100", "debit": 10},
                {"account_code": "999", "credit": 10},
            ]),
            current_user=_user("accountant"),
        )
    assert exc.value.status_code == 400


async def test_inactive_account_rejected(_patch):
    await _seed_basic_coa()
    await gl.update_account("600", gl.AccountUpdate(active=False), current_user=_user("accountant"))
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal([
                {"account_code": "100", "debit": 10},
                {"account_code": "600", "credit": 10},
            ]),
            current_user=_user("accountant"),
        )
    assert exc.value.status_code == 400


async def test_journal_rbac_denies_supervisor(_patch):
    await _seed_basic_coa()
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal([
                {"account_code": "100", "debit": 10},
                {"account_code": "600", "credit": 10},
            ]),
            current_user=_user("supervisor"),
        )
    assert exc.value.status_code == 403


async def test_idempotency_key_dedups(_patch):
    await _seed_basic_coa()
    j = _journal(
        [{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}],
        idempotency_key="payroll-2026-06",
    )
    first = await gl.create_journal(j, current_user=_user("accountant"))
    second = await gl.create_journal(j, current_user=_user("accountant"))
    assert first["entry"]["id"] == second["entry"]["id"]
    assert len(_patch.gl_journal_entries.docs) == 1


# ---------------------------------------------------------------------------
# Trial balance
# ---------------------------------------------------------------------------
async def test_trial_balance_balanced(_patch):
    await _seed_basic_coa()
    await gl.create_journal(
        _journal([
            {"account_code": "100", "debit": 100},
            {"account_code": "600", "credit": 100},
        ]),
        current_user=_user("accountant"),
    )
    await gl.create_journal(
        _journal([
            {"account_code": "740", "debit": 40},
            {"account_code": "100", "credit": 40},
        ]),
        current_user=_user("accountant"),
    )
    tb = await gl.trial_balance(as_of=None, current_user=_user("accountant"))
    by_code = {r["account_code"]: r for r in tb["rows"]}
    assert by_code["100"]["debit_balance"] == 60.0
    assert by_code["600"]["credit_balance"] == 100.0
    assert by_code["740"]["debit_balance"] == 40.0
    assert tb["totals"]["debit_balance"] == 100.0
    assert tb["totals"]["credit_balance"] == 100.0
    assert tb["totals"]["balanced"] is True
