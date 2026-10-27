"""Cent-exact settlement, refund, replay and transactional audit contract."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import audit_chain
from domains.pms import enterprise_router as router
from domains.pms.pos_fnb.daily_closure import preview, summarize
from tests.test_pos_final_consistency_replica import db  # noqa: F401


def sale(**values):
    return {"id": "s", "status": "completed", "total_amount": "120.00", "tip_amount": "10.00",
            "payment_method": "cash", "currency": "TRY", **values}


def test_refunds_mixed_tenders_tips_and_duplicate_sources():
    s = sale(payment_method="mixed", payment_breakdown=[{"method": "cash", "amount": 40}, {"method": "card", "amount": 80}])
    r = sale(id="r", status="refunded", total_amount=-60, tip_amount=-5, payment_method="mixed",
             payment_breakdown=[{"method": "cash", "amount": -20}, {"method": "card", "amount": -40}])
    result = summarize([s, deepcopy(s), r, sale(id="room", total_amount=30, tip_amount=0, payment_method="room_charge"), sale(status="open")])
    assert result["total_sales"] == 90 and result["net_sales"] == 85 and result["tips"] == 5
    assert result["cash_sales"] == 20 and result["card_sales"] == 40
    assert result["other_sales"] == result["room_charge_sales"] == 30
    assert result["collected_total"] == 60 and result["refund_total"] == 60
    assert result["transaction_count"] == 3 and result["refund_count"] == 1


def test_mixed_native_currencies_never_add_or_convert():
    result = summarize([sale(currency="USD"), sale(id="eur", currency="EUR", total_amount=50, tip_amount=0)])
    assert result["currency"] is result["total_sales"] is result["net_sales"] is None
    assert result["totals_by_currency"]["USD"]["net_sales"] == 110
    assert result["totals_by_currency"]["EUR"]["net_sales"] == 50


@pytest.mark.parametrize("value", ["NaN", "Infinity", -1, None, "not-money"])
def test_invalid_money_fails_closed(value):
    with pytest.raises(ValueError, match="INVALID_POS_MONETARY_VALUE"):
        summarize([sale(total_amount=value)])


@pytest.mark.parametrize("values,code", [
    ({"id": None}, "MISSING_POS_TRANSACTION_ID"), ({"currency": None}, "MISSING_POS_CURRENCY"),
    ({"payment_method": "mixed"}, "MISSING_POS_PAYMENT_BREAKDOWN"),
    ({"payment_breakdown": [{"method": "card", "amount": 119}]}, "UNBALANCED_POS_PAYMENT_BREAKDOWN"),
    ({"payment_breakdown": [{"method": "cash", "amount": -120}]}, "INVALID_POS_PAYMENT_BREAKDOWN"),
    ({"status": "refunded"}, "INVALID_POS_MONETARY_VALUE"),
])
def test_incomplete_source_fails_closed(values, code):
    with pytest.raises(ValueError, match=code):
        summarize([sale(**values)])


def test_conflicting_duplicate_and_penny_conservation():
    with pytest.raises(ValueError, match="CONFLICTING"):
        summarize([sale(), sale(total_amount=119)])
    rows = [sale(id=str(i), total_amount='.01', tip_amount=0) for i in range(100)]
    assert summarize(rows)["total_sales"] == 1


async def seed(database, monkeypatch):
    monkeypatch.setattr(router, "db", database)
    monkeypatch.setattr(audit_chain, "_system_db", lambda: database)
    for name in ("pos_closures", "pos_closure_locks", "audit_logs", "audit_chain_state"):
        await database.create_collection(name)
    await database.pos_transactions.insert_one({**sale(), "tenant_id": "t", "transaction_date": "2026-10-18"})
    return SimpleNamespace(tenant_id="t", id="manager")


async def request(database):
    p = await preview(database, 't', '2026-10-18')
    return router.POSClosureRequest(business_date="2026-10-18", expected_preview_hash=p["preview_hash"], reason="Kaynakları inceledim")


@pytest.mark.asyncio
async def test_atomic_closure_and_concurrent_replay(db, monkeypatch):
    user = await seed(db, monkeypatch)
    data = await request(db)
    results = await asyncio.gather(*(router.create_pos_closure(data, current_user=user, _perm=True) for _ in range(8)))
    assert sorted(r['replayed'] for r in results) == [False] + [True] * 7
    assert all(r['net_sales'] == 110 and r['tips'] == 10 for r in results)
    assert await db.pos_closures.count_documents({}) == await db.audit_logs.count_documents({'action': 'pos.daily_closure'}) == 1
    event = await db.audit_logs.find_one({'action': 'pos.daily_closure'})
    assert event['actor_id'] == 'manager' and event['record_hash'] and event['after_snapshot']['preview_hash'] == data.expected_preview_hash
    assert (await audit_chain.verify_chain('t'))['ok']


@pytest.mark.asyncio
async def test_source_drift_never_replays_or_rewrites_sealed_snapshot(db, monkeypatch):
    user = await seed(db, monkeypatch)
    old = await request(db)
    saved = await router.create_pos_closure(old, current_user=user, _perm=True)
    await db.pos_transactions.update_one({'id': 's'}, {'$set': {'total_amount': 121}})
    for data in (old, await request(db)):
        with pytest.raises(HTTPException) as exc:
            await router.create_pos_closure(data, current_user=user, _perm=True)
        assert exc.value.status_code == 409
    assert (await db.pos_closures.find_one({}))['total_sales'] == saved['total_sales']


@pytest.mark.asyncio
async def test_historical_requires_real_completed_night_audit(db, monkeypatch):
    user = await seed(db, monkeypatch)
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-19'}})
    data = await request(db)
    with pytest.raises(HTTPException) as exc:
        await router.create_pos_closure(data, current_user=user, _perm=True)
    assert exc.value.status_code == 409
    await db.night_audit_runs.insert_one({'tenant_id': 't', 'business_date': '2026-10-18', 'status': 'completed', 'dry_run': False})
    result = await router.create_pos_closure(data, current_user=user, _perm=True)
    assert result['is_historical_snapshot'] and result['closure_date'] == '2026-10-18'
    assert (await db.tenant_settings.find_one({'tenant_id': 't'}))['business_date'] == '2026-10-19'


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_closure(db, monkeypatch):
    user = await seed(db, monkeypatch)
    data = await request(db)
    async def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(router, 'log_chained_audit_event', fail)
    with pytest.raises(RuntimeError, match='audit unavailable'):
        await router.create_pos_closure(data, current_user=user, _perm=True)
    assert await db.pos_closures.count_documents({}) == 0


@pytest.mark.asyncio
async def test_open_checks_future_day_and_legacy_record_are_not_closed(db, monkeypatch):
    user = await seed(db, monkeypatch)
    data = await request(db)
    await db.pos_orders.insert_one({'id': 'open', 'tenant_id': 't', 'business_date': '2026-10-18', 'status': 'open'})
    with pytest.raises(HTTPException):
        await router.create_pos_closure(data, current_user=user, _perm=True)
    await db.pos_orders.delete_one({'id': 'open'})
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-17'}})
    with pytest.raises(HTTPException):
        await router.create_pos_closure(data, current_user=user, _perm=True)
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-18'}})
    await db.pos_closures.insert_one({'tenant_id': 't', 'closure_date': '2026-10-18', 'total_sales': 5420.5})
    with pytest.raises(HTTPException):
        await router.create_pos_closure(data, current_user=user, _perm=True)
    assert (await db.pos_closures.find_one({}))['total_sales'] == 5420.5


@pytest.mark.asyncio
async def test_canonical_sources_are_deduplicated_and_other_tenant_excluded(db, monkeypatch):
    await seed(db, monkeypatch)
    copy = await db.pos_transactions.find_one({'id': 's'}, {'_id': 0})
    await db.pos_menu_transactions.insert_one(copy)
    await db.pos_transactions.insert_one({**sale(id='private', total_amount=999), 'tenant_id': 'other', 'transaction_date': '2026-10-18'})
    p = await preview(db, 't', '2026-10-18')
    assert p['transaction_count'] == 1 and p['total_sales'] == 120
    await db.pos_menu_transactions.update_one({'id': 's'}, {'$set': {'total_amount': 121}})
    with pytest.raises(ValueError, match='CONFLICTING_POS_TRANSACTION'):
        await preview(db, 't', '2026-10-18')
