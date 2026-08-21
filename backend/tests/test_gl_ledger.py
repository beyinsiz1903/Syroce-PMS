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

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from core.tenant_db import TENANT_SCOPED_COLLECTIONS
from domains.accounting import gl_router as gl
from shared_kernel import gl_posting


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and ("$gte" in v or "$lte" in v or "$gt" in v or "$lt" in v):
            val = doc.get(k)
            if "$gte" in v and (val is None or val < v["$gte"]):
                return False
            if "$lte" in v and (val is None or val > v["$lte"]):
                return False
            if "$gt" in v and (val is None or val <= v["$gt"]):
                return False
            if "$lt" in v and (val is None or val >= v["$lt"]):
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
                for key, value in update.get("$push", {}).items():
                    d.setdefault(key, []).append(value)
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            doc = dict(flt)
            doc.update(update.get("$setOnInsert", {}))
            doc.update(update.get("$set", {}))
            self.docs.append(doc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="x")
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def find_one_and_update(self, flt, update, upsert=False, return_document=None):
        del return_document
        for d in self.docs:
            if _match(d, flt):
                for key, value in update.get("$inc", {}).items():
                    d[key] = d.get(key, 0) + value
                d.update(update.get("$set", {}))
                return {kk: vv for kk, vv in d.items() if kk != "_id"} | ({"_id": d["_id"]} if "_id" in d else {})
        if not upsert:
            return None
        doc = dict(flt)
        doc.update(update.get("$setOnInsert", {}))
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        doc.update(update.get("$set", {}))
        self.docs.append(doc)
        return dict(doc)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.gl_accounts = _Coll("gl_accounts")
        self.gl_counters = _Coll("gl_counters")
        self.gl_journal_entries = _Coll("gl_journal_entries", unique_key=("tenant_id", "idempotency_key"))
        self.gl_periods = _Coll("gl_periods")
        self.gl_sequence_reservations = _Coll("gl_sequence_reservations")
        self.payroll_gl_mapping = _Coll("payroll_gl_mapping")


TENANT = "tenant-A"


def test_accounting_subledgers_are_strictly_tenant_scoped():
    assert {
        "ap_invoices",
        "ap_payments",
        "proc_purchase_orders",
        "proc_suppliers",
        "cash_flow",
        "finance_budgets",
        "fixed_assets",
        "depreciation_entries",
        "gl_counters",
        "gl_sequence_reservations",
    }.issubset(TENANT_SCOPED_COLLECTIONS)


