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

import io
import json
import uuid
import zipfile
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
        if k == "$or":
            if not any(_match(doc, clause) for clause in v):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
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
                for key in update.get("$unset", {}):
                    d.pop(key, None)
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

    async def count_documents(self, flt):
        return sum(1 for doc in self.docs if _match(doc, flt))


class _FakeDB:
    def __init__(self):
        self.gl_accounts = _Coll("gl_accounts")
        self.gl_counters = _Coll("gl_counters")
        self.gl_journal_entries = _Coll("gl_journal_entries", unique_key=("tenant_id", "idempotency_key"))
        self.gl_vouchers = _Coll("gl_vouchers")
        self.gl_operational_mappings = _Coll("gl_operational_mappings")
        self.gl_intercompany_rules = _Coll("gl_intercompany_rules")
        self.gl_eledger_settings = _Coll("gl_eledger_settings")
        self.gl_setup_profiles = _Coll("gl_setup_profiles")
        self.gl_periods = _Coll("gl_periods")
        self.gl_sequence_reservations = _Coll("gl_sequence_reservations")
        self.gl_year_end_closures = _Coll("gl_year_end_closures")
        self.payroll_gl_mapping = _Coll("payroll_gl_mapping")
        self.tenants = _Coll("tenants")
        self.hotel_chains = _Coll("hotel_chains")


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
        "gl_year_end_closures",
        "gl_operational_mappings",
        "gl_intercompany_rules",
        "gl_eledger_settings",
        "gl_setup_profiles",
    }.issubset(TENANT_SCOPED_COLLECTIONS)


def _user(role="finance", *, super_admin=False, tenant=TENANT, user_id="u1"):
    return SimpleNamespace(
        id=user_id,
        user_id=user_id,
        tenant_id=tenant,
        role=role,
        is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(gl, "db", fake)
    monkeypatch.setattr(gl, "_system_db", fake)

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


def test_accounting_setup_profile_validates_tenant_specific_legal_data():
    profile = gl.AccountingSetupProfileIn(
        legal_name="The Canyon Turizm AŞ",
        taxpayer_id="1234567890",
        tax_office="Kartepe",
        address="Kartepe Kocaeli",
        city="Kocaeli",
        fiscal_year=2026,
        migration_date="2026-01-01",
    )
    assert profile.currency == "TRY"
    assert profile.opening_balance_required is False

    with pytest.raises(ValidationError):
        gl.AccountingSetupProfileIn(
            legal_name="The Canyon",
            taxpayer_id="123",
            tax_office="Kartepe",
            address="Kartepe Kocaeli",
            city="Kocaeli",
            fiscal_year=2026,
            migration_date="2026-01-01",
        )


@pytest.mark.asyncio
async def test_accounting_setup_profile_is_tenant_scoped_and_reports_blockers(_patch):
    response = await gl.save_accounting_setup_profile(
        gl.AccountingSetupProfileIn(
            legal_name="The Canyon Turizm AŞ",
            taxpayer_id="1234567890",
            tax_office="Kartepe",
            address="Kartepe Kocaeli",
            city="Kocaeli",
            fiscal_year=2026,
            migration_date="2026-01-01",
            opening_balance_required=True,
        ),
        current_user=_user("finance"),
    )

    assert response["profile"]["tenant_id"] == TENANT
    assert response["profile"]["taxpayer_id"] == "1234567890"
    assert response["ready"] is False
    assert {item["code"] for item in response["blockers"]} == {
        "chart_of_accounts", "fiscal_periods", "operational_mapping", "opening_balance"
    }
    assert _patch.gl_eledger_settings.docs[0]["legal_name"] == "The Canyon Turizm AŞ"


@pytest.mark.asyncio
async def test_accounting_setup_opening_balance_is_draft_and_idempotent():
    payload = gl.AccountingSetupOpeningBalanceIn(
        date="2026-01-01",
        memo="Kontrollü açılış bakiyesi",
        idempotency_key="opening-import-2026",
        lines=[
            gl.JournalLineIn(account_code="100", debit=1000, credit=0),
            gl.JournalLineIn(account_code="570", debit=0, credit=1000),
        ],
    )
    first = await gl.create_accounting_setup_opening_balance(payload, current_user=_user("finance"))
    replay = await gl.create_accounting_setup_opening_balance(payload, current_user=_user("finance"))

    assert first["voucher"]["status"] == "draft"
    assert first["voucher"]["voucher_type"] == "acilis"
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert replay["voucher"]["id"] == first["voucher"]["id"]


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


async def test_account_allows_explicit_contra_balance(_patch):
    out = await gl.create_account(
        gl.AccountIn(
            code="257",
            name="Birikmiş Amortismanlar",
            type="asset",
            normal_balance="credit",
        ),
        current_user=_user("finance"),
    )
    assert out["account"]["normal_balance"] == "credit"


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

    assert first == {"created": 24, "total": 24, "payroll_mapping_created": True}
    assert second == {"created": 0, "total": 24, "payroll_mapping_created": False}
    assert len(_patch.gl_accounts.docs) == 24
    assert next(row for row in _patch.gl_accounts.docs if row["code"] == "257")["normal_balance"] == "credit"
    assert next(row for row in _patch.gl_accounts.docs if row["code"] == "591")["normal_balance"] == "debit"
    assert next(row for row in _patch.gl_accounts.docs if row["code"] == "102")["monetary"] is True
    assert _patch.payroll_gl_mapping.docs[0]["withholding_payable_code"] == "360"
    assert {row["tenant_id"] for row in _patch.gl_accounts.docs} == {TENANT}


async def test_initialize_chart_of_accounts_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await gl.initialize_chart_of_accounts(current_user=_user("front_desk"))
    assert exc.value.status_code == 403
    assert _patch.gl_accounts.docs == []


async def test_initialize_chart_backfills_legacy_monetary_flags(_patch):
    await _mk_account("102", "Bankalar", "asset")
    _patch.gl_accounts.docs[0].pop("monetary")

    await gl.initialize_chart_of_accounts(current_user=_user("finance"))

    assert next(row for row in _patch.gl_accounts.docs if row["code"] == "102")["monetary"] is True


async def test_operational_bridge_mapping_validates_and_persists_accounts(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))

    result = await gl.update_operational_gl_mapping(
        gl.OperationalMappingIn(enabled=True),
        current_user=_user("finance"),
    )

    assert result["mapping"]["enabled"] is True
    assert result["mapping"]["receivable_account_code"] == "120"
    assert _patch.gl_operational_mappings.docs[0]["tenant_id"] == TENANT


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


