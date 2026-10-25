import asyncio
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from modules.pms_core import account_projection_repair as repair
from routers import reservation_detail as router

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(id="admin", name="Operator", role="admin", tenant_id="A")


@pytest.fixture(autouse=True)
def isolated_chain(monkeypatch, ledger_db):
    from core import audit_chain
    monkeypatch.setattr(audit_chain, "_system_db", lambda: ledger_db)
    monkeypatch.setattr(repair, "invalidate_receivable_report_caches", lambda *_: None)


def account(**extra):
    return {"id": "a", "tenant_id": "A", "balance": 4501, "current_balance": 4501, "currency": "TRY", **extra}


def tx(**extra):
    return {"id": "t", "tenant_id": "A", "cari_account_id": "a", "transaction_type": "charge", "amount": 4503, **extra}


def payload(preview, **extra):
    return router.AccountProjectionRepair(request_id=extra.pop("request_id", uuid4()), source_fingerprint=preview["source_fingerprint"],
        reason="Kaynak hareketleri incelendi; yalnız türetilmiş bakiye yenileniyor.",
        source_review_reference="İncelenen tarihsel cari hareketleri ve kaynak dökümü", confirm_sources_authoritative=True, **extra)


def preview(acc, rows):
    return repair.projection_preview(acc, rows, source="cari_accounts", fallback_currency="TRY")


def test_exact_legacy_2tl_projection_difference_preserves_sources_and_negative_customer_credit():
    acc, rows = account(), [tx()]
    before = deepcopy((acc, rows))
    result = preview(acc, rows)
    assert result["source_balance"] == 4503 and result["needs_repair"] and result["repairable"]
    assert (acc, rows) == before
    credit = preview(account(balance=0, current_balance=0), [tx(transaction_type="payment", amount=1)])
    assert credit["source_balance"] == -1 and credit["repairable"]


@pytest.mark.parametrize("rows,reason", [([], "source_history_missing"), ([tx(status="pending")], "uncommitted_source"),
    ([tx(currency="EUR")], "mixed_currency_sources"), ([tx(), tx()], "missing_or_duplicate_source_identity"),
    ([tx(amount="NaN")], "invalid_account_source"), ([tx(amount=-1)], "invalid_source_amount_or_type"),
    ([tx(amount="1e100")], "invalid_account_source"),
    ([tx(transaction_type="mystery")], "invalid_source_amount_or_type")])
def test_uncertain_sources_block_repair(rows, reason):
    result = preview(account(), rows)
    assert reason in result["blocked_reasons"] and not result["repairable"]


def test_fingerprint_is_order_independent_but_every_source_change_requires_review():
    rows = [tx(), tx(id="p", transaction_type="payment", amount=1)]
    first = preview(account(), rows)
    assert first["source_fingerprint"] == preview(account(), list(reversed(rows)))["source_fingerprint"]
    rows[1]["amount"] = 2
    assert first["source_fingerprint"] != preview(account(), rows)["source_fingerprint"]


def test_no_sources_cannot_be_relabelled_as_opening_balance_implicitly():
    assert not preview(account(), [tx(voided=True)])["repairable"]
    assert preview(account(opening_balance=4503), [])["source_balance"] == 4503


@pytest.mark.parametrize("bad", [{"confirm_sources_authoritative": False}, {"reason": "          "}, {"source_review_reference": "  "}, {"amount": 0}])
def test_source_review_is_explicit_and_no_caller_chosen_balance(bad):
    data = payload(preview(account(), [tx()])).model_dump()
    data.update(bad)
    with pytest.raises(ValidationError):
        router.AccountProjectionRepair(**data)


async def seed(database, source="cari_accounts"):
    await database[source].insert_one(account())
    field = repair.SOURCES[source][1]
    await database[repair.SOURCES[source][0]].insert_one(tx(**{field: "a"}))
    _, p = await repair.load_projection_preview(database, "A", source, "a", fallback_currency="TRY")
    return p


