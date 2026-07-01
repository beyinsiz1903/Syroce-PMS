"""Targeted tests for Budget & variance analysis.

Pinned contract (Kademe 2):
  * Budget upsert is unique per (tenant, period, category, kind); no duplicates.
  * Actuals come from cash_flow (expense->expense, revenue->income), server-side.
  * Expense variance = budget - actual (saving positive); revenue variance =
    actual - budget. favorable flag follows the sign.
  * data_available is False when nothing is defined/spent.
  * All tenant-scoped; mutations accounting-tier RBAC.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.accounting import budget_router as bud


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
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, flt=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, flt or {})])

    async def find_one(self, flt, proj=None, sort=None):
        for d in self.docs:
            if _match(d, flt):
                return {kk: vv for kk, vv in d.items() if kk != "_id"}
        return None

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            newdoc = {k: v for k, v in flt.items() if not isinstance(v, dict)}
            newdoc.update(update.get("$set", {}))
            newdoc.update(update.get("$setOnInsert", {}))
            self.docs.append(newdoc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="x")
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.finance_budgets = _Coll()
        self.cash_flow = _Coll()


TENANT = "tenant-A"


def _user(role="accountant", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role, is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(bud, "db", fake)
    return fake


async def _set_budget(period, category, amount, kind="expense", user=None):
    return (await bud.upsert_budget(
        bud.BudgetIn(period=period, category=category, kind=kind, budget_amount=amount),
        current_user=user or _user("accountant"),
    ))["budget"]


def _flow(fake, category, amount, txn="expense", date="2026-06-15T10:00:00"):
    fake.cash_flow.docs.append({
        "tenant_id": TENANT, "transaction_type": txn, "category": category,
        "amount": amount, "date": date,
    })


# ---------------------------------------------------------------------------
# Budget CRUD
# ---------------------------------------------------------------------------
async def test_upsert_rbac_denies(_patch):
    with pytest.raises(HTTPException) as exc:
        await _set_budget("2026-06", "fnb", 1000, user=_user("front_desk"))
    assert exc.value.status_code == 403


async def test_upsert_is_unique_per_key(_patch):
    await _set_budget("2026-06", "fnb", 1000)
    await _set_budget("2026-06", "fnb", 1500)
    assert len(_patch.finance_budgets.docs) == 1
    assert _patch.finance_budgets.docs[0]["budget_amount"] == 1500


async def test_invalid_kind_400(_patch):
    with pytest.raises(HTTPException) as exc:
        await _set_budget("2026-06", "fnb", 1000, kind="bogus")
    assert exc.value.status_code == 400


async def test_invalid_period_400(_patch):
    with pytest.raises(HTTPException) as exc:
        await _set_budget("2026/06", "fnb", 1000)
    assert exc.value.status_code == 400


async def test_delete_budget(_patch):
    b = await _set_budget("2026-06", "fnb", 1000)
    out = await bud.delete_budget(b["id"], current_user=_user("accountant"))
    assert out["ok"] is True
    assert _patch.finance_budgets.docs == []


# ---------------------------------------------------------------------------
# Budget vs actual
# ---------------------------------------------------------------------------
async def test_expense_variance_saving_is_favorable(_patch):
    await _set_budget("2026-06", "fnb", 1000)
    _flow(_patch, "fnb", 800, txn="expense")  # under budget -> saving 200
    out = await bud.budget_vs_actual(period="2026-06", kind="expense", current_user=_user("accountant"))
    row = next(r for r in out["rows"] if r["category"] == "fnb")
    assert row["budget"] == 1000.0
    assert row["actual"] == 800.0
    assert row["variance"] == 200.0
    assert row["favorable"] is True
    assert out["totals"]["variance"] == 200.0


async def test_expense_overrun_is_unfavorable(_patch):
    await _set_budget("2026-06", "fnb", 1000)
    _flow(_patch, "fnb", 1200, txn="expense")
    out = await bud.budget_vs_actual(period="2026-06", kind="expense", current_user=_user("accountant"))
    row = next(r for r in out["rows"] if r["category"] == "fnb")
    assert row["variance"] == -200.0
    assert row["favorable"] is False


async def test_revenue_variance_uses_income_flows(_patch):
    await _set_budget("2026-06", "rooms", 5000, kind="revenue")
    _flow(_patch, "rooms", 6000, txn="income")
    _flow(_patch, "rooms", 999, txn="expense")  # must be ignored for revenue
    out = await bud.budget_vs_actual(period="2026-06", kind="revenue", current_user=_user("accountant"))
    row = next(r for r in out["rows"] if r["category"] == "rooms")
    assert row["actual"] == 6000.0
    assert row["variance"] == 1000.0  # actual - budget
    assert row["favorable"] is True


async def test_actuals_outside_period_excluded(_patch):
    await _set_budget("2026-06", "fnb", 1000)
    _flow(_patch, "fnb", 500, txn="expense", date="2026-07-02T10:00:00")
    out = await bud.budget_vs_actual(period="2026-06", kind="expense", current_user=_user("accountant"))
    row = next(r for r in out["rows"] if r["category"] == "fnb")
    assert row["actual"] == 0.0
    assert row["variance"] == 1000.0


async def test_no_budget_no_actual_data_unavailable(_patch):
    out = await bud.budget_vs_actual(period="2026-06", kind="expense", current_user=_user("accountant"))
    assert out["data_available"] is False
    assert out["rows"] == []


async def test_vs_actual_rbac_denies_guest(_patch):
    with pytest.raises(HTTPException) as exc:
        await bud.budget_vs_actual(period="2026-06", kind="expense", current_user=_user("guest"))
    assert exc.value.status_code == 403
