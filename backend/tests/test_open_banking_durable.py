from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers.finance import open_banking
from shared_kernel.gl_posting import GLPostingError


def _matches(document: dict, query: dict) -> bool:
    for field, expected in query.items():
        if field == "$or":
            if not any(_matches(document, clause) for clause in expected):
                return False
            continue
        value = document.get(field)
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$nin" in expected and value in expected["$nin"]:
                return False
            if "$ne" in expected:
                if isinstance(value, list) and expected["$ne"] in value:
                    return False
                if not isinstance(value, list) and value == expected["$ne"]:
                    return False
            if "$exists" in expected and (field in document) != expected["$exists"]:
                return False
        elif isinstance(value, list):
            if expected not in value:
                return False
        elif value != expected:
            return False
    return True


class _Cursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *args):
        return self

    def limit(self, _limit):
        return self

    async def to_list(self, length=None):
        rows = deepcopy(self.documents)
        return rows[:length] if length else rows


class _Collection:
    def __init__(self, documents=None):
        self.documents = documents or []

    def find(self, query, projection=None):
        return _Cursor([document for document in self.documents if _matches(document, query)])

    async def find_one(self, query, projection=None):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    async def update_one(self, query, update):
        for document in self.documents:
            if not _matches(document, query):
                continue
            for field, value in update.get("$set", {}).items():
                document[field] = value
            for field, value in update.get("$inc", {}).items():
                document[field] = document.get(field, 0) + value
            for field, value in update.get("$addToSet", {}).items():
                target = document.setdefault(field, [])
                if value not in target:
                    target.append(value)
            for field in update.get("$unset", {}):
                document.pop(field, None)
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _Database:
    def __init__(self):
        self.bank_transactions = _Collection(
            [
                {
                    "id": "transaction-1",
                    "tenant_id": "tenant-a",
                    "date": "2026-08-13",
                    "amount": 250,
                    "sender_iban": "TR120000000000001234567890",
                    "sender_name": "Test Sender",
                    "description": "Test payment",
                    "status": "unmatched",
                },
                {
                    "id": "transaction-1",
                    "tenant_id": "tenant-b",
                    "date": "2026-08-13",
                    "amount": 999,
                    "sender_iban": "TR990000000000009999999999",
                    "status": "unmatched",
                },
            ]
        )
        self.invoices = _Collection(
            [
                {
                    "id": "invoice-1",
                    "tenant_id": "tenant-a",
                    "invoice_number": "INV-TEST",
                    "total": 250,
                    "amount_paid": 0,
                    "status": "draft",
                    "payment_status": "pending",
                }
            ]
        )


def _user(tenant="tenant-a"):
    return SimpleNamespace(tenant_id=tenant, id="user-1", user_id="user-1")


@pytest.fixture
def database(monkeypatch):
    fake = _Database()
    monkeypatch.setattr(open_banking, "db", fake)
    return fake


@pytest.mark.asyncio
async def test_bank_transaction_list_is_tenant_scoped_and_masks_account(database):
    rows = await open_banking.get_transactions(current_user=_user(), _perm=None)

    assert len(rows) == 1
    assert rows[0]["amount"] == 250
    assert rows[0]["sender_account_masked"].startswith("TR")
    assert rows[0]["sender_account_masked"].endswith("7890")
    assert "sender_iban" not in rows[0]
    assert "1234567890" not in rows[0]["sender_account_masked"]


@pytest.mark.asyncio
async def test_bank_sync_fails_closed_without_connector(database):
    with pytest.raises(HTTPException) as exc:
        await open_banking.sync_bank_transactions(current_user=_user(), _perm=None)

    assert exc.value.status_code == 409
    assert len(database.bank_transactions.documents) == 2


@pytest.mark.asyncio
async def test_reconciliation_is_durable_tenant_scoped_and_idempotent(database, monkeypatch):
    calls = []

    async def _post(*args, **kwargs):
        calls.append(kwargs)
        return {"id": "journal-1"}

    monkeypatch.setattr(open_banking, "post_journal_entry", _post)
    request = open_banking.ReconcileRequest(transaction_id="transaction-1", invoice_id="invoice-1")

    first = await open_banking.reconcile_transaction(request, current_user=_user(), _perm=None)
    second = await open_banking.reconcile_transaction(request, current_user=_user(), _perm=None)

    assert first == {"status": "success", "already_reconciled": False}
    assert second == {"status": "success", "already_reconciled": True}
    assert len(calls) == 1
    assert calls[0]["idempotency_key"] == "bank-reconcile:transaction-1"
    own = next(row for row in database.bank_transactions.documents if row["tenant_id"] == "tenant-a")
    other = next(row for row in database.bank_transactions.documents if row["tenant_id"] == "tenant-b")
    assert own["status"] == "matched"
    assert own["journal_entry_id"] == "journal-1"
    assert other["status"] == "unmatched"
    assert database.invoices.documents[0]["amount_paid"] == 250
    assert database.invoices.documents[0]["payment_status"] == "paid"
    assert database.invoices.documents[0]["reconciled_bank_transaction_ids"] == ["transaction-1"]


@pytest.mark.asyncio
async def test_gl_rejection_leaves_transaction_unmatched(database, monkeypatch):
    async def _reject(*args, **kwargs):
        raise GLPostingError("Hesap planında yok: 102")

    monkeypatch.setattr(open_banking, "post_journal_entry", _reject)
    request = open_banking.ReconcileRequest(transaction_id="transaction-1", invoice_id="invoice-1")

    with pytest.raises(HTTPException) as exc:
        await open_banking.reconcile_transaction(request, current_user=_user(), _perm=None)

    assert exc.value.status_code == 400
    own = next(row for row in database.bank_transactions.documents if row["tenant_id"] == "tenant-a")
    assert own["status"] == "unmatched"
    assert "reconciliation_claim_id" not in own
    assert database.invoices.documents[0]["amount_paid"] == 0
    assert "bank_reconciliation_claim_id" not in database.invoices.documents[0]


@pytest.mark.asyncio
async def test_reconciliation_rejects_overpayment_before_gl_post(database, monkeypatch):
    database.bank_transactions.documents[0]["amount"] = 251

    async def _post(*args, **kwargs):
        pytest.fail("GL must not be called for an overpayment")

    monkeypatch.setattr(open_banking, "post_journal_entry", _post)
    request = open_banking.ReconcileRequest(transaction_id="transaction-1", invoice_id="invoice-1")

    with pytest.raises(HTTPException) as exc:
        await open_banking.reconcile_transaction(request, current_user=_user(), _perm=None)

    assert exc.value.status_code == 409
    own = next(row for row in database.bank_transactions.documents if row["tenant_id"] == "tenant-a")
    assert own["status"] == "unmatched"
    assert "reconciliation_claim_id" not in own
    assert "bank_reconciliation_claim_id" not in database.invoices.documents[0]
    assert database.invoices.documents[0]["amount_paid"] == 0


@pytest.mark.asyncio
async def test_reconciliation_cannot_cross_tenants(database, monkeypatch):
    monkeypatch.setattr(
        open_banking,
        "post_journal_entry",
        lambda *args, **kwargs: pytest.fail("GL must not be called"),
    )
    request = open_banking.ReconcileRequest(transaction_id="transaction-1", invoice_id="invoice-1")

    with pytest.raises(HTTPException) as exc:
        await open_banking.reconcile_transaction(request, current_user=_user("tenant-b"), _perm=None)

    assert exc.value.status_code == 404