@pytest.mark.parametrize("source", list(repair.SOURCES))
async def test_real_mongo_atomic_repair_and_replay_never_add_payments_or_rewrite_history(ledger_db, source):
    p = await seed(ledger_db, source)
    collection = ledger_db[repair.SOURCES[source][0]]
    sources = await collection.find({}).to_list(None)
    data = payload(p)
    result = await repair.repair_projection(ledger_db, ledger_db.client, USER, source, "a", data, fallback_currency="TRY")
    assert result["new_balance"] == 4503 and not result["replayed"]
    assert (await ledger_db[source].find_one({"id": "a"}))["current_balance"] == 4503
    assert await collection.find({}).to_list(None) == sources
    assert await ledger_db.payments.count_documents({}) == 0 and await ledger_db.gl_journal_entries.count_documents({}) == 0
    entry = await ledger_db.audit_logs.find_one({"action": "account_projection_rebuilt"})
    assert entry["metadata"]["cached_balances"]["balance"] == 4501
    assert entry["metadata"]["source_balance"] == 4503
    assert entry["metadata"]["reason"] == data.reason and entry["actor_id"] == USER.id
    from core.audit_chain import compute_record_hash
    assert entry["record_hash"] == compute_record_hash(entry, entry["seq"], entry["prev_hash"])
    tampered = deepcopy(entry)
    tampered["after_snapshot"]["reason"] = "tampered explanation"
    assert entry["record_hash"] != compute_record_hash(tampered, entry["seq"], entry["prev_hash"])
    again = await repair.repair_projection(ledger_db, ledger_db.client, USER, source, "a", data, fallback_currency="TRY")
    assert again["replayed"] and await ledger_db.audit_logs.count_documents({}) == 1
    changed = data.model_copy(update={"reason": "Farklı içerik yeniden uygulanamaz"})
    with pytest.raises(HTTPException) as error:
        await repair.repair_projection(ledger_db, ledger_db.client, USER, source, "a", changed, fallback_currency="TRY")
    assert error.value.status_code == 409


async def test_real_mongo_stale_preview_and_wrong_tenant_are_rejected(ledger_db):
    p = await seed(ledger_db)
    await ledger_db.cari_transactions.insert_one(tx(id="later", amount=1))
    with pytest.raises(HTTPException) as error:
        await repair.repair_projection(ledger_db, ledger_db.client, USER, "cari_accounts", "a", payload(p), fallback_currency="TRY")
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await repair.load_projection_preview(ledger_db, "B", "cari_accounts", "a", fallback_currency="TRY")
    assert error.value.status_code == 404
    assert (await ledger_db.cari_accounts.find_one({"id": "a"}))["balance"] == 4501


@pytest.mark.parametrize("other_source", ["cari_accounts", "city_ledger_accounts"])
async def test_real_mongo_ambiguous_account_identity_cannot_be_rebuilt(ledger_db, other_source):
    await seed(ledger_db)
    await ledger_db[other_source].insert_one(account())
    with pytest.raises(HTTPException) as error:
        await repair.load_projection_preview(ledger_db, "A", "cari_accounts", "a", fallback_currency="TRY")
    assert error.value.status_code == 409


async def test_real_mongo_city_ledger_credit_is_preserved_as_negative_not_clamped_to_zero(ledger_db):
    source = "city_ledger_accounts"
    await ledger_db[source].insert_one(account(balance=0, current_balance=0))
    await ledger_db.city_ledger_transactions.insert_one(tx(account_id="a", transaction_type="payment", amount=1))
    _, p = await repair.load_projection_preview(ledger_db, "A", source, "a", fallback_currency="TRY")
    result = await repair.repair_projection(ledger_db, ledger_db.client, USER, source, "a", payload(p), fallback_currency="TRY")
    assert result["new_balance"] == -1
    assert (await ledger_db[source].find_one({"id": "a"}))["current_balance"] == -1
    from datetime import date
    from modules.pms_core.cari_receivable_reporting import load_account_positions
    _, failed, issues = await load_account_positions(ledger_db, "A", fallback_currency="TRY", today=date(2026, 10, 24))
    assert not failed and not issues