async def test_year_end_close_posts_profit_and_prepares_opening_year(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))
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
    for month in range(1, 12):
        await gl.close_period(
            f"tenant-A:2026:{month:02d}",
            gl.PeriodActionIn(reason="Aylık kapanış tamamlandı"),
            current_user=_user("finance"),
        )

    result = await gl.close_fiscal_year(
        gl.YearEndCloseIn(fiscal_year=2026, reason="Yasal yıl sonu kapanışı"),
        current_user=_user("finance"),
    )

    closure = result["closure"]
    assert result["already_closed"] is False
    assert closure["net_income_minor"] == 6000
    assert closure["closing_entry_no"] == "YEV-2026-00000003"
    assert closure["opening_fiscal_year"] == 2027
    assert closure["opening_carry_forward_mode"] == "continuous_ledger"
    assert len([p for p in _patch.gl_periods.docs if p["fiscal_year"] == 2027]) == 12
    assert next(p for p in _patch.gl_periods.docs if p["id"] == "tenant-A:2026:12")["status"] == "closed"

    trial = await gl.trial_balance(as_of="2026-12-31", current_user=_user("finance"))
    balances = {row["account_code"]: row for row in trial["rows"]}
    assert balances["600"]["credit_balance_minor"] == 0
    assert balances["740"]["debit_balance_minor"] == 0
    assert balances["590"]["credit_balance_minor"] == 6000

    status = await gl.get_year_end_status(2026, current_user=_user("supervisor"))
    assert status["closed"] is True
    retry = await gl.close_fiscal_year(
        gl.YearEndCloseIn(fiscal_year=2026, reason="Tekrar güvenli kapanış"),
        current_user=_user("finance"),
    )
    assert retry["already_closed"] is True
    assert len(_patch.gl_year_end_closures.docs) == 1


