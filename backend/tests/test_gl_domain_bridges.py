"""Durable, tenant-scoped GL bridge contracts for operational modules."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import fnb_cost_router as fnb
from routers import mice, procurement


def _user():
    return SimpleNamespace(
        id="user-1",
        tenant_id="tenant-a",
        role="super_admin",
        roles=["super_admin"],
        is_super_admin=True,
        granted_permissions=[],
    )


def _database(**collections):
    return SimpleNamespace(**collections)


@pytest.mark.asyncio
async def test_procurement_gl_uses_received_po_server_total_and_idempotency(monkeypatch):
    po = {
        "id": "po-1",
        "tenant_id": "tenant-a",
        "status": "received",
        "grand_total": 125.5,
        "po_no": "PO-1",
        "last_received_at": "2026-08-13T10:00:00Z",
    }
    collection = SimpleNamespace(find_one=AsyncMock(return_value=po), update_one=AsyncMock())
    database = _database(proc_purchase_orders=collection)
    post = AsyncMock(return_value={"id": "journal-1"})
    monkeypatch.setattr(procurement, "get_system_db", lambda: database)
    monkeypatch.setattr(procurement, "post_journal_entry", post)

    result = await procurement.post_invoice_to_gl(
        procurement.PurchaseOrderGLPostIn(purchase_order_id="po-1"),
        current_user=_user(),
        _perm=None,
    )

    assert result == {"status": "success", "journal_entry_id": "journal-1"}
    assert collection.find_one.await_args.args[0] == {"id": "po-1", "tenant_id": "tenant-a"}
    kwargs = post.await_args.kwargs
    assert kwargs["idempotency_key"] == "procurement-po:po-1"
    assert kwargs["lines"][0]["debit"] == 125.5
    assert kwargs["lines"][1]["credit"] == 125.5


@pytest.mark.asyncio
async def test_procurement_gl_rejects_unreceived_po_without_post(monkeypatch):
    collection = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "po-1", "tenant_id": "tenant-a", "status": "sent"}),
        update_one=AsyncMock(),
    )
    post = AsyncMock()
    monkeypatch.setattr(procurement, "get_system_db", lambda: _database(proc_purchase_orders=collection))
    monkeypatch.setattr(procurement, "post_journal_entry", post)

    with pytest.raises(HTTPException) as exc:
        await procurement.post_invoice_to_gl(
            procurement.PurchaseOrderGLPostIn(purchase_order_id="po-1"),
            current_user=_user(),
            _perm=None,
        )

    assert exc.value.status_code == 409
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_mice_gl_uses_tenant_event_total_and_idempotency(monkeypatch):
    event = {
        "id": "event-1",
        "tenant_id": "tenant-a",
        "status": "confirmed",
        "end_date": "2026-08-13",
        "totals": {"grand_total": 780},
    }
    collection = SimpleNamespace(find_one=AsyncMock(return_value=event), update_one=AsyncMock())
    post = AsyncMock(return_value={"id": "journal-2"})
    monkeypatch.setattr(mice, "get_system_db", lambda: _database(mice_events=collection))
    monkeypatch.setattr(mice, "post_journal_entry", post)

    result = await mice.post_beo_to_folio("event-1", current_user=_user(), _perm=None)

    assert result["journal_entry_id"] == "journal-2"
    assert collection.find_one.await_args.args[0] == {"id": "event-1", "tenant_id": "tenant-a"}
    kwargs = post.await_args.kwargs
    assert kwargs["idempotency_key"] == "mice-event:event-1"
    assert kwargs["lines"][0]["debit"] == 780


@pytest.mark.asyncio
async def test_fnb_gl_uses_computed_cost_and_period_idempotency(monkeypatch):
    variance = AsyncMock(
        return_value={"totals": {"actual_cost": 42.25, "theoretical_cost": 40}}
    )
    post = AsyncMock(return_value={"id": "journal-4"})
    monkeypatch.setattr(fnb, "yield_variance", variance)
    monkeypatch.setattr(fnb, "post_journal_entry", post)

    result = await fnb.post_fnb_cost_to_gl(
        start="2026-08-01",
        end="2026-08-07",
        outlet_id=None,
        current_user=_user(),
    )

    assert result["journal_entry_id"] == "journal-4"
    kwargs = post.await_args.kwargs
    assert kwargs["idempotency_key"] == "fnb-cost:2026-08-01:2026-08-07:all"
    assert kwargs["lines"][0]["debit"] == 42.25
    assert kwargs["lines"][1]["credit"] == 42.25


@pytest.mark.asyncio
async def test_fnb_gl_zero_cost_is_not_fake_success(monkeypatch):
    post = AsyncMock()
    monkeypatch.setattr(
        fnb,
        "yield_variance",
        AsyncMock(return_value={"totals": {"actual_cost": 0, "theoretical_cost": 0}}),
    )
    monkeypatch.setattr(fnb, "post_journal_entry", post)

    with pytest.raises(HTTPException) as exc:
        await fnb.post_fnb_cost_to_gl(
            start="2026-08-01",
            end="2026-08-07",
            outlet_id=None,
            current_user=_user(),
        )

    assert exc.value.status_code == 400
    post.assert_not_awaited()


def test_operational_gl_bridges_do_not_import_legacy_mock():
    for module in (procurement, mice, fnb):
        source = module.__loader__.get_source(module.__name__)
        assert "routers.finance.general_ledger import mock_db" not in source
