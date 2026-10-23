"""Existing-window allocation: real ledger math, fake transactional storage only."""
import asyncio
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import OperationFailure

from domains.pms import folio_window_router as api
from modules.pms_core.folio_allocation import FolioAllocationRequest, allocate_posted_debt
from modules.pms_core.receivable_reporting import folio_snapshots
from modules.pms_core.reporting_financials import effective_collection


def matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(matches(doc, part) for part in value):
                return False
            continue
        actual = doc.get(key)
        if isinstance(value, dict):
            if "$in" in value and not (any(v in value["$in"] for v in actual) if isinstance(actual, list) else actual in value["$in"]):
                return False
            if "$nin" in value and actual in value["$nin"]:
                return False
            if "$ne" in value and actual == value["$ne"]:
                return False
        elif actual != value:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    async def to_list(self, _limit):
        return self.rows

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row
        return iterate()


class Collection:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))
        self.fail_write = False

    def find(self, query, projection=None, *, session):
        assert session is not None
        return Cursor([row for row in self.rows if matches(row, query)])

    async def find_one(self, query, projection=None, *, session):
        return next(iter(await self.find(query, projection, session=session).to_list(None)), None)

    async def insert_one(self, row, *, session):
        assert session is not None
        if self.fail_write:
            raise RuntimeError("injected write failure")
        self.rows.append(deepcopy(row))

    async def update_one(self, query, update, *, session):
        assert session is not None
        if self.fail_write:
            raise RuntimeError("injected write failure")
        for row in self.rows:
            if matches(row, query):
                row.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


@pytest.fixture
def ledger():
    base = {"tenant_id": "hotel-a", "booking_id": "booking", "status": "open", "currency": "TRY"}
    source = {**base, "id": "guest", "folio_number": "F-1", "balance": 999999}
    target = {**base, "id": "company", "folio_number": "F-2", "cari_account_id": "ar-company", "balance": 0}
    return SimpleNamespace(folios=Collection([source, target]),
        bookings=Collection([{ "id": "booking", "tenant_id": "hotel-a", "currency": "TRY" }]),
        tenant_settings=Collection([{ "tenant_id": "hotel-a", "business_date": "2026-10-23" }]),
        invoices=Collection(), payments=Collection(), folio_operations=Collection(), pms_audit_trail=Collection(),
        folio_charges=Collection([{ "id": key, "tenant_id": "hotel-a", "booking_id": "booking", "folio_id": "guest",
            "voided": False, "currency": "TRY", "total": value, "amount": value - tax, "tax_amount": tax,
            "charge_category": category, "business_date": "2026-10-22" }
            for key, value, tax, category in [("room", 6000, 600, "room"), ("extras", 4000, 400, "minibar")]]))


def request(**overrides):
    return FolioAllocationRequest(request_id=overrides.pop("request_id", uuid4()), booking_id="booking",
        source_folio_id="guest", target_folio_id="company", mode="items", charge_ids=["room"], expected_amount="6000.00", reason="Konaklama şirket hesabına", **overrides)


async def run(db, body, tenant="hotel-a"):
    return await allocate_posted_debt(db, tenant, "operator", body, session=object())


@pytest.mark.asyncio
async def test_company_6000_guest_4000_then_card_and_ar_settle_separately(ledger):
    original = deepcopy(ledger.folio_charges.rows)
    result = await run(ledger, request())
    assert (result["source_balance"], result["target_balance"]) == (4000, 6000)
    assert len(ledger.folios.rows) == 2 and not ledger.payments.rows
    assert sum(row["tax_amount"] for row in ledger.folio_charges.rows) == 1000
    assert all({**row, "folio_id": "guest"} == old for row, old in zip(ledger.folio_charges.rows, original))
    ledger.payments.rows.extend([{ "id": "card", "tenant_id": "hotel-a", "folio_id": "guest", "amount": 4000, "currency": "TRY", "method": "credit_card" },
        { "id": "ar", "tenant_id": "hotel-a", "folio_id": "company", "amount": 6000, "currency": "TRY", "method": "city_ledger" }])
    snapshots = await folio_snapshots(ledger, "hotel-a", ledger.folios.rows, fallback_currency="TRY", session=object())
    assert all(snap["balance_by_currency"]["TRY"] == 0 for snap in snapshots.values())
    assert sum(effective_collection(row) for row in ledger.payments.rows) == 4000