async def test_year_end_requires_first_eleven_periods_closed(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))
    with pytest.raises(HTTPException) as exc:
        await gl.close_fiscal_year(
            gl.YearEndCloseIn(fiscal_year=2026, reason="Erken kapanış denemesi"),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 409
    assert "Önce" in exc.value.detail


async def test_year_end_close_posts_loss_to_contra_equity(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))
    await gl.create_journal(
        _journal(
            [{"account_code": "740", "debit": 25}, {"account_code": "100", "credit": 25}],
            date="2026-06-02",
        ),
        current_user=_user("finance"),
    )
    for month in range(1, 12):
        await gl.close_period(
            f"tenant-A:2026:{month:02d}",
            gl.PeriodActionIn(reason="Aylık kapanış tamamlandı"),
            current_user=_user("finance"),
        )

    result = await gl.close_fiscal_year(
        gl.YearEndCloseIn(fiscal_year=2026, reason="Zarar dönemi kapanışı"),
        current_user=_user("finance"),
    )
    trial = await gl.trial_balance(as_of="2026-12-31", current_user=_user("finance"))
    balances = {row["account_code"]: row for row in trial["rows"]}

    assert result["closure"]["net_income_minor"] == -2500
    assert balances["591"]["debit_balance_minor"] == 2500
    assert balances["740"]["debit_balance_minor"] == 0


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


async def test_balance_sheet_presents_contra_asset_as_negative(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))
    await gl.create_journal(
        _journal(
            [
                {"account_code": "100", "debit": 100},
                {"account_code": "257", "credit": 40},
                {"account_code": "590", "credit": 60},
            ]
        ),
        current_user=_user("finance"),
    )

    balance = await gl.balance_sheet(as_of="2026-06-30", current_user=_user("finance"))
    contra = next(row for row in balance["assets"] if row["account_code"] == "257")

    assert contra["amount"] == -40.0
    assert contra["normal_balance"] == "credit"
    assert contra["is_contra"] is True
    assert balance["totals"]["assets"] == 60.0
    assert balance["totals"]["equity"] == 60.0
    assert balance["totals"]["balanced"] is True


async def test_foreign_currency_line_requires_matching_try_value(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))
    with pytest.raises(HTTPException) as exc:
        await gl.create_journal(
            _journal(
                [
                    {
                        "account_code": "102",
                        "debit": 3000,
                        "currency": "USD",
                        "foreign_amount": 100,
                        "exchange_rate": 32,
                    },
                    {"account_code": "590", "credit": 3000},
                ]
            ),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 400
    assert "uyuşmuyor" in exc.value.detail


async def test_fx_revaluation_posts_incremental_gain(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))
    await gl.create_journal(
        _journal(
            [
                {
                    "account_code": "102",
                    "debit": 3200,
                    "currency": "USD",
                    "foreign_amount": 100,
                    "exchange_rate": 32,
                },
                {"account_code": "590", "credit": 3200},
            ]
        ),
        current_user=_user("finance"),
    )

    first = await gl.revalue_foreign_currency(
        gl.FXRevaluationIn(date="2026-06-30", currency="usd", closing_rate=33),
        current_user=_user("finance"),
    )
    second = await gl.revalue_foreign_currency(
        gl.FXRevaluationIn(date="2026-07-31", currency="USD", closing_rate=34),
        current_user=_user("finance"),
    )

    assert first["positions"][0]["difference"] == 100.0
    assert second["positions"][0]["carrying_amount"] == 3300.0
    assert second["positions"][0]["difference"] == 100.0
    assert first["entry"]["source"] == "fx_revaluation"
    assert [line["account_code"] for line in first["entry"]["lines"]] == ["102", "646"]


async def test_comparative_income_statement_and_exports(_patch):
    await gl.initialize_chart_of_accounts(current_user=_user("finance"))
    await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 50}, {"account_code": "600", "credit": 50}],
            date="2025-06-01",
        ),
        current_user=_user("finance"),
    )
    await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 100}, {"account_code": "600", "credit": 100}],
            date="2026-06-01",
        ),
        current_user=_user("finance"),
    )

    comparison = await gl.comparative_income_statement(
        start="2026-01-01",
        end="2026-12-31",
        comparison_start="2025-01-01",
        comparison_end="2025-12-31",
        current_user=_user("finance"),
    )
    xlsx = await gl.export_gl_report(
        report="trial_balance",
        format="xlsx",
        start=None,
        end=None,
        as_of="2026-12-31",
        current_user=_user("finance"),
    )
    pdf = await gl.export_gl_report(
        report="journal",
        format="pdf",
        start="2026-01-01",
        end="2026-12-31",
        as_of=None,
        current_user=_user("finance"),
    )

    assert comparison["variance"]["revenue"] == {
        "current_minor": 10000,
        "comparison_minor": 5000,
        "difference_minor": 5000,
        "percent": 100.0,
    }
    assert xlsx.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert pdf.media_type == "application/pdf"
    assert pdf.body.startswith(b"%PDF")