async def test_real_mongo_audit_failure_aborts_balance_and_receipt(ledger_db, monkeypatch):
    p = await seed(ledger_db)
    async def fail(*args, **kwargs):
        raise RuntimeError("injected immutable audit failure")
    monkeypatch.setattr(repair, "append_audit_log", fail)
    with pytest.raises(RuntimeError):
        await repair.repair_projection(ledger_db, ledger_db.client, USER, "cari_accounts", "a", payload(p), fallback_currency="TRY")
    assert (await ledger_db.cari_accounts.find_one({"id": "a"}))["balance"] == 4501
    assert await ledger_db.account_projection_repairs.count_documents({}) == 0


async def test_real_mongo_chain_link_failure_cannot_commit_unchained_repair(ledger_db, monkeypatch):
    from core import audit_chain
    p = await seed(ledger_db)
    async def fail(*args, **kwargs):
        raise RuntimeError("chain state unavailable")
    monkeypatch.setattr(audit_chain, "_link_chain", fail)
    with pytest.raises(RuntimeError, match="chain state unavailable"):
        await repair.repair_projection(ledger_db, ledger_db.client, USER, "cari_accounts", "a", payload(p), fallback_currency="TRY")
    assert (await ledger_db.cari_accounts.find_one({"id": "a"}))["balance"] == 4501
    assert await ledger_db.account_projection_repairs.count_documents({}) == 0
    assert await ledger_db.audit_logs.count_documents({}) == 0


async def test_real_mongo_same_payload_concurrently_commits_exactly_once(ledger_db):
    p = await seed(ledger_db)
    data = payload(p)
    results = await asyncio.gather(*[repair.repair_projection(ledger_db, ledger_db.client, USER, "cari_accounts", "a", data, fallback_currency="TRY") for _ in range(2)])
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert await ledger_db.account_projection_repairs.count_documents({}) == 1
    assert await ledger_db.audit_logs.count_documents({}) == 1


async def test_real_mongo_post_commit_cache_failure_never_obscures_durable_success(ledger_db, monkeypatch):
    p = await seed(ledger_db)
    def fail(_tenant):
        raise RuntimeError("injected cache failure")
    monkeypatch.setattr(repair, "invalidate_receivable_report_caches", fail)
    result = await repair.repair_projection(ledger_db, ledger_db.client, USER, "cari_accounts", "a", payload(p), fallback_currency="TRY")
    assert result["success"] and result["new_balance"] == 4503
    assert await ledger_db.account_projection_repairs.count_documents({}) == 1


def test_receivable_cache_invalidation_is_tenant_scoped_and_includes_role_variants(monkeypatch):
    from core import report_cache
    from unittest.mock import Mock
    cache = Mock()
    monkeypatch.setattr(report_cache, "cache", cache)
    report_cache.invalidate_receivable_report_caches("A")
    assert cache.invalidate_tenant_cache.call_count == 2
    for prefix in report_cache.RECEIVABLE_REPORT_CACHE_PREFIXES:
        cache.invalidate_tenant_cache.assert_any_call("A", prefix, include_role_variants=True)


async def test_financial_permission_and_admin_permission_required_before_database_access(monkeypatch):
    calls = []
    def enforce(user, op):
        calls.append(op)
        if op == "manage_night_audit":
            raise HTTPException(403, "forbidden")
    monkeypatch.setattr(router, "_enforce_perm", enforce)
    with pytest.raises(HTTPException) as error:
        await router.repair_account_projection("cari_accounts", "a", payload(preview(account(), [tx()])), current_user=USER)
    assert error.value.status_code == 403 and calls == ["manage_city_ledger", "manage_night_audit"]
