from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.integrations import operational_gl_bridge as bridge


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


def _collection(*, one=None, rows=None):
    return SimpleNamespace(
        find_one=AsyncMock(return_value=one),
        find=Mock(return_value=_Cursor(rows or [])),
        update_one=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_night_audit_bridge_posts_daily_accrual_and_collections(monkeypatch):
    mapping = {**bridge.DEFAULT_MAPPING, "tenant_id": "tenant-a", "enabled": True}
    database = SimpleNamespace(
        gl_operational_mappings=_collection(one=mapping),
        folio_charges=_collection(rows=[{"total": 110, "tax_amount": 10}]),
        payments=_collection(rows=[{"amount": 110, "method": "cash"}]),
        night_audit_runs=_collection(),
    )
    post = AsyncMock(return_value={"id": "journal-1", "entry_no": "YEV-2026-00000001"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)

    result = await bridge.post_night_audit_daily_to_gl(
        database,
        "tenant-a",
        "2026-08-21",
        run_id="run-1",
    )

    assert result["status"] == "posted"
    kwargs = post.await_args.kwargs
    assert kwargs["idempotency_key"] == "operational-daily:2026-08-21"
    assert kwargs["source"] == "night_audit"
    assert kwargs["lines"] == [
        {"account_code": "120", "debit": 110.0, "memo": "Günlük folio tahakkukları"},
        {"account_code": "600", "credit": 100.0, "memo": "Günlük oda/PMS geliri"},
        {"account_code": "391", "credit": 10.0, "memo": "Günlük hesaplanan vergi"},
        {"account_code": "100", "debit": 110.0, "memo": "Günlük tahsilatlar"},
        {"account_code": "120", "credit": 110.0, "memo": "Günlük folio tahsilat kapaması"},
    ]
    database.night_audit_runs.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_night_audit_bridge_is_disabled_until_configured(monkeypatch):
    database = SimpleNamespace(
        gl_operational_mappings=_collection(one=None),
        night_audit_runs=_collection(),
    )
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)

    result = await bridge.post_night_audit_daily_to_gl(
        database,
        "tenant-a",
        "2026-08-21",
        run_id="run-1",
    )

    assert result == {"status": "skipped", "reason": "not_configured"}
    post.assert_not_awaited()
    database.night_audit_runs.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_pos_bridge_posts_settlement_revenue_and_tax(monkeypatch):
    mapping = {**bridge.DEFAULT_MAPPING, "tenant_id": "tenant-a", "enabled": True}
    database = SimpleNamespace(
        gl_operational_mappings=_collection(one=mapping),
        pos_transactions=_collection(),
    )
    post = AsyncMock(return_value={"id": "journal-pos", "entry_no": "YEV-2026-00000002"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    transaction = {
        "id": "txn-1",
        "order_id": "order-1",
        "order_number": "42",
        "transaction_date": "2026-08-21",
        "total_amount": 220,
        "payment_method": "card",
    }

    result = await bridge.post_direct_pos_to_gl(
        database,
        "tenant-a",
        transaction=transaction,
        order={"tax_amount": 20},
        posted_to_folio=False,
        actor="cashier-1",
    )

    assert result["status"] == "posted"
    kwargs = post.await_args.kwargs
    assert kwargs["idempotency_key"] == "pos-direct:order-1"
    assert kwargs["lines"] == [
        {"account_code": "108", "debit": 220.0, "memo": "POS tahsilatı"},
        {"account_code": "600", "credit": 200.0, "memo": "POS geliri"},
        {"account_code": "391", "credit": 20.0, "memo": "POS hesaplanan vergi"},
    ]


@pytest.mark.asyncio
async def test_room_charge_pos_skips_direct_gl_to_prevent_double_post(monkeypatch):
    database = SimpleNamespace(gl_operational_mappings=_collection(one={**bridge.DEFAULT_MAPPING, "enabled": True}))
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)

    result = await bridge.post_direct_pos_to_gl(
        database,
        "tenant-a",
        transaction={},
        order={},
        posted_to_folio=True,
        actor="cashier-1",
    )

    assert result == {"status": "skipped", "reason": "folio_path"}
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_comp_pos_is_auditable_no_activity_not_a_bridge_failure(monkeypatch):
    mapping = {**bridge.DEFAULT_MAPPING, "tenant_id": "tenant-a", "enabled": True}
    database = SimpleNamespace(
        gl_operational_mappings=_collection(one=mapping),
        pos_transactions=_collection(),
    )
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)

    result = await bridge.post_direct_pos_to_gl(
        database,
        "tenant-a",
        transaction={
            "id": "txn-comp",
            "order_id": "order-comp",
            "transaction_date": "2026-09-09",
            "total_amount": 0,
            "payment_method": "complimentary",
        },
        order={"tax_amount": 0},
        posted_to_folio=False,
        actor="cashier-1",
    )

    assert result == {"status": "skipped", "reason": "no_activity"}
    post.assert_not_awaited()
    database.pos_transactions.update_one.assert_awaited_once_with(
        {"tenant_id": "tenant-a", "id": "txn-comp"},
        {"$set": {"gl_bridge_status": "no_activity"}},
    )


@pytest.mark.asyncio
async def test_discounted_pos_posts_the_settled_net_and_recomputed_tax(monkeypatch):
    mapping = {**bridge.DEFAULT_MAPPING, "tenant_id": "tenant-a", "enabled": True}
    database = SimpleNamespace(
        gl_operational_mappings=_collection(one=mapping),
        pos_transactions=_collection(),
    )
    post = AsyncMock(return_value={"id": "journal-discount"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)

    await bridge.post_direct_pos_to_gl(
        database,
        "tenant-a",
        transaction={
            "id": "txn-discount",
            "order_id": "order-discount",
            "order_number": "43",
            "transaction_date": "2026-09-09",
            "total_amount": 180,
            "payment_method": "cash",
        },
        order={"tax_amount": 15},
        posted_to_folio=False,
        actor="cashier-1",
    )

    assert post.await_args.kwargs["lines"] == [
        {"account_code": "100", "debit": 180.0, "memo": "POS tahsilatı"},
        {"account_code": "600", "credit": 165.0, "memo": "POS geliri"},
        {"account_code": "391", "credit": 15.0, "memo": "POS hesaplanan vergi"},
    ]


@pytest.mark.asyncio
async def test_night_audit_matrix_splits_cash_and_card_and_excludes_voids(monkeypatch):
    mapping = {**bridge.DEFAULT_MAPPING, "tenant_id": "tenant-a", "enabled": True}
    charges = _collection(rows=[{"total": 330, "tax_amount": 30}])
    payments = _collection(rows=[
        {"amount": 110, "method": "cash"},
        {"amount": 220, "method": "card"},
    ])
    database = SimpleNamespace(
        gl_operational_mappings=_collection(one=mapping),
        folio_charges=charges,
        payments=payments,
        night_audit_runs=_collection(),
    )
    post = AsyncMock(return_value={"id": "journal-split"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)

    result = await bridge.post_night_audit_daily_to_gl(
        database,
        "tenant-a",
        "2026-09-09",
        run_id="run-split",
    )

    assert result["charge_total"] == 330
    assert result["payment_total"] == 330
    assert post.await_args.kwargs["lines"] == [
        {"account_code": "120", "debit": 330.0, "memo": "Günlük folio tahakkukları"},
        {"account_code": "600", "credit": 300.0, "memo": "Günlük oda/PMS geliri"},
        {"account_code": "391", "credit": 30.0, "memo": "Günlük hesaplanan vergi"},
        {"account_code": "100", "debit": 110.0, "memo": "Günlük tahsilatlar"},
        {"account_code": "108", "debit": 220.0, "memo": "Günlük tahsilatlar"},
        {"account_code": "120", "credit": 330.0, "memo": "Günlük folio tahsilat kapaması"},
    ]

    charge_filter = charges.find.call_args.args[0]
    payment_filter = payments.find.call_args.args[0]
    assert charge_filter["tenant_id"] == payment_filter["tenant_id"] == "tenant-a"
    assert charge_filter["voided"] == payment_filter["voided"] == {"$ne": True}
    assert {"date": {"$gte": "2026-09-09", "$lt": "2026-09-10"}} in charge_filter["$or"]
