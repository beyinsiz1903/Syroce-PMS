"""Task #199 — VKN/TCKN customer-tax validation enforced at the HTTP route.

The model-level contract is locked by ``test_invoice_tax_id_contract.py`` and the
live e-Fatura/e-Arşiv behaviour by the CI-only stress spec
``frontend/e2e-stress/specs/98-efatura-earsiv-dryrun.spec.js``. Neither runs the
actual FastAPI route (auth + module/permission gate + body validation) in normal
CI. These TestClient tests close that gap: a regression that drops the validator
or stops the route using the validated request model would now fail fast without
the full stress harness.

Self-contained, in-process: a fake Mongo and dependency overrides stand in for
auth/module/permission, matching the ``test_inventory_transfer_unit_guard.py``
pattern. No running backend or live DB required.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.finance import accounting as accounting_mod
from routers.finance import invoices as invoices_mod
from routers.finance.accounting import router as accounting_router
from routers.finance.invoices import router as invoices_router

INVALID_TAX_IDS = ["123", "12345abc90", "123456789", "123456789012", "ABCDEFGHIJ"]


class _FakeCollection:
    def __init__(self):
        self.inserts = []

    async def count_documents(self, filt):
        return len(self.inserts)

    async def insert_one(self, doc):
        self.inserts.append(doc)
        return SimpleNamespace(inserted_id="x")


class _FakeDB:
    def __init__(self):
        self.invoices = _FakeCollection()
        self.accounting_invoices = _FakeCollection()
        self.cash_flow = _FakeCollection()


def _override_gate_deps(app, path, names):
    """Override auth + the named module/permission gate deps for one route."""
    from core.security import get_current_user

    async def _fake_user():
        return SimpleNamespace(id="u1", tenant_id="t1", name="Tester")

    async def _noop():
        return None

    app.dependency_overrides[get_current_user] = _fake_user
    for route in app.routes:
        if getattr(route, "path", "") != path:
            continue
        for param in route.dependant.dependencies:
            if param.name in names:
                app.dependency_overrides[param.call] = _noop
            for sub in param.dependencies:
                if sub.name in names:
                    app.dependency_overrides[sub.call] = _noop
        break


@pytest.fixture
def invoices_client(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(invoices_mod, "db", fake_db)
    monkeypatch.setattr(accounting_mod, "db", fake_db)
    app = FastAPI()
    app.include_router(invoices_router, prefix="/api")
    _override_gate_deps(app, "/api/invoices", {"_"})
    return TestClient(app), fake_db


@pytest.fixture
def accounting_client(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(accounting_mod, "db", fake_db)
    monkeypatch.setattr(accounting_mod, "cache", None)
    app = FastAPI()
    app.include_router(accounting_router, prefix="/api")
    _override_gate_deps(app, "/api/accounting/invoices", {"_perm"})
    return TestClient(app), fake_db


def _invoice_payload(**extra):
    payload = dict(
        customer_name="Acme A.S.",
        customer_email="billing@acme.test",
        items=[{"description": "Room", "quantity": 1, "unit_price": 100, "total": 100}],
        subtotal=100.0,
        tax=20.0,
        total=120.0,
        due_date="2026-06-30",
    )
    payload.update(extra)
    return payload


def _accounting_payload(**extra):
    payload = dict(
        invoice_type="sales",
        customer_name="Acme A.S.",
        items=[{"description": "Room", "quantity": 1, "unit_price": 100, "vat_rate": 20}],
        due_date="2026-06-30",
    )
    payload.update(extra)
    return payload


def _tax_id_in_loc(body):
    """True when a 422 error entry references the tax-identity field."""
    for err in body.get("detail", []):
        if isinstance(err, dict) and "customer_tax" in ".".join(
            str(p) for p in err.get("loc", [])
        ):
            return True
    return False


# ── /api/invoices (InvoiceCreate.customer_tax_id) ──────────────────────────


class TestInvoicesRouteTaxId:
    @pytest.mark.parametrize("bad", INVALID_TAX_IDS)
    def test_invalid_tax_id_rejected_422(self, invoices_client, bad):
        client, fake_db = invoices_client
        r = client.post("/api/invoices", json=_invoice_payload(customer_tax_id=bad))
        assert r.status_code == 422, f"got {r.status_code} {r.text}"
        assert _tax_id_in_loc(r.json()), r.text
        assert fake_db.invoices.inserts == []

    # NOTE: the /invoices response_model (Invoice) intentionally has no
    # customer_tax_id field, so a valid id is proven accepted by a 200 (no 422
    # on customer_tax_id) plus a persisted row — the inverse of the 422 cases
    # above which share the same payload but a malformed id.
    def test_valid_vkn_accepted(self, invoices_client):
        client, fake_db = invoices_client
        r = client.post(
            "/api/invoices", json=_invoice_payload(customer_tax_id="1234567890")
        )
        assert r.status_code == 200, f"got {r.status_code} {r.text}"
        assert len(fake_db.invoices.inserts) == 1

    def test_valid_tckn_accepted(self, invoices_client):
        client, fake_db = invoices_client
        r = client.post(
            "/api/invoices", json=_invoice_payload(customer_tax_id="12345678901")
        )
        assert r.status_code == 200, f"got {r.status_code} {r.text}"
        assert len(fake_db.invoices.inserts) == 1


# ── /api/accounting/invoices (AccountingInvoiceCreateRequest.customer_tax_number)


class TestAccountingInvoicesRouteTaxNumber:
    @pytest.mark.parametrize("bad", INVALID_TAX_IDS)
    def test_invalid_tax_number_rejected_422(self, accounting_client, bad):
        client, fake_db = accounting_client
        r = client.post(
            "/api/accounting/invoices",
            json=_accounting_payload(customer_tax_number=bad),
        )
        assert r.status_code == 422, f"got {r.status_code} {r.text}"
        assert _tax_id_in_loc(r.json()), r.text
        assert fake_db.accounting_invoices.inserts == []

    def test_valid_vkn_accepted(self, accounting_client):
        client, fake_db = accounting_client
        r = client.post(
            "/api/accounting/invoices",
            json=_accounting_payload(customer_tax_number="1234567890"),
        )
        assert r.status_code == 200, f"got {r.status_code} {r.text}"
        assert r.json()["customer_tax_number"] == "1234567890"
        assert len(fake_db.accounting_invoices.inserts) == 1

    def test_valid_tckn_accepted(self, accounting_client):
        client, fake_db = accounting_client
        r = client.post(
            "/api/accounting/invoices",
            json=_accounting_payload(customer_tax_number="12345678901"),
        )
        assert r.status_code == 200, f"got {r.status_code} {r.text}"
        assert r.json()["customer_tax_number"] == "12345678901"
        assert len(fake_db.accounting_invoices.inserts) == 1
