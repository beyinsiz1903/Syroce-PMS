from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.integrations import operational_gl_bridge as bridge


def database(tip_account="335"):
    return SimpleNamespace(
        gl_operational_mappings=SimpleNamespace(find_one=AsyncMock(return_value={
            **bridge.DEFAULT_MAPPING, "enabled": True, "tip_account_code": tip_account,
        })),
        pos_transactions=SimpleNamespace(update_one=AsyncMock()),
        gl_journal_entries=SimpleNamespace(find_one=AsyncMock(return_value={
            "lines": [{"account_code": "335", "credit": 1.01}],
        })),
    )


SALE = {"id": "sale", "order_id": "order", "transaction_date": "2026-10-30",
        "gl_journal_entry_id": "original-journal",
        "total_amount": 111.01, "tax_amount": 10, "tip_amount": 1.01,
        "payment_breakdown": [{"method": "cash", "amount": 74.01}, {"method": "card", "amount": 37}]}


@pytest.mark.asyncio
async def test_tip_is_separate_from_sales_tax_and_actual_tender(monkeypatch):
    post = AsyncMock(return_value={"id": "journal"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    await bridge.post_direct_pos_to_gl(database(), "hotel", transaction=SALE, order={}, posted_to_folio=False, actor="cashier")
    lines = post.await_args.kwargs["lines"]
    assert {r["account_code"]: r.get("credit", r.get("debit")) for r in lines} == {
        "100": 74.01, "108": 37, "600": 100, "391": 10, "335": 1.01}


@pytest.mark.asyncio
@pytest.mark.parametrize("account", [None, "600", "391", "100", "326"])
async def test_tip_without_separate_mapping_cannot_be_silently_posted_as_sales(monkeypatch, account):
    db = database(account)
    db.gl_operational_mappings.find_one.return_value["security_deposit_account_code"] = "326"
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    with pytest.raises(bridge.SourceValuationRequired, match="tip"):
        await bridge.post_direct_pos_to_gl(db, "hotel", transaction=SALE, order={}, posted_to_folio=False, actor="cashier")
    post.assert_not_awaited()
    db.pos_transactions.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_cumulative_partial_refund_tip_snapshots_reverse_exactly_once(monkeypatch):
    post = AsyncMock(return_value={"id": "refund-journal"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    for ident, amount, tax, tip in [("first", -55.51, -5, -.51), ("last", -55.50, -5, -.50)]:
        await bridge.post_direct_pos_refund_to_gl(database(), "hotel",
            refund={"id": ident, "order_id": "order", "transaction_date": "2026-10-30",
                    "total_amount": amount, "tax_amount": tax, "tip_amount": tip},
            original_transaction=SALE, order={}, actor="cashier")
    lines = [r for call in post.await_args_list for r in call.kwargs["lines"]]
    assert round(sum(r.get("debit", 0) for r in lines if r["account_code"] == "600"), 2) == 100
    assert round(sum(r.get("debit", 0) for r in lines if r["account_code"] == "335"), 2) == 1.01
    assert round(sum(r.get("debit", 0) for r in lines), 2) == 111.01
    assert round(sum(r.get("credit", 0) for r in lines), 2) == 111.01


@pytest.mark.asyncio
async def test_legacy_tipped_refund_requires_original_component_evidence(monkeypatch):
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    with pytest.raises(bridge.SourceValuationRequired, match="tip"):
        await bridge.post_direct_pos_refund_to_gl(database(), "hotel",
            refund={"id": "refund", "order_id": "order", "transaction_date": "2026-10-30", "total_amount": -55.51},
            original_transaction=SALE, order={}, actor="cashier")
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_sealed_tip_as_revenue_must_not_reverse_a_nonexistent_liability(monkeypatch):
    db = database()
    db.gl_journal_entries.find_one.return_value = {"lines": [{"account_code": "600", "credit": 101.01}]}
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    with pytest.raises(bridge.SourceValuationRequired, match="source-linked reconciliation"):
        await bridge.post_direct_pos_refund_to_gl(db, "hotel",
            refund={"id": "refund", "order_id": "order", "transaction_date": "2026-10-30",
                    "total_amount": -111.01, "tax_amount": -10, "tip_amount": -1.01},
            original_transaction=SALE, order={}, actor="cashier")
    post.assert_not_awaited()
    db.pos_transactions.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tip,tax", [(-1, 10), (102, 10)])
async def test_invalid_sale_components_cannot_create_a_journal(monkeypatch, tip, tax):
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    with pytest.raises(bridge.OperationalGLBridgeError):
        await bridge.post_direct_pos_to_gl(database(), "hotel", transaction={**SALE, "tip_amount": tip, "tax_amount": tax},
            order={}, posted_to_folio=False, actor="cashier")
    post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tip_code,tip_type,accepted", [("335", "liability", True), ("335", "revenue", False), ("391", "liability", False)])
async def test_mapping_requires_active_separate_liability_and_audits_choice(monkeypatch, tip_code, tip_type, accepted):
    from fastapi import HTTPException

    from domains.accounting import gl_router as gl

    db = database()
    db.gl_operational_mappings.update_one = AsyncMock()
    accounts = [{"code": code, "type": "asset"} for code in ("100", "108", "102", "120")]
    accounts += [{"code": "600", "type": "revenue"}, {"code": "391", "type": "liability"}]
    if tip_code != "391":
        accounts.append({"code": tip_code, "type": tip_type})
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=accounts))
    db.gl_accounts = SimpleNamespace(find=Mock(return_value=cursor))
    monkeypatch.setattr(gl, "db", db)
    audit = AsyncMock()
    monkeypatch.setattr(gl, "log_audit_event", audit)
    request = gl.OperationalMappingIn(tip_account_code=tip_code)
    user = SimpleNamespace(tenant_id="hotel", role="finance", id="finance")
    if not accepted:
        with pytest.raises(HTTPException) as exc:
            await gl.update_operational_gl_mapping(request, user)
        assert exc.value.status_code == 409
        db.gl_operational_mappings.update_one.assert_not_awaited()
        audit.assert_not_awaited()
    else:
        result = await gl.update_operational_gl_mapping(request, user)
        assert result["mapping"]["tip_account_code"] == "335"
        assert result["mapping"]["enabled"] is True
        assert audit.await_args.kwargs["after_value"]["tip_account_code"] == "335"
