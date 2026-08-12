from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.integrations import invoice_gl_bridge as bridge
from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
from models.schemas.invoice_lifecycle import InvoiceLifecycleActionState


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, length=100):
        return self._docs[:length]


class _JournalCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    def find(self, query, projection=None):
        rows = []
        for doc in self.docs:
            ok = True
            for key, value in query.items():
                if doc.get(key) != value:
                    ok = False
                    break
            if ok:
                rows.append(dict(doc))
        return _Cursor(rows)


class _DB:
    def __init__(self):
        self.gl_journal_entries = _JournalCollection()


def _invoice(**overrides):
    base = dict(
        id="inv-1",
        provider_uuid="11111111-1111-4111-8111-111111111111",
        invoice_number="ABC2026000001",
        issue_date=datetime(2026, 8, 12, tzinfo=UTC),
        payable_amount=Decimal("120.00"),
        currency="TRY",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _line(**overrides):
    base = dict(
        active=True,
        line_extension_amount=Decimal("100.00"),
        kdv_amount=Decimal("20.00"),
        other_taxes=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_post_incoming_invoice_to_gl_uses_explicit_accounts_and_idempotency(monkeypatch):
    db = _DB()
    monkeypatch.setattr(bridge, "get_db_for_tenant", lambda _tenant: db)
    monkeypatch.setattr(
        bridge.IncomingInvoiceRepository,
        "get_by_id",
        AsyncMock(return_value=_invoice()),
    )
    monkeypatch.setattr(
        bridge.IncomingInvoiceRepository,
        "list_lines",
        AsyncMock(return_value=[_line()]),
    )

    captured = {}

    async def _post(_db, tenant_id, **kwargs):
        captured.update(kwargs)
        doc = {
            "id": "je-source",
            "tenant_id": tenant_id,
            "entry_no": "JE-1",
            "status": "posted",
            **kwargs,
        }
        db.gl_journal_entries.docs.append(doc)
        return dict(doc)

    monkeypatch.setattr(bridge, "post_journal_entry", _post)

    result = await bridge.post_incoming_invoice_to_gl(
        "tenant-1",
        "inv-1",
        purchase_account_code="153",
        vat_account_code="191",
        payable_account_code="320",
        actor="accountant-1",
    )

    assert captured["idempotency_key"] == "nilvera-incoming:inv-1"
    assert captured["source"] == "nilvera_incoming"
    assert captured["source_ref"] == "inv-1"
    assert captured["lines"] == [
        {
            "account_code": "153",
            "debit": 100.0,
            "credit": 0,
            "memo": "Nilvera alış faturası matrahı",
        },
        {
            "account_code": "191",
            "debit": 20.0,
            "credit": 0,
            "memo": "Nilvera indirilecek KDV",
        },
        {
            "account_code": "320",
            "debit": 0,
            "credit": 120.0,
            "memo": "Nilvera satıcı borcu",
        },
    ]
    assert result["integration_kind"] == "nilvera_incoming"
    assert result["nilvera_source_provider_uuid"] == _invoice().provider_uuid


@pytest.mark.asyncio
async def test_post_incoming_invoice_to_gl_fails_closed_on_complex_tax(monkeypatch):
    monkeypatch.setattr(
        bridge.IncomingInvoiceRepository,
        "get_by_id",
        AsyncMock(return_value=_invoice()),
    )
    monkeypatch.setattr(
        bridge.IncomingInvoiceRepository,
        "list_lines",
        AsyncMock(return_value=[_line(other_taxes=[{"tax_type": "OTV"}])]),
    )

    with pytest.raises(bridge.InvoiceGLBridgeError, match="unsupported other taxes"):
        await bridge.post_incoming_invoice_to_gl(
            "tenant-1",
            "inv-1",
            purchase_account_code="153",
            vat_account_code="191",
            payable_account_code="320",
            actor="accountant-1",
        )


@pytest.mark.asyncio
async def test_return_reversal_swaps_exact_source_debits_and_credits(monkeypatch):
    db = _DB()
    db.gl_journal_entries.docs.append(
        {
            "id": "je-source",
            "tenant_id": "tenant-1",
            "entry_no": "JE-SOURCE",
            "status": "posted",
            "source": "nilvera_incoming",
            "source_ref": "inv-1",
            "idempotency_key": "nilvera-incoming:inv-1",
            "lines": [
                {"account_code": "153", "debit": 100.0, "credit": 0.0, "memo": "base"},
                {"account_code": "191", "debit": 20.0, "credit": 0.0, "memo": "vat"},
                {"account_code": "320", "debit": 0.0, "credit": 120.0, "memo": "vendor"},
            ],
        }
    )
    monkeypatch.setattr(bridge, "get_db_for_tenant", lambda _tenant: db)

    captured = {}

    async def _post(_db, tenant_id, **kwargs):
        captured.update(kwargs)
        doc = {
            "id": "je-return",
            "tenant_id": tenant_id,
            "entry_no": "JE-RETURN",
            "status": "posted",
            **kwargs,
        }
        db.gl_journal_entries.docs.append(doc)
        return dict(doc)

    monkeypatch.setattr(bridge, "post_journal_entry", _post)

    result = await bridge.reverse_incoming_invoice_gl_for_return(
        "tenant-1",
        "inv-1",
        action_id="action-1",
        generated_provider_uuid="22222222-2222-4222-8222-222222222222",
    )

    assert captured["idempotency_key"] == "nilvera-return:action-1"
    assert captured["source"] == "nilvera_return"
    assert captured["lines"][0]["debit"] == 0.0
    assert captured["lines"][0]["credit"] == 100.0
    assert captured["lines"][1]["credit"] == 20.0
    assert captured["lines"][2]["debit"] == 120.0
    assert captured["lines"][2]["credit"] == 0.0
    assert result["reverses_entry_id"] == "je-source"
    assert result["nilvera_return_action_id"] == "action-1"


@pytest.mark.asyncio
async def test_return_reversal_is_optional_when_source_invoice_not_posted(monkeypatch):
    db = _DB()
    monkeypatch.setattr(bridge, "get_db_for_tenant", lambda _tenant: db)

    result = await bridge.reverse_incoming_invoice_gl_for_return(
        "tenant-1",
        "inv-missing",
        action_id="action-1",
        generated_provider_uuid="22222222-2222-4222-8222-222222222222",
    )
    assert result is None


@pytest.mark.asyncio
async def test_lifecycle_success_attempts_gl_reversal_and_reports_status(monkeypatch):
    action = SimpleNamespace(
        id="action-1",
        tenant_id="tenant-1",
        source_invoice_id="inv-1",
    )
    adapter = SimpleNamespace(verify_return_draft=AsyncMock(return_value=None))

    monkeypatch.setattr(
        "core.integrations.invoice_lifecycle_service.handle_return_action_success",
        AsyncMock(return_value=None),
    )
    reverse = AsyncMock(return_value={"id": "je-return"})
    monkeypatch.setattr(
        "core.integrations.invoice_lifecycle_service.reverse_incoming_invoice_gl_for_return",
        reverse,
    )
    finish = AsyncMock(return_value=True)
    monkeypatch.setattr(InvoiceLifecycleService, "_finish", finish)
    publish = AsyncMock(return_value={})
    monkeypatch.setattr(
        "core.integrations.invoice_lifecycle_service.event_bus.publish",
        publish,
    )

    await InvoiceLifecycleService._verify_return_draft(
        action,
        "worker-1",
        "22222222-2222-4222-8222-222222222222",
        adapter,
    )

    reverse.assert_awaited_once_with(
        "tenant-1",
        "inv-1",
        action_id="action-1",
        generated_provider_uuid="22222222-2222-4222-8222-222222222222",
        actor="system",
    )
    assert finish.await_args.kwargs["state"] == InvoiceLifecycleActionState.SUCCEEDED
    payload = publish.await_args.args[2]
    assert payload["gl_reversal_status"] == "posted"
    assert payload["generated_provider_uuid"] == "22222222-2222-4222-8222-222222222222"