def _user(role="finance", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1",
        user_id="u1",
        tenant_id=tenant,
        role=role,
        is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(gl, "db", fake)

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(gl_posting, "ensure_gl_idem_index", _noop)
    monkeypatch.setattr(gl, "ensure_compound_unique", _noop)
    monkeypatch.setattr(gl, "log_audit_event", _noop)
    return fake


async def _mk_account(code, name, atype, user=None):
    return await gl.create_account(
        gl.AccountIn(code=code, name=name, type=atype),
        current_user=user or _user("finance"),
    )


async def _seed_basic_coa():
    await _mk_account("100", "Kasa", "asset")
    await _mk_account("600", "Satış Geliri", "revenue")
    await _mk_account("740", "Hizmet Maliyeti", "expense")


def test_gl_roles_follow_the_real_user_role_enum():
    assert gl._GL_ROLES == {"super_admin", "admin", "finance"}
    assert "accountant" not in gl._GL_ROLES


def _journal(lines, **kw):
    return gl.JournalIn(
        memo=kw.get("memo", "test"),
        date=kw.get("date", "2026-06-01"),
        lines=[gl.JournalLineIn(**ln) for ln in lines],
        source=kw.get("source", "manual"),
        idempotency_key=kw.get("idempotency_key", str(uuid.uuid4())),
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


async def test_account_mutations_emit_audit_events(_patch, monkeypatch):
    events = []

    async def _record(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(gl, "log_audit_event", _record)
    await _mk_account("100", "Kasa", "asset")
    await gl.update_account("100", gl.AccountUpdate(name="Merkez Kasa"), current_user=_user("finance"))

    assert [event["action"] for event in events] == ["gl_account_created", "gl_account_updated"]
    assert events[1]["before_value"]["name"] == "Kasa"
    assert events[1]["after_value"]["name"] == "Merkez Kasa"


async def test_initialize_chart_of_accounts_is_tenant_scoped_and_idempotent(_patch):
    first = await gl.initialize_chart_of_accounts(current_user=_user("finance"))
    second = await gl.initialize_chart_of_accounts(current_user=_user("finance"))

    assert first == {"created": 14, "total": 14, "payroll_mapping_created": True}
    assert second == {"created": 0, "total": 14, "payroll_mapping_created": False}
    assert len(_patch.gl_accounts.docs) == 14
    assert _patch.payroll_gl_mapping.docs[0]["withholding_payable_code"] == "360"
    assert {row["tenant_id"] for row in _patch.gl_accounts.docs} == {TENANT}


async def test_initialize_chart_of_accounts_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await gl.initialize_chart_of_accounts(current_user=_user("front_desk"))
    assert exc.value.status_code == 403
    assert _patch.gl_accounts.docs == []


async def test_account_reads_require_accounting_read_role(_patch):
    await _mk_account("100", "Kasa", "asset")

    with pytest.raises(HTTPException) as exc:
        await gl.list_accounts(include_inactive=True, type=None, current_user=_user("front_desk"))
    assert exc.value.status_code == 403

    result = await gl.list_accounts(include_inactive=True, type=None, current_user=_user("supervisor"))
    assert [row["code"] for row in result["accounts"]] == ["100"]


# ---------------------------------------------------------------------------
# Journal posting
# ---------------------------------------------------------------------------
async def test_balanced_journal_posts(_patch):
    await _seed_basic_coa()
    out = await gl.create_journal(
        _journal(
            [
                {"account_code": "100", "debit": 100},
                {"account_code": "600", "credit": 100},
            ]
        ),
        current_user=_user("finance"),
    )
    e = out["entry"]
    assert e["total_debit"] == 100.0
    assert e["total_credit"] == 100.0
    assert e["status"] == "posted"
    assert e["entry_no"] == "YEV-2026-00000001"
    assert e["posting_sequence"] == 1
    assert len(_patch.gl_journal_entries.docs) == 1
    assert _patch.gl_sequence_reservations.docs[0]["status"] == "posted"


async def test_manual_journal_emits_tamper_evident_audit_event(_patch, monkeypatch):
    await _seed_basic_coa()
    events = []

    async def _record(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(gl, "log_audit_event", _record)
    out = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}]),
        current_user=_user("finance"),
    )

    assert len(events) == 1
    assert events[0]["action"] == "gl_manual_journal_posted"
    assert events[0]["entity_id"] == out["entry"]["id"]
    assert events[0]["after_value"]["entry_no"] == "YEV-2026-00000001"


async def test_unbalanced_journal_rejected(_patch):
    await _seed_basic_coa()
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal(
                [
                    {"account_code": "100", "debit": 100},
                    {"account_code": "600", "credit": 90},
                ]
            ),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 400
    assert _patch.gl_journal_entries.docs == []


async def test_line_debit_xor_credit_enforced(_patch):
    await _seed_basic_coa()
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal(
                [
                    {"account_code": "100", "debit": 50, "credit": 50},
                    {"account_code": "600", "credit": 50},
                ]
            ),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 400


async def test_unknown_account_rejected(_patch):
    await _mk_account("100", "Kasa", "asset")
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal(
                [
                    {"account_code": "100", "debit": 10},
                    {"account_code": "999", "credit": 10},
                ]
            ),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 400


async def test_inactive_account_rejected(_patch):
    await _seed_basic_coa()
    await gl.update_account("600", gl.AccountUpdate(active=False), current_user=_user("finance"))
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal(
                [
                    {"account_code": "100", "debit": 10},
                    {"account_code": "600", "credit": 10},
                ]
            ),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 400


async def test_journal_rbac_denies_supervisor(_patch):
    await _seed_basic_coa()
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal(
                [
                    {"account_code": "100", "debit": 10},
                    {"account_code": "600", "credit": 10},
                ]
            ),
            current_user=_user("supervisor"),
        )
    assert exc.value.status_code == 403