@pytest.mark.asyncio
async def test_fixed_amount_exact_cents_full_balance_and_replay(ledger):
    body = request().model_copy(update={"mode": "amount", "charge_ids": [], "expected_amount": None, "amount": Decimal("10000.00")})
    first = await run(ledger, body)
    second = await run(ledger, body)
    assert second == {**first, "replayed": True}
    assert first["source_balance"] == 0 and first["target_balance"] == 10000
    assert len(ledger.folio_charges.rows) == 4
    adjustments = ledger.folio_charges.rows[2:]
    assert sum(row["total"] for row in adjustments) == 0
    assert all(row["business_date"] == "2026-10-23" and row["tax_amount"] == 0 for row in adjustments)
    assert len(ledger.folio_operations.rows) == len(ledger.pms_audit_trail.rows) == 1
    audit = ledger.pms_audit_trail.rows[0]
    assert audit['timestamp'] and audit['entity_id'] == 'guest' and audit['metadata']['folio_id'] == 'company'
    assert audit['metadata']['before']['guest'] == 10000 and audit['metadata']['after']['guest'] == 0
    with pytest.raises(HTTPException) as exc:
        await run(ledger, body.model_copy(update={"reason": "Different request"}))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_amount_uses_ledger_not_cached_balance_and_keeps_cents(ledger):
    data = request().model_dump()
    body = FolioAllocationRequest(**{**data, "mode": "amount", "charge_ids": [], "expected_amount": None, "amount": "10000.01"})
    with pytest.raises(HTTPException) as exc:
        await run(ledger, body)
    assert exc.value.status_code == 409
    body = FolioAllocationRequest(**{**data, "mode": "amount", "charge_ids": [], "expected_amount": None, "amount": "6000.01"})
    result = await run(ledger, body)
    assert (result['source_balance'], result['target_balance']) == (3999.99, 6000.01)
    assert sum(row['tax_amount'] for row in ledger.folio_charges.rows) == 1000
    assert not ledger.payments.rows and ledger.bookings.rows[0]['currency'] == 'TRY'


@pytest.mark.parametrize("mutation,status", [
    (lambda db: db.folios.rows[0].update(status="closed"), 409),
    (lambda db: db.folios.rows[1].update(status="closed"), 409),
    (lambda db: db.folios.rows[1].update(tenant_id="hotel-b"), 404),
    (lambda db: db.folios.rows[1].update(booking_id="other-booking"), 404),
    (lambda db: db.folios.rows[1].update(currency="EUR"), 409),
    (lambda db: db.folio_charges.rows[0].update(voided=True), 409),
    (lambda db: db.folio_charges.rows[0].update(total=5500), 409),
    (lambda db: db.folio_charges.rows[0].update(total=6000.001), 409),
    (lambda db: db.folio_charges.rows[0].update(invoice_id="invoiced"), 409),
    (lambda db: db.folio_charges.rows[0].update(charge_category="split_adjustment"), 409),
    (lambda db: db.folios.rows[0].update(invoice_id="invoice"), 409),
    (lambda db: db.invoices.rows.append({"tenant_id": "hotel-a", "booking_id": "booking", "status": "draft"}), 409),
    (lambda db: db.tenant_settings.rows.clear(), 409),
    (lambda db: db.payments.rows.append({"id": "paid", "tenant_id": "hotel-a", "folio_id": "guest", "amount": 5000, "currency": "TRY"}), 409),
])
@pytest.mark.asyncio
async def test_invalid_or_stale_selection_has_no_writes(ledger, mutation, status):
    mutation(ledger)
    before = deepcopy(vars(ledger))
    with pytest.raises(HTTPException) as exc:
        await run(ledger, request())
    assert exc.value.status_code == status
    assert {key: value.rows for key, value in vars(ledger).items()} == {key: value.rows for key, value in before.items()}