async def test_chain_consolidation_is_strictly_chain_scoped(_patch):
    _patch.tenants.docs.extend(
        [
            {"id": "tenant-A", "chain_id": "chain-1", "hotel_name": "Otel A"},
            {"id": "tenant-B", "chain_id": "chain-1", "hotel_name": "Otel B"},
            {"id": "tenant-X", "chain_id": "chain-2", "hotel_name": "Yabancı Otel"},
        ]
    )
    for tenant, amount in (("tenant-A", 100), ("tenant-B", 50), ("tenant-X", 999)):
        user = _user("finance", tenant=tenant)
        await _mk_account("100", "Kasa", "asset", user=user)
        await _mk_account("600", "Satış", "revenue", user=user)
        await gl.create_journal(
            _journal(
                [{"account_code": "100", "debit": amount}, {"account_code": "600", "credit": amount}],
                date="2026-06-01",
            ),
            current_user=user,
        )

    result = await gl.chain_consolidated_finance(
        start="2026-01-01",
        end="2026-12-31",
        as_of="2026-12-31",
        current_user=_user("finance", tenant="tenant-A"),
    )

    assert result["scope"] == "chain"
    assert result["property_count"] == 2
    assert {row["tenant_id"] for row in result["properties"]} == {"tenant-A", "tenant-B"}
    assert result["totals"]["revenue"]["amount"] == 150.0
    assert result["consolidation"]["intercompany_eliminations_applied"] is False


async def test_chain_consolidation_applies_balanced_intercompany_rules(_patch):
    _patch.tenants.docs.extend(
        [
            {"id": "tenant-A", "chain_id": "chain-1", "property_name": "Otel A", "is_chain_headquarters": True},
            {"id": "tenant-B", "chain_id": "chain-1", "property_name": "Otel B"},
        ]
    )
    _patch.hotel_chains.docs.append({"id": "chain-1", "name": "Test Zinciri", "headquarters_tenant_id": "tenant-A"})
    for code, name, account_type in (("120", "Grup İçi Alıcı", "asset"), ("600", "Grup İçi Gelir", "revenue")):
        await _mk_account(code, name, account_type, user=_user("admin", tenant="tenant-A"))
    for code, name, account_type in (("320", "Grup İçi Satıcı", "liability"), ("740", "Grup İçi Gider", "expense")):
        await _mk_account(code, name, account_type, user=_user("admin", tenant="tenant-B"))
    await gl.create_journal(
        _journal(
            [{"account_code": "120", "debit": 100}, {"account_code": "600", "credit": 100}],
            date="2026-06-01",
        ),
        current_user=_user("finance", tenant="tenant-A"),
    )
    await gl.create_journal(
        _journal(
            [{"account_code": "740", "debit": 100}, {"account_code": "320", "credit": 100}],
            date="2026-06-01",
        ),
        current_user=_user("finance", tenant="tenant-B"),
    )
    admin = _user("admin", tenant="tenant-A")
    await gl.create_intercompany_rule(
        gl.IntercompanyRuleIn(
            name="Grup içi cari",
            kind="balance",
            tenant_a_id="tenant-A",
            account_a_code="120",
            tenant_b_id="tenant-B",
            account_b_code="320",
        ),
        current_user=admin,
    )
    await gl.create_intercompany_rule(
        gl.IntercompanyRuleIn(
            name="Grup içi hizmet",
            kind="income",
            tenant_a_id="tenant-A",
            account_a_code="600",
            tenant_b_id="tenant-B",
            account_b_code="740",
        ),
        current_user=admin,
    )

    result = await gl.chain_consolidated_finance(
        start="2026-01-01",
        end="2026-12-31",
        as_of="2026-12-31",
        current_user=_user("finance", tenant="tenant-B"),
    )

    assert result["raw_totals"]["revenue"]["amount"] == 100.0
    assert result["raw_totals"]["assets"]["amount"] == 100.0
    assert result["totals"]["revenue"]["amount"] == 0.0
    assert result["totals"]["expenses"]["amount"] == 0.0
    assert result["totals"]["assets"]["amount"] == 0.0
    assert result["totals"]["liabilities"]["amount"] == 0.0
    assert result["consolidation"]["mode"] == "eliminated"
    assert result["consolidation"]["applied_rule_count"] == 2