async def test_idempotency_key_dedups(_patch):
    await _seed_basic_coa()
    j = _journal(
        [{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}],
        idempotency_key="payroll-2026-06",
    )
    first = await gl.create_journal(j, current_user=_user("finance"))
    second = await gl.create_journal(j, current_user=_user("finance"))
    assert first["entry"]["id"] == second["entry"]["id"]
    assert len(_patch.gl_journal_entries.docs) == 1
    assert len(_patch.gl_sequence_reservations.docs) == 1
    assert _patch.gl_counters.docs[0]["value"] == 1


async def test_journal_sequence_is_monotonic_per_fiscal_year(_patch):
    await _seed_basic_coa()
    first = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}]),
        current_user=_user("finance"),
    )
    second = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 20}, {"account_code": "600", "credit": 20}]),
        current_user=_user("finance"),
    )
    assert first["entry"]["entry_no"] == "YEV-2026-00000001"
    assert second["entry"]["entry_no"] == "YEV-2026-00000002"

    audit = await gl.sequence_audit(fiscal_year=2026, current_user=_user("supervisor"))
    assert audit["healthy"] is True
    assert audit["totals"] == {"count": 2, "posted": 2, "void": 0, "reserved": 0, "missing": 0}


async def test_sequence_audit_detects_counter_gap(_patch):
    await _seed_basic_coa()
    await gl.create_journal(
        _journal([{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}]),
        current_user=_user("finance"),
    )
    _patch.gl_counters.docs[0]["value"] = 2

    audit = await gl.sequence_audit(fiscal_year=2026, current_user=_user("finance"))

    assert audit["healthy"] is False
    assert audit["totals"]["missing"] == 1
    assert audit["missing_sequences"] == {"2026": [2]}


async def test_sequence_audit_requires_accounting_read_role(_patch):
    with pytest.raises(HTTPException) as exc:
        await gl.sequence_audit(fiscal_year=2026, current_user=_user("front_desk"))
    assert exc.value.status_code == 403


async def test_idempotency_key_reuse_with_different_payload_is_rejected(_patch):
    await _seed_basic_coa()
    first = _journal(
        [{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}],
        idempotency_key="manual-key-1",
    )
    second = _journal(
        [{"account_code": "100", "debit": 20}, {"account_code": "600", "credit": 20}],
        idempotency_key="manual-key-1",
    )
    await gl.create_journal(first, current_user=_user("finance"))
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(second, current_user=_user("finance"))
    assert exc.value.status_code == 409
    assert len(_patch.gl_journal_entries.docs) == 1


async def test_manual_journal_requires_idempotency_key(_patch):
    await _seed_basic_coa()
    payload = _journal(
        [{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}],
        idempotency_key=None,
    )
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(payload, current_user=_user("finance"))
    assert exc.value.status_code == 422


def test_manual_journal_source_cannot_impersonate_an_integration():
    with pytest.raises(ValidationError):
        _journal(
            [{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}],
            source="payroll",
        )


async def test_journal_reads_require_accounting_read_role(_patch):
    await _seed_basic_coa()
    posted = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}]),
        current_user=_user("finance"),
    )

    with pytest.raises(HTTPException) as list_exc:
        await gl.list_journal(start=None, end=None, limit=200, current_user=_user("front_desk"))
    assert list_exc.value.status_code == 403

    with pytest.raises(HTTPException) as detail_exc:
        await gl.get_journal(posted["entry"]["id"], current_user=_user("front_desk"))
    assert detail_exc.value.status_code == 403

    listed = await gl.list_journal(start=None, end=None, limit=200, current_user=_user("supervisor"))
    detail = await gl.get_journal(posted["entry"]["id"], current_user=_user("supervisor"))
    assert [row["id"] for row in listed["entries"]] == [posted["entry"]["id"]]
    assert detail["entry"]["id"] == posted["entry"]["id"]


async def test_money_is_rounded_and_balanced_in_minor_units(_patch):
    await _seed_basic_coa()
    payload = _journal(
        [{"account_code": "100", "debit": "0.105"}, {"account_code": "600", "credit": "0.11"}],
    )
    out = await gl.create_journal(payload, current_user=_user("finance"))
    entry = out["entry"]
    assert entry["total_debit"] == 0.11
    assert entry["total_debit_minor"] == 11
    assert entry["lines"][0]["debit_minor"] == 11
    assert entry["lines"][1]["credit_minor"] == 11