@pytest.mark.parametrize("patch", [{"mode": "amount", "charge_ids": [], "amount": "NaN"}, {"mode": "amount", "charge_ids": [], "amount": "1.001"},
    {"mode": "amount", "charge_ids": [], "amount": 0}, {"charge_ids": ["room", "room"]}, {"charge_ids": []},
    {"target_folio_id": "guest"}, {"reason": " "}, {"mode": "items", "amount": 1}, {"expected_amount": None}])
def test_request_validation_is_fail_closed(patch):
    data = request().model_dump()
    with pytest.raises(ValidationError):
        FolioAllocationRequest(**{**data, **({"expected_amount": None} if patch.get('mode') == 'amount' else {}), **patch})


@pytest.mark.asyncio
async def test_route_uses_shared_booking_and_sorted_folio_transaction_locks(ledger, monkeypatch):
    monkeypatch.setattr(api, "db", ledger)
    gate = asyncio.Lock()

    async def transaction(**kwargs):
        assert kwargs["locks_collection"] == "reservation_financial_locks"
        assert kwargs["resources"] == [("booking", "booking"), ("folio", "company"), ("folio", "guest")]
        async with gate:  # Simulate the driver's serialisable callback/retry contract.
            snapshot = {name: deepcopy(coll.rows) for name, coll in vars(ledger).items()}
            try:
                return await kwargs["callback"](object())
            except Exception:
                for name, rows in snapshot.items():
                    getattr(ledger, name).rows = rows
                raise

    monkeypatch.setattr("core.booking_atomicity.with_resource_locks", transaction)
    user = SimpleNamespace(id="operator", tenant_id="hotel-a")
    ledger.pms_audit_trail.fail_write = True
    with pytest.raises(RuntimeError):
        await api.allocate_windows(request(), user=user)
    assert len(ledger.folio_charges.rows) == 2 and ledger.folio_charges.rows[0]["folio_id"] == "guest"
    assert not ledger.folio_operations.rows
    ledger.pms_audit_trail.fail_write = False
    body = request()
    results = await asyncio.gather(*[api.allocate_windows(body, user=user) for _ in range(2)])
    assert sum(result["replayed"] for result in results) == 1
    assert len(ledger.folio_operations.rows) == 1

    # A different request cannot spend the same source debt after the first.
    body = FolioAllocationRequest(**{**request().model_dump(), "mode": "amount", "charge_ids": [], "expected_amount": None, "amount": "3000.00"})
    another = body.model_copy(update={"request_id": uuid4()})
    results = await asyncio.gather(api.allocate_windows(body, user=user), api.allocate_windows(another, user=user), return_exceptions=True)
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    assert sum(isinstance(result, dict) for result in results) == 1


@pytest.mark.asyncio
async def test_no_nontransactional_fallback(ledger, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await allocate_posted_debt(ledger, "hotel-a", "operator", request(), session=None)
    assert exc.value.status_code == 503

    async def unavailable(**_kwargs):
        raise OperationFailure("Transaction numbers are only allowed on a replica set")
    monkeypatch.setattr("core.booking_atomicity.with_resource_locks", unavailable)
    with pytest.raises(HTTPException) as exc:
        await api.allocate_windows(request(), user=SimpleNamespace(id="operator", tenant_id="hotel-a"))
    assert exc.value.status_code == 503


def test_allocation_requires_transfer_permission():
    route = next(route for route in api.router.routes if route.path.endswith('/allocate'))
    dependency = next(dep for dep in route.dependant.dependencies if dep.name == '_perm')
    assert 'transfer_folio' in [cell.cell_contents for cell in dependency.call.__closure__]