async def test_intercompany_rule_write_is_headquarters_and_chain_scoped(_patch):
    _patch.tenants.docs.extend(
        [
            {"id": "tenant-A", "chain_id": "chain-1", "is_chain_headquarters": True},
            {"id": "tenant-B", "chain_id": "chain-1"},
            {"id": "tenant-X", "chain_id": "chain-2"},
        ]
    )
    _patch.hotel_chains.docs.extend(
        [
            {"id": "chain-1", "headquarters_tenant_id": "tenant-A"},
            {"id": "chain-2", "headquarters_tenant_id": "tenant-X"},
        ]
    )
    await _mk_account("120", "Alıcı", "asset", user=_user("admin", tenant="tenant-A"))
    await _mk_account("320", "Satıcı", "liability", user=_user("admin", tenant="tenant-B"))
    await _mk_account("320", "Yabancı Satıcı", "liability", user=_user("admin", tenant="tenant-X"))

    payload = gl.IntercompanyRuleIn(
        name="Yetki testi",
        kind="balance",
        tenant_a_id="tenant-A",
        account_a_code="120",
        tenant_b_id="tenant-B",
        account_b_code="320",
    )
    with pytest.raises(HTTPException) as non_hq:
        await gl.create_intercompany_rule(payload, current_user=_user("admin", tenant="tenant-B"))
    assert non_hq.value.status_code == 403

    cross_chain = payload.model_copy(update={"tenant_b_id": "tenant-X"})
    with pytest.raises(HTTPException) as foreign_member:
        await gl.create_intercompany_rule(cross_chain, current_user=_user("admin", tenant="tenant-A"))
    assert foreign_member.value.status_code == 400