# ---------------------------------------------------------------------------
# Journal reversal
# ---------------------------------------------------------------------------
async def test_reversal_creates_linked_contra_entry_and_preserves_source(_patch):
    await _seed_basic_coa()
    original = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 75}, {"account_code": "600", "credit": 75}]),
        current_user=_user("finance"),
    )
    original_id = original["entry"]["id"]
    out = await gl.reverse_journal(
        original_id,
        gl.JournalReversalIn(
            date="2026-06-02",
            reason="Hatalı hesap seçimi",
            idempotency_key="reverse-request-001",
        ),
        current_user=_user("finance"),
    )
    reversal = out["entry"]
    assert reversal["reverses_entry_id"] == original_id
    assert reversal["lines"][0]["credit_minor"] == 7500
    assert reversal["lines"][1]["debit_minor"] == 7500
    source = await _patch.gl_journal_entries.find_one({"id": original_id})
    assert source["status"] == "posted"
    assert source["reversal_status"] == "reversed"
    assert source["reversed_by_entry_id"] == reversal["id"]
    trial = await gl.trial_balance(as_of=None, current_user=_user("finance"))
    assert trial["totals"]["debit_balance_minor"] == 0
    assert trial["totals"]["credit_balance_minor"] == 0


async def test_reversal_is_single_and_idempotent(_patch):
    await _seed_basic_coa()
    original = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}]),
        current_user=_user("finance"),
    )
    original_id = original["entry"]["id"]
    request = gl.JournalReversalIn(
        date="2026-06-02",
        reason="Mükerrer kayıt",
        idempotency_key="reverse-request-002",
    )
    first = await gl.reverse_journal(original_id, request, current_user=_user("finance"))
    retry = await gl.reverse_journal(original_id, request, current_user=_user("finance"))
    assert retry["entry"]["id"] == first["entry"]["id"]
    with pytest.raises(HTTPException) as exc:
        await gl.reverse_journal(
            original_id,
            gl.JournalReversalIn(
                date="2026-06-02",
                reason="İkinci ters kayıt",
                idempotency_key="reverse-request-other",
            ),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 409


async def test_reversal_date_must_be_in_open_period(_patch):
    await _seed_basic_coa()
    original = await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}],
            date="2026-01-15",
        ),
        current_user=_user("finance"),
    )
    await gl.close_period(
        original["entry"]["period_id"],
        gl.PeriodActionIn(reason="Ocak kapanışı"),
        current_user=_user("finance"),
    )
    with pytest.raises(HTTPException) as exc:
        await gl.reverse_journal(
            original["entry"]["id"],
            gl.JournalReversalIn(
                date="2026-01-31",
                reason="Kapalı döneme ters kayıt",
                idempotency_key="reverse-request-003",
            ),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Fiscal periods
# ---------------------------------------------------------------------------
async def test_initialize_fiscal_year_creates_twelve_open_periods(_patch):
    out = await gl.initialize_periods(gl.FiscalYearIn(fiscal_year=2026), current_user=_user("finance"))
    assert len(out["periods"]) == 12
    assert {period["status"] for period in out["periods"]} == {"open"}
    assert out["periods"][0]["start_date"] == "2026-01-01"
    assert out["periods"][-1]["end_date"] == "2026-12-31"


async def test_closed_period_blocks_new_post_but_allows_exact_retry(_patch):
    await _seed_basic_coa()
    key = "close-retry-key"
    payload = _journal(
        [{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}],
        date="2026-01-15",
        idempotency_key=key,
    )
    first = await gl.create_journal(payload, current_user=_user("finance"))
    period_id = first["entry"]["period_id"]
    await gl.close_period(
        period_id,
        gl.PeriodActionIn(reason="Ocak kapanışı"),
        current_user=_user("finance"),
    )

    retry = await gl.create_journal(payload, current_user=_user("finance"))
    assert retry["entry"]["id"] == first["entry"]["id"]

    new_payload = _journal(
        [{"account_code": "100", "debit": 5}, {"account_code": "600", "credit": 5}],
        date="2026-01-20",
    )
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(new_payload, current_user=_user("finance"))
    assert exc.value.status_code == 409


async def test_periods_must_close_and_reopen_in_order(_patch):
    await gl.initialize_periods(gl.FiscalYearIn(fiscal_year=2026), current_user=_user("finance"))
    january = "tenant-A:2026:01"
    february = "tenant-A:2026:02"
    with pytest.raises(HTTPException) as exc:
        await gl.close_period(
            february,
            gl.PeriodActionIn(reason="Şubat kapanışı"),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 409

    await gl.close_period(
        january,
        gl.PeriodActionIn(reason="Ocak kapanışı"),
        current_user=_user("finance"),
    )
    await gl.close_period(
        february,
        gl.PeriodActionIn(reason="Şubat kapanışı"),
        current_user=_user("finance"),
    )
    with pytest.raises(HTTPException) as exc:
        await gl.reopen_period(
            january,
            gl.PeriodActionIn(reason="Düzeltme gerekiyor"),
            current_user=_user("admin"),
        )
    assert exc.value.status_code == 409
    await gl.reopen_period(
        february,
        gl.PeriodActionIn(reason="Düzeltme gerekiyor"),
        current_user=_user("admin"),
    )
    reopened = await gl.reopen_period(
        january,
        gl.PeriodActionIn(reason="Düzeltme gerekiyor"),
        current_user=_user("admin"),
    )
    assert reopened["period"]["status"] == "open"


async def test_finance_role_cannot_reopen_closed_period(_patch):
    await gl.initialize_periods(gl.FiscalYearIn(fiscal_year=2026), current_user=_user("finance"))
    january = "tenant-A:2026:01"
    await gl.close_period(
        january,
        gl.PeriodActionIn(reason="Ocak kapanışı"),
        current_user=_user("finance"),
    )
    with pytest.raises(HTTPException) as exc:
        await gl.reopen_period(
            january,
            gl.PeriodActionIn(reason="Yetkisiz açma"),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Trial balance
# ---------------------------------------------------------------------------
async def test_trial_balance_balanced(_patch):
    await _seed_basic_coa()
    await gl.create_journal(
        _journal(
            [
                {"account_code": "100", "debit": 100},
                {"account_code": "600", "credit": 100},
            ]
        ),
        current_user=_user("finance"),
    )
    await gl.create_journal(
        _journal(
            [
                {"account_code": "740", "debit": 40},
                {"account_code": "100", "credit": 40},
            ]
        ),
        current_user=_user("finance"),
    )
    tb = await gl.trial_balance(as_of=None, current_user=_user("finance"))
    by_code = {r["account_code"]: r for r in tb["rows"]}
    assert by_code["100"]["debit_balance"] == 60.0
    assert by_code["600"]["credit_balance"] == 100.0
    assert by_code["740"]["debit_balance"] == 40.0
    assert tb["totals"]["debit_balance"] == 100.0
    assert tb["totals"]["credit_balance"] == 100.0
    assert tb["totals"]["balanced"] is True


async def test_income_statement_and_balance_sheet_are_derived_from_posted_ledger(_patch):
    await _seed_basic_coa()
    await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 100}, {"account_code": "600", "credit": 100}],
            date="2026-06-01",
        ),
        current_user=_user("finance"),
    )
    await gl.create_journal(
        _journal(
            [{"account_code": "740", "debit": 40}, {"account_code": "100", "credit": 40}],
            date="2026-06-02",
        ),
        current_user=_user("finance"),
    )

    income = await gl.income_statement(
        start="2026-06-01",
        end="2026-06-30",
        current_user=_user("finance"),
    )
    assert income["totals"]["revenue_minor"] == 10000
    assert income["totals"]["expenses_minor"] == 4000
    assert income["totals"]["net_income_minor"] == 6000

    balance = await gl.balance_sheet(as_of="2026-06-30", current_user=_user("finance"))
    assert balance["totals"]["assets"] == 60.0
    assert balance["current_earnings"]["amount"] == 60.0
    assert balance["totals"]["liabilities_and_equity"] == 60.0
    assert balance["totals"]["balanced"] is True


async def test_income_statement_honors_date_range(_patch):
    await _seed_basic_coa()
    await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 25}, {"account_code": "600", "credit": 25}],
            date="2026-05-31",
        ),
        current_user=_user("finance"),
    )
    income = await gl.income_statement(
        start="2026-06-01",
        end="2026-06-30",
        current_user=_user("finance"),
    )
    assert income["totals"]["revenue_minor"] == 0
