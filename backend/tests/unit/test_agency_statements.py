"""Period statement rules: who owes whom, penalties, payments, status guards."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.agency_statements import outstanding, penalty_amount, statement_line, statement_totals
from routers import agency_statements

BASE = {"id": "b1", "confirmation_code": "MKT-1", "check_in": "2026-11-20", "check_out": "2026-11-22",
        "total_amount": 1000, "commission_pct": 15, "syroce_b2b_fee_pct": 2,
        "cancellation_policy": {"free_until_days_before": 7, "penalty_pct": 50, "no_show_penalty_pct": 100}}


def test_on_arrival_stay_hotel_owes_commission():
    line = statement_line({**BASE, "status": "checked_out", "payment_terms": "on_arrival"}, None)
    assert (line["gross"], line["commission"], line["platform_fee"], line["net_to_hotel"]) == (1000, 150, 20, 850)
    assert (line["hotel_owes_agency"], line["agency_owes_hotel"]) == (150, 0)


def test_prepaid_stay_agency_owes_net():
    line = statement_line({**BASE, "status": "confirmed", "payment_terms": "prepaid"}, None)
    assert (line["hotel_owes_agency"], line["agency_owes_hotel"]) == (0, 850)


@pytest.mark.parametrize("cancelled_at,expected", [("2026-11-01", 0.0), ("2026-11-15", 500.0), (None, 0.0)])
def test_cancellation_penalty_follows_policy(cancelled_at, expected):
    row = {**BASE, "status": "cancelled"}
    assert penalty_amount(row, {"cancelled_at": cancelled_at} if cancelled_at else None) == expected
    line = statement_line(row, {"cancelled_at": cancelled_at} if cancelled_at else None)
    assert line["commission"] == 0 and line["agency_owes_hotel"] == expected


def test_no_show_penalty_and_totals():
    lines = [
        statement_line({**BASE, "status": "no_show", "payment_terms": "on_arrival"}, None),
        statement_line({**BASE, "id": "b2", "status": "checked_out", "payment_terms": "on_arrival"}, None),
    ]
    totals = statement_totals(lines)
    assert totals["penalty"] == 1000 and totals["hotel_owes_agency"] == 150
    assert totals["net_balance"] == 850  # agency pays the hotel
    assert (totals["bookings"], totals["no_show"]) == (1, 1)


def test_outstanding_nets_payments_by_direction():
    statement = {"totals": {"net_balance": -150.0}, "payments": [{"amount": 100, "direction": "hotel_to_agency"}]}
    assert outstanding(statement) == -50.0
    statement["payments"].append({"amount": 50, "direction": "hotel_to_agency"})
    assert outstanding(statement) == 0.0


USER = SimpleNamespace(id="u", email="ops@hotel.test", tenant_id="t1", role="admin", roles=[])


@pytest.mark.asyncio
async def test_payment_refused_before_agency_agrees(monkeypatch):
    sysdb = SimpleNamespace(agency_statements=SimpleNamespace(find_one=AsyncMock(return_value={"id": "s1", "status": "issued"})))
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: sysdb)
    with pytest.raises(HTTPException) as exc:
        await agency_statements.record_payment(
            "s1", agency_statements.PaymentCreate(amount=10, direction="hotel_to_agency", paid_at="2026-12-01"), USER
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_dispute_must_reference_statement_lines(monkeypatch):
    sysdb = SimpleNamespace(agency_statements=SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "s1", "lines": [{"booking_id": "b1"}]}), find_one_and_update=AsyncMock()))
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: sysdb)
    with pytest.raises(HTTPException) as exc:
        await agency_statements.dispute_statement(
            "s1", agency_statements.DisputeCreate(reason="Tutar hatalı", booking_ids=["other"]), {"agency_id": "a1"}
        )
    assert exc.value.status_code == 400
    sysdb.agency_statements.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_agree_only_from_issued_or_resolved(monkeypatch):
    sysdb = SimpleNamespace(agency_statements=SimpleNamespace(find_one_and_update=AsyncMock(return_value=None)))
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: sysdb)
    with pytest.raises(HTTPException) as exc:
        await agency_statements.agree_statement("s1", {"agency_id": "a1"})
    assert exc.value.status_code == 409
    query = sysdb.agency_statements.find_one_and_update.await_args.args[0]
    assert query["status"] == {"$in": ["issued", "resolved"]}


# ── consistency: concurrent payments, overlapping periods, stale commission ──

class _Statements:
    """Minimal agency_statements double with find_one_and_update semantics."""

    def __init__(self, docs):
        self.docs = docs

    @staticmethod
    def _matches(doc, query):
        for key, cond in query.items():
            if "." in key and key.split(".")[0] == "payments":
                _, index, *field = key.split(".")
                payments = doc.get("payments") or []
                item = payments[int(index)] if int(index) < len(payments) else None
                if isinstance(cond, dict) and "$exists" in cond:
                    if (item is not None) != cond["$exists"]:
                        return False
                elif item is None or item.get(field[0]) != cond:
                    return False
            elif doc.get(key) != cond:
                return False
        return True

    async def find_one(self, query, *_a, **_k):
        return next((dict(d) for d in self.docs if self._matches(d, query)), None)

    async def find_one_and_update(self, query, update, **_k):
        for doc in self.docs:
            if self._matches(doc, query):
                for key, value in update.get("$push", {}).items():
                    doc.setdefault(key, []).append(value)
                doc.update(update.get("$set", {}))
                return dict(doc)
        return None


@pytest.mark.asyncio
async def test_concurrent_payments_cannot_leave_a_paid_statement_open(monkeypatch):
    doc = {"id": "s1", "tenant_id": "t1", "status": "agreed", "currency": "TRY", "agency_id": "a1", "number": "EKS-1",
           "totals": {"net_balance": 100.0}, "payments": []}
    store = _Statements([doc])
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: SimpleNamespace(agency_statements=store))
    monkeypatch.setattr(agency_statements, "_notify_agency", AsyncMock())
    payment = agency_statements.PaymentCreate(amount=50, direction="agency_to_hotel", paid_at="2026-12-01")

    # Both requests read the statement before either writes.
    stale = dict(doc, payments=[])
    monkeypatch.setattr(agency_statements, "_hotel_statement", AsyncMock(return_value=stale))
    await agency_statements.record_payment("s1", payment, USER)
    with pytest.raises(HTTPException) as exc:
        await agency_statements.record_payment("s1", payment, USER)
    assert exc.value.status_code == 409

    # The retry reads the fresh statement and settles it.
    monkeypatch.setattr(agency_statements, "_hotel_statement", AsyncMock(side_effect=lambda *_a: dict(doc)))
    settled = await agency_statements.record_payment("s1", payment, USER)
    assert settled["status"] == "settled" and len(doc["payments"]) == 2


@pytest.mark.asyncio
async def test_overlapping_period_and_already_billed_stays_are_refused(monkeypatch):
    queries = []

    class _Store:
        async def find_one(self, query, *_a, **_k):
            queries.append(query)
            if "period_start" in query:  # overlap check
                return {"number": "EKS-1", "period_start": "2026-10-01", "period_end": "2026-10-31"} if overlap else None
            return {"number": "EKS-1", "lines": [{"booking_id": "b1", "confirmation_code": "MKT-1"}]}

    sysdb = SimpleNamespace(agency_statements=_Store())
    monkeypatch.setattr(agency_statements, "build_statement", AsyncMock(return_value={"lines": [{"booking_id": "b1"}], "totals": {}}))
    data = agency_statements.StatementCreate(agency_id="a1", period_start="2026-10-15", period_end="2026-11-15", currency="TRY")

    overlap = True
    with pytest.raises(HTTPException) as exc:
        await agency_statements._issue_statement_locked(sysdb, "t1", data, {}, USER)
    assert exc.value.status_code == 409 and "çakışıyor" in exc.value.detail
    assert queries[0]["period_start"] == {"$lte": "2026-11-15"} and queries[0]["period_end"] == {"$gte": "2026-10-15"}

    overlap = False
    with pytest.raises(HTTPException) as exc:
        await agency_statements._issue_statement_locked(sysdb, "t1", data, {}, USER)
    assert "MKT-1 zaten EKS-1" in exc.value.detail


def test_ledger_sync_takes_the_modified_commission_rate():
    from core.marketplace_ledger_sync import ledger_patch_from_booking

    ledger = {"total_amount": 100, "commission_pct": 20, "commission_amount": 20, "net_to_hotel": 80, "syroce_b2b_fee_pct": 1}
    patch = ledger_patch_from_booking(ledger, {"total_amount": 130, "agency_commission_rate": 10})
    assert (patch["commission_pct"], patch["commission_amount"], patch["net_to_hotel"]) == (10, 13, 117)
    line = statement_line({**BASE, **ledger, **patch, "status": "confirmed", "payment_terms": "prepaid"}, None)
    assert line["net_to_hotel"] == 117  # not 104 from the stale 20 %
    # Rate changed alone (amount unchanged) is healed too.
    assert ledger_patch_from_booking(ledger, {"total_amount": 100, "agency_commission_rate": 10})["net_to_hotel"] == 90


# ── statement payments are the single source for credit; payment rules ──

class _Bookings:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, *_a, **_k):
        excluded = (query.get("id") or {}).get("$ne")
        rows = [r for r in self.rows if r.get("agency_id") == query.get("agency_id") and r.get("status") != "cancelled"
                and r.get("id") != excluded]
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))

    async def find_one(self, query, *_a, **_k):
        return next((dict(r) for r in self.rows if r.get("id") == query.get("id")), None)


class _StatementFinder:
    def __init__(self, store):
        self.store = store

    def find(self, query, *_a, **_k):
        ids = set(query["lines.booking_id"]["$in"])
        rows = [d for d in self.store.docs if d.get("status") != "void"
                and any(line.get("booking_id") in ids for line in d.get("lines", []))]
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))


def _credit_world(monkeypatch):
    statement = {"id": "s1", "tenant_id": "t1", "agency_id": "a1", "number": "EKS-1", "currency": "TRY", "status": "agreed",
                 "payments": [], "lines": [{"booking_id": "b1", "agency_owes_hotel": 60}, {"booking_id": "b2", "agency_owes_hotel": 30}],
                 "totals": {"net_balance": 90, "hotel_owes_agency": 0}}
    store = _Statements([statement])
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: SimpleNamespace(agency_statements=store))
    monkeypatch.setattr(agency_statements, "_notify_agency", AsyncMock())
    bookings = _Bookings([
        {"id": "b1", "agency_id": "a1", "status": "checked_out", "currency": "TRY", "credit_exposure_amount": 60},
        {"id": "b2", "agency_id": "a1", "status": "checked_out", "currency": "TRY", "credit_exposure_amount": 30},
    ])
    return store, SimpleNamespace(bookings=bookings), SimpleNamespace(agency_statements=_StatementFinder(store))


async def _can_sell(database, statements_db, amount):
    from core.agency_credit import assert_credit_capacity

    try:
        await assert_credit_capacity(database, tenant_id="t1", agency_id="a1", contract={"credit_limit": 100, "credit_currency": "TRY"},
                                     booking_currency="TRY", new_net_exposure=amount, statements_db=statements_db)
        return True
    except HTTPException:
        return False


@pytest.mark.asyncio
async def test_paid_statement_frees_the_credit_limit(monkeypatch):
    store, database, statements_db = _credit_world(monkeypatch)
    assert not await _can_sell(database, statements_db, 20)  # 90 open + 20 > 100

    pay = agency_statements.PaymentCreate(amount=40, direction="agency_to_hotel", paid_at="2026-10-15", reference="EFT-1")
    await agency_statements.record_payment("s1", pay, USER)  # partial: clears 40 of b1 (oldest first)
    assert await _can_sell(database, statements_db, 50)  # 50 open + 50 = 100
    assert not await _can_sell(database, statements_db, 51)

    rest = agency_statements.PaymentCreate(amount=50, direction="agency_to_hotel", paid_at="2026-10-16", reference="EFT-2")
    settled = await agency_statements.record_payment("s1", rest, USER)
    assert settled["status"] == "settled"
    assert await _can_sell(database, statements_db, 100)  # every statement line cleared


@pytest.mark.asyncio
async def test_payment_rules_are_enforced_by_the_backend(monkeypatch):
    store, _, _ = _credit_world(monkeypatch)
    pay = lambda amount, direction="agency_to_hotel", reference="": agency_statements.PaymentCreate(  # noqa: E731
        amount=amount, direction=direction, paid_at="2026-10-15", reference=reference)

    for bad in (pay(91), pay(10, "hotel_to_agency")):  # overpayment, wrong direction
        with pytest.raises(HTTPException) as exc:
            await agency_statements.record_payment("s1", bad, USER)
        assert exc.value.status_code == 409

    await agency_statements.record_payment("s1", pay(30, reference="EFT-9"), USER)
    again = await agency_statements.record_payment("s1", pay(30, reference="EFT-9"), USER)  # resent request
    assert len(store.docs[0]["payments"]) == 1 and outstanding(again) == 60
    with pytest.raises(HTTPException):
        await agency_statements.record_payment("s1", pay(25, reference="EFT-9"), USER)

    await agency_statements.record_payment("s1", pay(60), USER)
    assert store.docs[0]["status"] == "settled"
    with pytest.raises(HTTPException) as closed:  # closed statement: no extra payment
        await agency_statements.record_payment("s1", pay(10), USER)
    assert closed.value.status_code == 409 and outstanding(store.docs[0]) == 0


class _Rows:
    """Ledger/PMS double: equality, $in, $gte/$lte and $not filters."""

    def __init__(self, rows):
        self.rows = rows

    @classmethod
    def _ok(cls, value, cond):
        if isinstance(cond, dict):
            if "$not" in cond:
                return not cls._ok(value, cond["$not"])
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$gte" in cond and not (value is not None and str(value) >= cond["$gte"]):
                return False
            if "$lte" in cond and not (value is not None and str(value) <= cond["$lte"]):
                return False
            return True
        return value == cond

    def find(self, query, *_a, **_k):
        hits = [dict(r) for r in self.rows if all(self._ok(r.get(k), v) for k, v in query.items())]

        class _Cursor:
            async def to_list(self, _n=None):
                return hits

            def __aiter__(self):
                self._it = iter(hits)
                return self

            async def __anext__(self):
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration from None

        return _Cursor()

    async def update_one(self, query, update, **_k):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                r.update(update["$set"])
        return SimpleNamespace(matched_count=1)


@pytest.mark.asyncio
async def test_statement_period_follows_the_current_pms_date():
    from core.agency_statements import build_statement

    row = {"tenant_id": "t", "agency_id": "a", "status": "confirmed", "currency": "TRY", "total_amount": 100,
           "commission_pct": 10, "payment_terms": "prepaid"}
    ledger = _Rows([
        {**row, "id": "moved-out", "check_in": "2026-10-20", "check_out": "2026-10-22"},   # PMS moved it to November
        {**row, "id": "moved-in", "check_in": "2026-09-05", "check_out": "2026-09-07"},    # PMS moved it into October
        {**row, "id": "last-day", "check_in": "2026-10-31T14:00:00", "check_out": "2026-11-01T11:00:00"},
    ])
    pms = _Rows([
        {**row, "id": "moved-out", "check_in": "2026-11-20", "check_out": "2026-11-22"},
        {**row, "id": "moved-in", "check_in": "2026-10-05", "check_out": "2026-10-07"},
        {**row, "id": "last-day", "check_in": "2026-10-31T14:00:00", "check_out": "2026-11-01T11:00:00"},
    ])
    database = SimpleNamespace(marketplace_bookings=ledger, bookings=pms)
    kwargs = {"tenant_id": "t", "agency_id": "a", "period_start": "2026-10-01", "period_end": "2026-10-31", "currency": "TRY"}
    first = await build_statement(database, **kwargs)
    second = await build_statement(database, **kwargs)
    assert [line["booking_id"] for line in first["lines"]] == ["moved-in", "last-day"]
    assert first == second  # identical reads give identical statements
    november = await build_statement(database, **{**kwargs, "period_start": "2026-11-01", "period_end": "2026-11-30"})
    assert [line["booking_id"] for line in november["lines"]] == ["moved-out"]


@pytest.mark.asyncio
async def test_modifying_a_paid_booking_keeps_its_payment(monkeypatch):
    from core.agency_credit import assert_credit_capacity

    statement = {"id": "s1", "tenant_id": "t1", "agency_id": "a1", "status": "settled", "currency": "TRY",
                 "lines": [{"booking_id": "b1", "agency_owes_hotel": 90}], "totals": {"hotel_owes_agency": 0},
                 "payments": [{"amount": 90, "direction": "agency_to_hotel"}]}
    statements_db = SimpleNamespace(agency_statements=_StatementFinder(_Statements([statement])))
    database = SimpleNamespace(bookings=_Bookings([
        {"id": "b1", "agency_id": "a1", "status": "confirmed", "currency": "TRY", "credit_exposure_amount": 90}]))
    contract = {"credit_limit": 100, "credit_currency": "TRY"}
    # New net 117 replaces b1; 90 of it is already paid, so 27 is new debt.
    await assert_credit_capacity(database, tenant_id="t1", agency_id="a1", contract=contract, booking_currency="TRY",
                                 new_net_exposure=117, exclude_booking_id="b1", statements_db=statements_db)
    with pytest.raises(HTTPException):
        await assert_credit_capacity(database, tenant_id="t1", agency_id="a1", contract=contract, booking_currency="TRY",
                                     new_net_exposure=191, exclude_booking_id="b1", statements_db=statements_db)


@pytest.mark.asyncio
async def test_pms_collection_frees_credit_without_double_counting(monkeypatch):
    from core.agency_credit import assert_credit_capacity

    statements_db = SimpleNamespace(agency_statements=_StatementFinder(_Statements([])))
    booking = {"id": "b1", "agency_id": "a1", "status": "confirmed", "currency": "TRY", "credit_exposure_amount": 6800}
    database = SimpleNamespace(bookings=_Bookings([booking]))
    contract = {"credit_limit": 10000, "credit_currency": "TRY"}

    async def can_sell(amount, **kw):
        try:
            await assert_credit_capacity(database, tenant_id="t1", agency_id="a1", contract=contract, booking_currency="TRY",
                                         new_net_exposure=amount, statements_db=statements_db, **kw)
            return True
        except HTTPException:
            return False

    assert not await can_sell(6800)  # 6800 open + 6800 > 10000
    booking["paid_amount"] = 8000  # guest paid the gross at the hotel (on-arrival terms)
    assert await can_sell(6800)
    booking["paid_amount"] = 3000  # partial collection
    assert await can_sell(6200) and not await can_sell(6201)
    # A modification keeps what was already collected on the booking itself.
    assert await can_sell(10000 + 3000, exclude_booking_id="b1") and not await can_sell(13001, exclude_booking_id="b1")