async def test_eledger_preflight_and_source_package_are_honestly_labelled(_patch):
    await _mk_account("100", "Kasa", "asset")
    await _mk_account("600", "Satış", "revenue")
    await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 250}, {"account_code": "600", "credit": 250}],
            date="2026-06-15",
        ),
        current_user=_user("finance"),
    )
    await _patch.gl_periods.update_one(
        {"tenant_id": TENANT, "fiscal_year": 2026, "period_no": 6},
        {"$set": {"status": "closed"}, "$setOnInsert": {"id": "period-6"}},
        upsert=True,
    )
    await gl.update_eledger_settings(
        gl.ELedgerSettingsIn(
            taxpayer_id="1234567890",
            legal_name="Syroce Test Oteli AŞ",
            source_application="Syroce PMS",
            source_application_version="2026.08",
            software_approval_reference=None,
        ),
        current_user=_user("admin"),
    )

    preflight = await gl.eledger_preflight(period="2026-06", current_user=_user("finance"))
    assert preflight["blockers"] == []
    response = await gl.download_eledger_source_package(period="2026-06", current_user=_user("finance"))

    assert preflight["ready_for_source_export"] is True
    assert preflight["official_edefter"] is False
    assert preflight["entry_count"] == 1
    assert preflight["warnings"][0]["code"] == "software_approval_unverified"
    assert response.media_type == "application/zip"
    assert response.headers["x-syroce-official-edefter"] == "false"
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert set(archive.namelist()) == {"journal.csv", "general_ledger.csv", "README.txt", "manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["official_edefter"] is False
        assert manifest["entry_count"] == 1
        assert manifest["files"]["journal.csv"]["sha256"]


async def test_eledger_preflight_blocks_unexplained_journal_sequence_gap(_patch):
    await _mk_account("100", "Kasa", "asset")
    await _mk_account("600", "Satış", "revenue")
    for amount in (10, 20, 30):
        await gl.create_journal(
            _journal(
                [{"account_code": "100", "debit": amount}, {"account_code": "600", "credit": amount}],
                date="2026-07-15",
            ),
            current_user=_user("finance"),
        )
    _patch.gl_journal_entries.docs = [item for item in _patch.gl_journal_entries.docs if item.get("posting_sequence") != 2]
    _patch.gl_sequence_reservations.docs = [item for item in _patch.gl_sequence_reservations.docs if item.get("sequence") != 2]
    await _patch.gl_periods.update_one(
        {"tenant_id": TENANT, "fiscal_year": 2026, "period_no": 7},
        {"$set": {"status": "closed"}},
    )
    await gl.update_eledger_settings(
        gl.ELedgerSettingsIn(
            taxpayer_id="1234567890",
            legal_name="Syroce Test Oteli AŞ",
            source_application_version="2026.08",
        ),
        current_user=_user("admin"),
    )

    preflight = await gl.eledger_preflight(period="2026-07", current_user=_user("finance"))

    gap = next(item for item in preflight["blockers"] if item["code"] == "unexplained_sequence_gap")
    assert gap["sequence_numbers"] == [2]
    assert preflight["ready_for_source_export"] is False


async def test_eledger_preflight_blocks_tampered_or_unsealed_entries(_patch):
    await _mk_account("100", "Kasa", "asset")
    await _mk_account("600", "Satış", "revenue")
    await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 25}, {"account_code": "600", "credit": 25}],
            date="2026-08-15",
        ),
        current_user=_user("finance"),
    )
    await _patch.gl_periods.update_one(
        {"tenant_id": TENANT, "fiscal_year": 2026, "period_no": 8},
        {"$set": {"status": "closed"}, "$setOnInsert": {"id": "period-8"}},
        upsert=True,
    )
    await gl.update_eledger_settings(
        gl.ELedgerSettingsIn(
            taxpayer_id="1234567890",
            legal_name="Syroce Test Oteli AŞ",
            source_application_version="2026.08",
        ),
        current_user=_user("admin"),
    )

    _patch.gl_journal_entries.docs[0]["memo"] = "mühür sonrası değişiklik"
    tampered = await gl.eledger_preflight(period="2026-08", current_user=_user("finance"))
    assert {item["code"] for item in tampered["blockers"]} >= {"journal_integrity_mismatch"}

    _patch.gl_journal_entries.docs[0].pop("entry_hash")
    unsealed = await gl.eledger_preflight(period="2026-08", current_user=_user("finance"))
    assert {item["code"] for item in unsealed["blockers"]} >= {"legacy_unsealed_entry"}
    assert unsealed["official_edefter"] is False


# ---------------------------------------------------------------------------
# Voucher lifecycle + tamper-evident journal chain
# ---------------------------------------------------------------------------
def _voucher_payload(amount=100, *, date="2026-08-10"):
    return gl.VoucherCreateIn(
        date=date,
        voucher_type="mahsup",
        memo="Kontrollü manuel mahsup",
        lines=[
            gl.JournalLineIn(account_code="100", debit=amount),
            gl.JournalLineIn(account_code="600", credit=amount),
        ],
    )


async def test_voucher_requires_maker_checker_before_posting(_patch):
    await _seed_basic_coa()
    maker = _user("finance", user_id="maker")
    approver = _user("finance", user_id="approver")

    created = await gl.create_voucher(_voucher_payload(), current_user=maker)
    voucher = created["voucher"]
    assert voucher["status"] == "draft"
    assert _patch.gl_journal_entries.docs == []

    submitted = await gl.submit_voucher(
        voucher["id"],
        gl.VoucherActionIn(reason="Belgeler kontrol için hazır"),
        current_user=maker,
    )
    assert submitted["voucher"]["status"] == "submitted"

    with pytest.raises(HTTPException) as exc:
        await gl.approve_voucher(
            voucher["id"],
            gl.VoucherActionIn(reason="Kendi kaydımı onaylıyorum"),
            current_user=maker,
        )
    assert exc.value.status_code == 409
    assert "hazırlayan" in exc.value.detail

    approved = await gl.approve_voucher(
        voucher["id"],
        gl.VoucherActionIn(reason="Borç alacak ve belge kontrol edildi"),
        current_user=approver,
    )
    assert approved["voucher"]["status"] == "approved"

    posted = await gl.post_approved_voucher(voucher["id"], current_user=approver)
    assert posted["voucher"]["status"] == "posted"
    assert posted["entry"]["source"] == "manual_voucher"
    assert posted["entry"]["entry_hash"]
    assert posted["entry"]["previous_entry_hash"] == gl.INTEGRITY_GENESIS

    replay = await gl.post_approved_voucher(voucher["id"], current_user=approver)
    assert replay["already_posted"] is True
    assert replay["entry"]["id"] == posted["entry"]["id"]
    assert len(_patch.gl_journal_entries.docs) == 1


