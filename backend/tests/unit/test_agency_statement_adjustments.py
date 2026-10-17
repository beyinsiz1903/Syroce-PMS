"""Statement preview (nothing saved) and signed per-line corrections with a reason."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.agency_statements import apply_adjustment, outstanding, statement_totals
from routers import agency_statements as st

USER = SimpleNamespace(id="u", email="ops@hotel.test", tenant_id="t1", role="admin", roles=[])
PREPAID = {"booking_id": "b1", "confirmation_code": "MKT-1", "status": "confirmed", "payment_terms": "prepaid",
           "agency_owes_hotel": 6800.0, "hotel_owes_agency": 0.0, "gross": 8000.0}
ON_ARRIVAL = {"booking_id": "b2", "confirmation_code": "MKT-2", "status": "confirmed", "payment_terms": "on_arrival",
              "agency_owes_hotel": 0.0, "hotel_owes_agency": 1200.0, "gross": 8000.0}


def test_adjustment_is_signed_keeps_the_computed_values_and_can_be_removed():
    less = apply_adjustment(PREPAID, -300, "Erken çıkış indirimi")
    assert (less["agency_owes_hotel"], less["adjustment"]["computed"]["agency_owes_hotel"]) == (6500.0, 6800.0)
    changed = apply_adjustment(less, 200, "Minibar")  # replaces, not stacks
    assert changed["agency_owes_hotel"] == 7000.0
    removed = apply_adjustment(changed, 0, "")
    assert removed["agency_owes_hotel"] == 6800.0 and "adjustment" not in removed
    # Crossing zero moves the line to the other side.
    flipped = apply_adjustment(ON_ARRIVAL, 1500, "Ek ücret")
    assert (flipped["agency_owes_hotel"], flipped["hotel_owes_agency"]) == (300.0, 0.0)
    totals = statement_totals([less, ON_ARRIVAL])
    assert (totals["net_balance"], totals["adjustments"]) == (5300.0, -300.0)


def _match(doc, query):
    for key, cond in query.items():
        value = doc
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else (value[int(part)] if isinstance(value, list) and int(part) < len(value) else None)
        if isinstance(cond, dict) and "$exists" in cond:
            if (value is not None) != cond["$exists"]:
                return False
        elif isinstance(cond, dict) and "$in" in cond:
            if value not in cond["$in"]:
                return False
        elif isinstance(cond, dict) and "$size" in cond:
            if len(value or []) != cond["$size"]:
                return False
        elif value != cond:
            return False
    return True


class _Store:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, query, *_a, **_k):
        return copy.deepcopy(self.doc) if _match(self.doc, query) else None

    async def find_one_and_update(self, query, update, **_k):
        if not _match(self.doc, query):
            return None
        for key, value in update.get("$push", {}).items():
            self.doc.setdefault(key, []).append(value)
        self.doc.update(copy.deepcopy(update.get("$set", {})))
        return copy.deepcopy(self.doc)


@pytest.fixture
def issued(monkeypatch):
    lines = [dict(PREPAID), dict(ON_ARRIVAL)]
    doc = {"id": "s1", "tenant_id": "t1", "agency_id": "a1", "number": "EKS-1", "currency": "TRY", "status": "issued",
           "lines": lines, "totals": statement_totals(lines), "payments": [], "history": [{"event": "issued"}]}
    store = _Store(doc)
    monkeypatch.setattr(st, "get_system_db", lambda: SimpleNamespace(agency_statements=store))
    monkeypatch.setattr(st, "_notify_agency", AsyncMock())
    monkeypatch.setattr(st, "_require_hotel_admin", lambda _u: "t1")
    return store


@pytest.mark.asyncio
async def test_hotel_corrects_one_line_and_the_agency_is_told(issued):
    result = await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="b1", amount=-300, reason="Erken çıkış indirimi"), USER)
    assert result["outstanding"] == 5300.0 and result["totals"]["adjustments"] == -300.0
    line = next(l for l in result["lines"] if l["booking_id"] == "b1")
    assert line["adjustment"]["reason"] == "Erken çıkış indirimi" and line["adjustment"]["by"] == USER.email
    assert result["history"][-1]["event"] == "line_adjusted"
    assert "MKT-1: -300.00 TRY" in st._notify_agency.await_args.args[3]


@pytest.mark.asyncio
async def test_correction_needs_a_reason_and_a_line_of_this_statement(issued):
    with pytest.raises(HTTPException) as no_reason:
        await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="b1", amount=-300, reason="yok"), USER)
    assert no_reason.value.status_code == 422
    with pytest.raises(HTTPException) as other:
        await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="zz", amount=10, reason="Başka satır"), USER)
    assert other.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"status": "agreed"}, {"payments": [{"id": "p", "amount": 1}]}])
async def test_agreed_or_paid_statement_cannot_be_corrected(issued, change):
    issued.doc.update(change)
    with pytest.raises(HTTPException) as exc:
        await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="b1", amount=-300, reason="Erken çıkış"), USER)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_correcting_a_disputed_statement_asks_the_agency_again(issued):
    issued.doc["status"] = "disputed"
    result = await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="b1", amount=-300, reason="İtiraz haklı"), USER)
    assert result["status"] == "resolved"


@pytest.mark.asyncio
@pytest.mark.parametrize("meanwhile", [{"status": "disputed"}, {"revision": 2}])
async def test_concurrent_change_makes_the_correction_miss(issued, monkeypatch, meanwhile):
    stale = copy.deepcopy(issued.doc)
    issued.doc.update(meanwhile)  # agency disputed / another correction after our read
    monkeypatch.setattr(st, "_load", AsyncMock(return_value=stale))
    with pytest.raises(HTTPException) as exc:
        await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="b1", amount=-300, reason="Erken çıkış"), USER)
    assert exc.value.status_code == 409 and "adjustment" not in issued.doc["lines"][0]


@pytest.mark.asyncio
async def test_preview_saves_nothing_and_matches_the_issue(monkeypatch):
    built = {"lines": [dict(PREPAID), dict(ON_ARRIVAL)], "totals": statement_totals([PREPAID, ON_ARRIVAL])}
    inserted = []
    sysdb = SimpleNamespace(
        agency_contracts=SimpleNamespace(find_one=AsyncMock(return_value={"agency_name": "Test", "hotel_name": "Demo"})),
        agency_statements=SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock(side_effect=inserted.append)),
    )
    monkeypatch.setattr(st, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(st, "build_statement", AsyncMock(return_value=copy.deepcopy(built)))
    monkeypatch.setattr(st, "_require_hotel_admin", lambda _u: "t1")
    monkeypatch.setattr(st, "_notify_agency", AsyncMock())
    data = st.StatementCreate(agency_id="a1", period_start="2026-11-01", period_end="2026-11-30",
                              adjustments=[st.LineAdjustment(booking_id="b1", amount=-300, reason="Erken çıkış indirimi")])
    preview = await st.preview_statement(data, USER)
    assert preview["outstanding"] == 5300.0 and inserted == [] and not st._notify_agency.await_count

    async def _next(_db):
        return "EKS-9"

    monkeypatch.setattr(st, "_next_number", _next)

    class _Lock:
        async def insert_one(self, _doc): ...
        async def delete_one(self, _q): ...

    sysdb.agency_statement_locks = _Lock()
    issued = await st.issue_statement(data, USER)
    def _no_time(lines):
        return [{**l, "adjustment": {k: v for k, v in l["adjustment"].items() if k != "at"}} if "adjustment" in l else l for l in lines]

    assert issued["totals"] == preview["totals"] and _no_time(issued["lines"]) == _no_time(preview["lines"])
    assert len(inserted) == 1


@pytest.mark.asyncio
async def test_payment_checked_against_an_old_balance_cannot_settle_a_corrected_statement(issued, monkeypatch):
    """Payment reads 100, the hotel adds +50, the 100 payment must not close it."""
    issued.doc.update(status="agreed", lines=[{**PREPAID, "agency_owes_hotel": 100.0}],
                      totals=statement_totals([{**PREPAID, "agency_owes_hotel": 100.0}]))
    stale = copy.deepcopy(issued.doc)
    issued.doc["status"] = "issued"
    await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="b1", amount=50, reason="Minibar ücreti"), USER)
    issued.doc["status"] = "agreed"  # agency agreed again, to the new version
    monkeypatch.setattr(st, "_load", AsyncMock(return_value=stale))
    with pytest.raises(HTTPException) as exc:
        await st.record_payment("s1", st.PaymentCreate(amount=100, direction="agency_to_hotel", paid_at="2026-11-30"), USER)
    assert exc.value.status_code == 409 and issued.doc["payments"] == [] and outstanding(issued.doc) == 150.0


@pytest.mark.asyncio
async def test_agency_agreement_is_bound_to_the_version_it_saw(issued, monkeypatch):
    agency = {"agency_id": "a1"}
    await st.adjust_statement_line("s1", st.LineAdjustment(booking_id="b1", amount=50, reason="Minibar ücreti"), USER)
    with pytest.raises(HTTPException) as stale:
        await st.agree_statement("s1", st.AgreeRequest(revision=1), agency)
    assert stale.value.status_code == 409 and issued.doc["status"] == "issued"
    monkeypatch.setattr(st, "_notify_hotel", AsyncMock())
    agreed = await st.agree_statement("s1", st.AgreeRequest(revision=2), agency)
    assert agreed["status"] == "agreed" and agreed["history"][-1]["revision"] == 2


@pytest.mark.asyncio
async def test_issue_refuses_a_balance_other_than_the_preview(monkeypatch):
    built = {"lines": [dict(PREPAID)], "totals": statement_totals([PREPAID])}
    sysdb = SimpleNamespace(
        agency_contracts=SimpleNamespace(find_one=AsyncMock(return_value={"agency_name": "Test"})),
        agency_statements=SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock()),
        agency_statement_locks=SimpleNamespace(insert_one=AsyncMock(), delete_one=AsyncMock()),
    )
    monkeypatch.setattr(st, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(st, "build_statement", AsyncMock(return_value=built))
    monkeypatch.setattr(st, "_require_hotel_admin", lambda _u: "t1")
    data = st.StatementCreate(agency_id="a1", period_start="2026-11-01", period_end="2026-11-30", expected_net_balance=6800,
                              adjustments=[st.LineAdjustment(booking_id="b1", amount=-300, reason="Erken çıkış indirimi")])
    with pytest.raises(HTTPException) as exc:  # preview showed 6800, the corrections make 6500
        await st.issue_statement(data, USER)
    assert exc.value.status_code == 409 and not sysdb.agency_statements.insert_one.await_count


@pytest.mark.asyncio
@pytest.mark.parametrize("adjustment,paid,expected_used", [(-300, 6500, 0.0), (-300, 0, 6500.0), (50, 0, 6850.0), (50, 6850, 0.0)])
async def test_credit_follows_the_corrected_statement(adjustment, paid, expected_used):
    from core.agency_credit import credit_usage

    line = apply_adjustment(PREPAID, adjustment, "Düzeltme gerekçesi")
    statement = {"tenant_id": "t1", "agency_id": "a1", "status": "settled" if paid else "agreed",
                 "lines": [line], "totals": statement_totals([line]),
                 "payments": [{"amount": paid, "direction": "agency_to_hotel"}] if paid else []}

    def _cursor(rows):
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))

    database = SimpleNamespace(
        bookings=SimpleNamespace(find=lambda *a, **k: _cursor([{"id": "b1", "currency": "TRY", "credit_exposure_amount": 6800}])),
        payments=SimpleNamespace(find=lambda *a, **k: _cursor([])),
    )
    statements_db = SimpleNamespace(agency_statements=SimpleNamespace(find=lambda *a, **k: _cursor([statement])))
    usage = await credit_usage(database, tenant_id="t1", agency_id="a1",
                               contract={"credit_limit": 10000, "credit_currency": "TRY"}, statements_db=statements_db)
    assert usage["used"] == expected_used


@pytest.mark.asyncio
async def test_surcharge_on_a_booking_paid_in_the_pms_still_uses_credit():
    """100 fully collected in the PMS (payment_status=paid) + 50 added on the
    statement: 50 is owed and must count against the limit."""
    from core.agency_credit import credit_usage

    line = apply_adjustment({**PREPAID, "agency_owes_hotel": 100.0}, 50, "Minibar ücreti")
    statement = {"tenant_id": "t1", "agency_id": "a1", "status": "agreed", "lines": [line],
                 "totals": statement_totals([line]), "payments": []}
    booking = {"id": "b1", "currency": "TRY", "credit_exposure_amount": 100, "payment_status": "paid"}

    def _cursor(rows):
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))

    def _bookings(query, *_a, **_k):
        # Mirrors the filter: a paid booking is only read when named in $or.
        named = any(booking["id"] in (cond.get("id") or {}).get("$in", []) for cond in query.get("$or", []))
        return _cursor([booking] if named else [])

    database = SimpleNamespace(
        bookings=SimpleNamespace(find=_bookings),
        payments=SimpleNamespace(find=lambda *a, **k: _cursor([{"booking_id": "b1", "amount": 100, "method": "cash", "status": "paid"}])),
    )
    statements_db = SimpleNamespace(agency_statements=SimpleNamespace(find=lambda *a, **k: _cursor([statement])))
    usage = await credit_usage(database, tenant_id="t1", agency_id="a1",
                               contract={"credit_limit": 1000, "credit_currency": "TRY"}, statements_db=statements_db)
    assert usage["used"] == 50.0


@pytest.mark.asyncio
async def test_issue_refuses_different_lines_with_the_same_total(monkeypatch):
    previewed = [{**PREPAID, "agency_owes_hotel": 100.0}, {**PREPAID, "booking_id": "b3", "agency_owes_hotel": 100.0}]
    now = [{**PREPAID, "agency_owes_hotel": 150.0}, {**PREPAID, "booking_id": "b3", "agency_owes_hotel": 50.0}]
    signature = st.statement_signature({"lines": previewed, "totals": statement_totals(previewed)})
    sysdb = SimpleNamespace(
        agency_contracts=SimpleNamespace(find_one=AsyncMock(return_value={"agency_name": "Test"})),
        agency_statements=SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock()),
        agency_statement_locks=SimpleNamespace(insert_one=AsyncMock(), delete_one=AsyncMock()),
    )
    monkeypatch.setattr(st, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(st, "build_statement", AsyncMock(return_value={"lines": now, "totals": statement_totals(now)}))
    monkeypatch.setattr(st, "_require_hotel_admin", lambda _u: "t1")
    data = st.StatementCreate(agency_id="a1", period_start="2026-11-01", period_end="2026-11-30",
                              expected_signature=signature, expected_net_balance=200)
    with pytest.raises(HTTPException) as exc:
        await st.issue_statement(data, USER)
    assert exc.value.status_code == 409 and not sysdb.agency_statements.insert_one.await_count


@pytest.mark.asyncio
async def test_charge_on_a_cancelled_booking_uses_credit():
    """Cancelled booking, nothing owed for the stay, +50 on its statement
    line: with a 50 limit a new 50 sale must be refused."""
    from core.agency_credit import assert_credit_capacity, credit_usage

    cancelled = {**PREPAID, "status": "cancelled", "agency_owes_hotel": 0.0}
    line = apply_adjustment(cancelled, 50, "Geç iptal masrafı")
    statement = {"tenant_id": "t1", "agency_id": "a1", "status": "agreed", "lines": [line],
                 "totals": statement_totals([line]), "payments": []}
    booking = {"id": "b1", "status": "cancelled", "currency": "TRY", "credit_exposure_amount": 6800}

    def _cursor(rows):
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))

    def _bookings(query, *_a, **_k):
        named = any(booking["id"] in (cond.get("id") or {}).get("$in", []) for cond in query.get("$or", []))
        return _cursor([booking] if named else [])

    database = SimpleNamespace(bookings=SimpleNamespace(find=_bookings), payments=SimpleNamespace(find=lambda *a, **k: _cursor([])))
    statements_db = SimpleNamespace(agency_statements=SimpleNamespace(find=lambda *a, **k: _cursor([statement])))
    contract = {"credit_limit": 50, "credit_currency": "TRY"}
    usage = await credit_usage(database, tenant_id="t1", agency_id="a1", contract=contract, statements_db=statements_db)
    assert usage["used"] == 50.0  # the statement charge, not the cancelled stay's 6.800
    with pytest.raises(HTTPException) as exc:
        await assert_credit_capacity(database, tenant_id="t1", agency_id="a1", contract=contract,
                                     booking_currency="TRY", new_net_exposure=50, statements_db=statements_db)
    assert exc.value.status_code == 409