async def test_voucher_numbers_are_monotonic_and_cancelled_numbers_remain_auditable(_patch):
    await _seed_basic_coa()
    maker = _user("finance", user_id="maker")
    first = (await gl.create_voucher(_voucher_payload(date="2026-02-01"), current_user=maker))["voucher"]
    second = (await gl.create_voucher(_voucher_payload(date="2026-02-02"), current_user=maker))["voucher"]
    next_year = (await gl.create_voucher(_voucher_payload(date="2027-01-02"), current_user=maker))["voucher"]

    assert first["voucher_no"] == "MF-2026-00000001"
    assert second["voucher_no"] == "MF-2026-00000002"
    assert next_year["voucher_no"] == "MF-2027-00000001"
    await gl.cancel_voucher(
        first["id"],
        gl.VoucherActionIn(reason="Belge iptal edildi"),
        current_user=maker,
    )
    cancelled = await gl.get_voucher(first["id"], current_user=maker)
    assert cancelled["voucher"]["status"] == "cancelled"
    assert cancelled["voucher"]["voucher_no"] == "MF-2026-00000001"


async def test_voucher_counter_repairs_legacy_counter_without_tenant_metadata(_patch):
    """A pre-tenant counter must continue from its existing ordinal.

    Querying it with both `_id` and `tenant_id` would miss the legacy document
    and cause Mongo's upsert to fail on the already occupied `_id`.
    """
    await _seed_basic_coa()
    legacy_id = f"gl-voucher-counter:{TENANT}:2026"
    _patch.gl_counters.docs.append({"_id": legacy_id, "value": 1})

    created = await gl.create_voucher(_voucher_payload(date="2026-02-01"), current_user=_user("finance"))

    assert created["voucher"]["voucher_no"] == "MF-2026-00000002"
    repaired = _patch.gl_counters.docs[0]
    assert repaired["tenant_id"] == TENANT
    assert repaired["fiscal_year"] == 2026
    assert repaired["counter_type"] == "voucher"


async def test_foreign_currency_voucher_can_be_created(_patch):
    await _seed_basic_coa()

    created = await gl.create_voucher(
        gl.VoucherCreateIn(
            date="2026-09-03",
            voucher_type="mahsup",
            memo="USD fiş oluşturma denetimi",
            lines=[
                gl.JournalLineIn(account_code="100", debit=4000, currency="USD", foreign_amount=100, exchange_rate=40),
                gl.JournalLineIn(account_code="600", credit=4000, currency="USD", foreign_amount=100, exchange_rate=40),
            ],
        ),
        current_user=_user("finance"),
    )

    assert created["voucher"]["status"] == "draft"
    assert created["voucher"]["total_debit"] == 4000.0
    assert created["voucher"]["lines"][0]["currency"] == "USD"
    assert created["voucher"]["lines"][0]["foreign_amount"] == 100.0


async def test_rejected_voucher_can_be_revised_with_optimistic_version(_patch):
    await _seed_basic_coa()
    maker = _user("finance", user_id="maker")
    reviewer = _user("finance", user_id="reviewer")
    voucher = (await gl.create_voucher(_voucher_payload(), current_user=maker))["voucher"]
    await gl.submit_voucher(
        voucher["id"],
        gl.VoucherActionIn(reason="İncelemeye sunuldu"),
        current_user=maker,
    )
    rejected = await gl.reject_voucher(
        voucher["id"],
        gl.VoucherActionIn(reason="Açıklama destekleyici belgeyle uyuşmuyor"),
        current_user=reviewer,
    )
    rejected_version = rejected["voucher"]["version"]
    update_payload = gl.VoucherUpdateIn(
        **_voucher_payload(amount=125).model_dump(),
        version=rejected_version,
    )
    updated = await gl.update_voucher(voucher["id"], update_payload, current_user=maker)
    assert updated["voucher"]["status"] == "draft"
    assert updated["voucher"]["total_debit"] == 125.0
    assert updated["voucher"]["revisions"][0]["status"] == "rejected"

    with pytest.raises(HTTPException) as exc:
        await gl.update_voucher(voucher["id"], update_payload, current_user=maker)
    assert exc.value.status_code == 409


async def test_integrity_audit_detects_journal_tampering_and_legacy_rows(_patch):
    await _seed_basic_coa()
    first = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 10}, {"account_code": "600", "credit": 10}]),
        current_user=_user("finance"),
    )
    second = await gl.create_journal(
        _journal([{"account_code": "100", "debit": 20}, {"account_code": "600", "credit": 20}]),
        current_user=_user("finance"),
    )
    assert second["entry"]["previous_entry_hash"] == first["entry"]["entry_hash"]

    healthy = await gl.journal_integrity_audit(fiscal_year=2026, current_user=_user("finance"))
    assert healthy["healthy"] is True
    assert healthy["fully_sealed"] is True
    assert healthy["counts"]["sealed"] == 2

    _patch.gl_journal_entries.docs[1]["lines"][0]["debit"] = 999.0
    broken = await gl.journal_integrity_audit(fiscal_year=2026, current_user=_user("finance"))
    assert broken["healthy"] is False
    assert {issue["code"] for issue in broken["issues"]} >= {"entry_hash_mismatch"}

    _patch.gl_journal_entries.docs[1]["lines"][0]["debit"] = 20.0
    _patch.gl_journal_entries.docs[0].pop("entry_hash")
    legacy = await gl.journal_integrity_audit(fiscal_year=2026, current_user=_user("finance"))
    assert legacy["fully_sealed"] is False
    assert legacy["counts"]["legacy_unsealed"] == 1


async def test_public_direct_manual_journal_route_is_retired(_patch):
    with pytest.raises(HTTPException) as exc:
        await gl.reject_legacy_manual_journal(current_user=_user("finance"))
    assert exc.value.status_code == 410
    assert "Taslak fiş" in exc.value.detail


async def test_period_close_blocks_pending_vouchers_then_allows_cancelled_draft(_patch):
    await _seed_basic_coa()
    await gl.initialize_periods(gl.FiscalYearIn(fiscal_year=2026), current_user=_user("finance"))
    maker = _user("finance", user_id="maker")
    voucher = (await gl.create_voucher(_voucher_payload(date="2026-01-10"), current_user=maker))["voucher"]

    with pytest.raises(HTTPException) as exc:
        await gl.close_period(
            "tenant-A:2026:01",
            gl.PeriodActionIn(reason="Ocak kapanışı"),
            current_user=_user("finance", user_id="closer"),
        )
    assert exc.value.status_code == 409
    assert voucher["voucher_no"] in exc.value.detail

    await gl.cancel_voucher(
        voucher["id"],
        gl.VoucherActionIn(reason="Hatalı taslak iptal edildi"),
        current_user=maker,
    )
    closed = await gl.close_period(
        "tenant-A:2026:01",
        gl.PeriodActionIn(reason="Ocak kapanışı"),
        current_user=_user("finance", user_id="closer"),
    )
    assert closed["period"]["status"] == "closed"


async def test_period_close_fails_when_journal_integrity_is_broken(_patch):
    await _seed_basic_coa()
    await gl.initialize_periods(gl.FiscalYearIn(fiscal_year=2026), current_user=_user("finance"))
    await gl.create_journal(
        _journal(
            [{"account_code": "100", "debit": 50}, {"account_code": "600", "credit": 50}],
            date="2026-01-05",
        ),
        current_user=_user("finance"),
    )
    _patch.gl_journal_entries.docs[0]["memo"] = "sonradan değiştirildi"

    with pytest.raises(HTTPException) as exc:
        await gl.close_period(
            "tenant-A:2026:01",
            gl.PeriodActionIn(reason="Ocak kapanışı"),
            current_user=_user("finance"),
        )
    assert exc.value.status_code == 409
    assert "bütünlük" in exc.value.detail
