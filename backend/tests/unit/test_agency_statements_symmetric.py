"""Either party issues; both must agree to the same revision; the payer
reports, the party owed verifies; the monthly job issues as "system"."""

import copy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.agency_statements import statement_totals
from routers import agency_statements as st

HOTEL = SimpleNamespace(id="u", email="ops@hotel.test", tenant_id="t1", role="admin", roles=[])
AGENCY = {"agency_id": "a1", "user": {"email": "acente@example.com"}}
COMMISSION = {"booking_id": "b1", "confirmation_code": "MKT-1", "status": "confirmed", "payment_terms": "on_arrival",
              "check_in": "2026-11-21", "gross": 8000.0, "commission": 1200.0, "agency_owes_hotel": 0.0, "hotel_owes_agency": 1200.0}


def _get(doc, key):
    for part in key.split("."):
        if isinstance(doc, list):
            if part.isdigit():
                doc = doc[int(part)] if int(part) < len(doc) else None
            else:  # array field: the values of every element
                doc = [item.get(part) if isinstance(item, dict) else None for item in doc]
        else:
            doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def _match(doc, query):
    for key, cond in query.items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        value = _get(doc, key)
        if isinstance(cond, dict) and "$exists" in cond:
            if (value is not None) != cond["$exists"]:
                return False
        elif isinstance(cond, dict) and "$type" in cond:
            if not isinstance(value, str):
                return False
        elif isinstance(cond, dict) and "$in" in cond:
            values = value if isinstance(value, list) else [value]
            if not any(v in cond["$in"] for v in values):
                return False
        elif isinstance(cond, dict) and "$elemMatch" in cond:
            if not any(_match(item, cond["$elemMatch"]) for item in value or []):
                return False
        elif isinstance(cond, dict) and ("$lte" in cond or "$gte" in cond or "$ne" in cond or "$nin" in cond):
            if "$lte" in cond and not (value is not None and value <= cond["$lte"]):
                return False
            if "$gte" in cond and not (value is not None and value >= cond["$gte"]):
                return False
            if "$ne" in cond and value == cond["$ne"]:
                return False
            if "$nin" in cond and value in cond["$nin"]:
                return False
        elif value != cond:
            return False
    return True


class _Coll:
    def __init__(self, rows=()):
        self.rows = [copy.deepcopy(r) for r in rows]

    async def find_one(self, query, *_a, **_k):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, query)), None)

    def find(self, query, *_a, **_k):
        rows = [copy.deepcopy(r) for r in self.rows if _match(r, query)]

        class _Cur:
            def sort(self, *_a, **_k):
                return self

            async def to_list(self, _n):
                return rows

            def __aiter__(self):
                self._it = iter(rows)
                return self

            async def __anext__(self):
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration from None

        return _Cur()

    async def insert_one(self, doc):
        self.rows.append(copy.deepcopy(doc))

    async def delete_one(self, _query):
        return SimpleNamespace(deleted_count=1)

    async def find_one_and_update(self, query, update, array_filters=None, **_k):
        for doc in self.rows:
            if not _match(doc, query):
                continue
            for key, value in update.get("$set", {}).items():
                if ".$[n]." in key:
                    field, attr = key.split(".$[n].")
                    flt = {k[2:]: v for k, v in array_filters[0].items()}
                    for item in doc[field]:
                        if _match(item, flt):
                            item[attr] = value
                elif ".$." in key:
                    field, attr = key.split(".$.")
                    item = next(i for i in doc[field] if _match(i, query[field]["$elemMatch"]))
                    item[attr] = value
                else:
                    doc[key] = copy.deepcopy(value)
            for key, value in update.get("$push", {}).items():
                doc.setdefault(key, []).append(copy.deepcopy(value))
            return copy.deepcopy(doc)
        return None


@pytest.fixture
def world(monkeypatch):
    sysdb = SimpleNamespace(
        agency_statements=_Coll(), agency_statement_locks=_Coll(),
        agency_contracts=_Coll([{"tenant_id": "t1", "agency_id": "a1", "contract_code": "SOZ-1", "agency_name": "Acente",
                                 "hotel_name": "Otel", "created_at": "2026-10-01"}]),
        counters=SimpleNamespace(find_one_and_update=AsyncMock(return_value={"seq": 7})),
    )
    monkeypatch.setattr(st, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(st, "_require_hotel_admin", lambda _u: "t1")
    monkeypatch.setattr(st, "build_statement", AsyncMock(return_value={"lines": [dict(COMMISSION)], "totals": statement_totals([COMMISSION])}))
    monkeypatch.setattr(st, "_notify_agency", AsyncMock())
    monkeypatch.setattr(st, "_notify_hotel", AsyncMock())
    return sysdb


def _period(**extra):
    return {"period_start": "2026-11-01", "period_end": "2026-11-30", "currency": "TRY", **extra}


async def _agency_issues():
    return await st.agency_issue_statement(st.AgencyStatementCreate(tenant_id="t1", **_period()), AGENCY)


@pytest.mark.asyncio
async def test_agency_issues_its_commission_statement_and_the_hotel_agrees(world):
    issued = await _agency_issues()
    assert (issued["issuer"], issued["status"], issued["agreements"]) == ("agency", "issued", {"hotel": None, "agency": 1})
    assert issued["outstanding"] == -1200.0  # the hotel owes the agency
    st._notify_hotel.assert_awaited()  # the hotel is asked to agree
    with pytest.raises(HTTPException) as again:  # the issuer already agreed
        await st.agree_statement(issued["id"], st.AgreeRequest(revision=1), AGENCY)
    assert again.value.status_code == 409
    agreed = await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=1), HOTEL)
    assert agreed["status"] == "agreed" and agreed["agreements"] == {"hotel": 1, "agency": 1}


@pytest.mark.asyncio
async def test_hotel_reports_its_commission_payment_and_the_agency_verifies(world):
    issued = await _agency_issues()
    await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=1), HOTEL)
    payment = st.PaymentCreate(amount=1200, direction="hotel_to_agency", paid_at="2026-10-16", reference="EFT-9")
    with pytest.raises(HTTPException) as payer:  # the payer cannot mark its own payment as received
        await st.record_payment(issued["id"], payment, HOTEL)
    assert payer.value.status_code == 409
    with pytest.raises(HTTPException) as wrong_side:  # the agency owes nothing here
        await st.report_payment(issued["id"], amount=10, paid_at="2026-10-16", reference="EFT-1", method="x", proof=None, agency=AGENCY)
    assert wrong_side.value.status_code == 409
    reported = await st.hotel_report_payment(issued["id"], amount=1200, paid_at="2026-10-16", reference="EFT-9",
                                             method="bank_transfer", proof=None, current_user=HOTEL)
    notice = reported["payment_notices"][0]
    assert (notice["direction"], notice["status"], reported["outstanding"]) == ("hotel_to_agency", "pending", -1200.0)
    with pytest.raises(HTTPException) as not_receiver:
        await st.verify_payment_notice(issued["id"], notice["id"], st.NoticeDecision(), HOTEL)
    assert not_receiver.value.status_code == 403
    settled = await st.agency_verify_payment_notice(issued["id"], notice["id"], st.NoticeDecision(), AGENCY)
    assert settled["status"] == "settled" and settled["payments"][0]["recorded_by_side"] == "agency"


@pytest.mark.asyncio
async def test_the_party_owed_may_record_money_received_directly(world):
    issued = await _agency_issues()
    await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=1), HOTEL)
    received = await st.agency_record_payment(
        issued["id"], st.PaymentCreate(amount=1200, direction="hotel_to_agency", paid_at="2026-10-16", reference="EFT-2"), AGENCY)
    assert received["status"] == "settled"


@pytest.mark.asyncio
async def test_dispute_resolve_and_void_follow_the_issuer(world):
    issued = await _agency_issues()
    with pytest.raises(HTTPException):  # the issuer corrects or voids, it does not dispute itself
        await st.dispute_statement(issued["id"], st.DisputeCreate(reason="Kendi ekstrem"), AGENCY)
    with pytest.raises(HTTPException) as foreign_void:
        await st.void_statement(issued["id"], st.ResolveRequest(note="Bizim değil"), HOTEL)
    assert foreign_void.value.status_code == 403
    disputed = await st.hotel_dispute_statement(issued["id"], st.DisputeCreate(reason="Komisyon %12 olmalı", booking_ids=["b1"]), HOTEL)
    assert disputed["status"] == "disputed" and disputed["dispute"]["by_side"] == "hotel"
    with pytest.raises(HTTPException):  # the disputing party does not answer itself
        await st.resolve_dispute(issued["id"], st.ResolveRequest(note="Kendime yanıt"), HOTEL)
    corrected = await st.agency_adjust_statement_line(
        issued["id"], st.LineAdjustment(booking_id="b1", amount=240, reason="Komisyon %12'ye düzeltildi"), AGENCY)
    assert (corrected["status"], corrected["revision"], corrected["agreements"]) == ("resolved", 2, {"agency": 2, "hotel": None})
    assert corrected["outstanding"] == -960.0
    agreed = await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=2), HOTEL)
    assert agreed["status"] == "agreed"
    with pytest.raises(HTTPException) as approved:  # the hotel approved it: the agency cannot void it any more
        await st.agency_void_statement(issued["id"], st.ResolveRequest(note="Yeniden düzenlenecek"), AGENCY)
    assert approved.value.status_code == 409


@pytest.mark.asyncio
async def test_agency_voids_its_statement_while_the_hotel_has_not_acted(world):
    issued = await _agency_issues()
    voided = await st.agency_void_statement(issued["id"], st.ResolveRequest(note="Yeniden düzenlenecek"), AGENCY)
    assert voided["status"] == "void"


@pytest.mark.asyncio
async def test_system_statement_needs_both_parties(world):
    issued = await st._issue(world, "t1", st.StatementCreate(agency_id="a1", **_period()), issuer="system", actor="system")
    assert issued["agreements"] == {"hotel": None, "agency": None}
    half = await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=1), HOTEL)
    assert half["status"] == "issued"
    corrected = await st.agency_adjust_statement_line(
        issued["id"], st.LineAdjustment(booking_id="b1", amount=100, reason="Ek ücret yansıtıldı"), AGENCY)
    assert corrected["agreements"] == {"agency": 2, "hotel": None}  # the hotel's earlier agreement no longer counts
    done = await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=2), HOTEL)
    assert done["status"] == "agreed"


@pytest.mark.asyncio
async def test_statement_issued_before_this_change_still_works(world):
    legacy = {"id": "old", "tenant_id": "t1", "agency_id": "a1", "number": "EKS-1", "currency": "TRY", "status": "issued",
              "lines": [dict(COMMISSION)], "totals": statement_totals([COMMISSION]), "payments": [], "history": []}
    world.agency_statements.rows.append(legacy)
    agreed = await st.agree_statement("old", st.AgreeRequest(revision=1), AGENCY)
    assert agreed["status"] == "agreed" and agreed["issuer"] == "hotel" and agreed["agreements"] == {"hotel": 1, "agency": 1}


@pytest.mark.asyncio
async def test_monthly_job_issues_once_per_hotel_agency_and_skips_what_exists(world):
    world.marketplace_bookings = _Coll([{"tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "check_in": "2026-11-21"},
                                        {"tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "check_in": "2026-10-02"}])
    world.bookings = _Coll([{"tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "check_in": "2026-11-20T14:00:00",
                             "agency_completion": {"kind": "marketplace"}}])
    first = await st.auto_issue_previous_month(world, date(2026, 12, 1))
    assert (first["period_start"], first["period_end"], len(first["issued"]), first["failed"]) == ("2026-11-01", "2026-11-30", 1, [])
    made = world.agency_statements.rows[0]
    assert made["issuer"] == "system" and made["agreements"] == {"hotel": None, "agency": None}
    assert st._notify_hotel.await_args.kwargs["database"] is world  # scheduled job: explicit handle
    again = await st.auto_issue_previous_month(world, date(2026, 12, 1))
    assert again["issued"] == [] and again["skipped"] == 1 and len(world.agency_statements.rows) == 1


@pytest.mark.asyncio
async def test_monthly_job_skips_a_period_with_nothing_owed(world, monkeypatch):
    cancelled = {**COMMISSION, "status": "cancelled", "gross": 0.0, "commission": 0.0, "hotel_owes_agency": 0.0}
    monkeypatch.setattr(st, "build_statement", AsyncMock(return_value={"lines": [cancelled], "totals": statement_totals([cancelled])}))
    world.marketplace_bookings = _Coll([{"tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "check_in": "2026-11-21"}])
    world.bookings = _Coll()
    result = await st.auto_issue_previous_month(world, date(2026, 12, 1))
    assert result["issued"] == [] and result["skipped"] == 1 and world.agency_statements.rows == []


def test_uncovered_ranges():
    assert st.uncovered_ranges("2026-11-01", "2026-11-30", []) == [("2026-11-01", "2026-11-30")]
    assert st.uncovered_ranges("2026-11-01", "2026-11-30", [("2026-11-01", "2026-11-07")]) == [("2026-11-08", "2026-11-30")]
    assert st.uncovered_ranges("2026-11-01", "2026-11-30", [("2026-10-20", "2026-11-05"), ("2026-11-10", "2026-11-12")]) == [
        ("2026-11-06", "2026-11-09"), ("2026-11-13", "2026-11-30")]
    assert st.uncovered_ranges("2026-11-01", "2026-11-30", [("2026-10-01", "2026-12-31")]) == []


@pytest.mark.asyncio
async def test_monthly_job_bills_the_rest_of_a_partly_covered_month(world):
    world.agency_statements.rows.append({"id": "old", "tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "status": "agreed",
                                         "period_start": "2026-11-01", "period_end": "2026-11-07", "lines": [], "payments": []})
    world.marketplace_bookings = _Coll([{"tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "check_in": "2026-11-20"}])
    world.bookings = _Coll()
    result = await st.auto_issue_previous_month(world, date(2026, 12, 1))
    assert len(result["issued"]) == 1 and result["failed"] == []
    made = world.agency_statements.rows[-1]
    assert (made["period_start"], made["period_end"]) == ("2026-11-08", "2026-11-30")
    again = await st.auto_issue_previous_month(world, date(2026, 12, 1))
    assert again["issued"] == [] and again["skipped"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("hotel_agrees", [False, True])
async def test_agency_discount_frees_credit_only_once_the_hotel_agrees(world, hotel_agrees):
    """10.000 owed; the agency proposes -10.000: until the hotel agrees,
    the credit control still counts 10.000."""
    from core.agency_credit import credit_usage

    prepaid = {**COMMISSION, "payment_terms": "prepaid", "hotel_owes_agency": 0.0, "agency_owes_hotel": 10000.0}
    st.build_statement.return_value = {"lines": [prepaid], "totals": statement_totals([prepaid])}
    issued = await st.agency_issue_statement(st.AgencyStatementCreate(
        tenant_id="t1", **_period(), adjustments=[st.LineAdjustment(booking_id="b1", amount=-10000, reason="Tamamı indirim")]), AGENCY)
    if hotel_agrees:
        await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=1), HOTEL)

    def _cursor(rows):
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))

    database = SimpleNamespace(
        bookings=SimpleNamespace(find=lambda *a, **k: _cursor([{"id": "b1", "currency": "TRY", "credit_exposure_amount": 10000}])),
        payments=SimpleNamespace(find=lambda *a, **k: _cursor([])),
    )
    usage = await credit_usage(database, tenant_id="t1", agency_id="a1",
                               contract={"credit_limit": 10000, "credit_currency": "TRY"}, statements_db=world)
    assert usage["used"] == (0.0 if hotel_agrees else 10000.0)



def _credit_db(bookings):
    def _cursor(rows):
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))

    def _find(query, *_a, **_k):
        named = {b for cond in query.get("$or", []) for b in (cond.get("id") or {}).get("$in", [])}
        return _cursor([b for b in bookings if b["status"] != "cancelled" or b["id"] in named])

    return SimpleNamespace(bookings=SimpleNamespace(find=_find), payments=SimpleNamespace(find=lambda *a, **k: _cursor([])))


async def _used(world, bookings):
    from core.agency_credit import credit_usage

    usage = await credit_usage(_credit_db(bookings), tenant_id="t1", agency_id="a1",
                               contract={"credit_limit": 20000, "credit_currency": "TRY"}, statements_db=world)
    return usage["used"]


@pytest.mark.asyncio
async def test_agency_cannot_remove_a_charge_the_hotel_added(world):
    prepaid = {**COMMISSION, "payment_terms": "prepaid", "hotel_owes_agency": 0.0, "agency_owes_hotel": 10000.0}
    st.build_statement.return_value = {"lines": [prepaid], "totals": statement_totals([prepaid])}
    booking = [{"id": "b1", "status": "confirmed", "currency": "TRY", "credit_exposure_amount": 10000}]
    issued = await st.issue_statement(st.StatementCreate(agency_id="a1", **_period()), HOTEL)
    await st.adjust_statement_line(issued["id"], st.LineAdjustment(booking_id="b1", amount=5000, reason="Hasar bedeli"), HOTEL)
    assert await _used(world, booking) == 15000.0
    await st.agency_adjust_statement_line(issued["id"], st.LineAdjustment(booking_id="b1", amount=0, reason=""), AGENCY)
    assert await _used(world, booking) == 15000.0  # the hotel has not agreed to the removal
    await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=3), HOTEL)
    assert await _used(world, booking) == 10000.0


@pytest.mark.asyncio
async def test_agency_cannot_void_away_a_hotel_charge(world):
    prepaid = {**COMMISSION, "payment_terms": "prepaid", "hotel_owes_agency": 0.0, "agency_owes_hotel": 10000.0}
    st.build_statement.return_value = {"lines": [prepaid], "totals": statement_totals([prepaid])}
    issued = await _agency_issues()
    await st.adjust_statement_line(issued["id"], st.LineAdjustment(booking_id="b1", amount=5000, reason="Hasar bedeli"), HOTEL)
    with pytest.raises(HTTPException) as exc:
        await st.agency_void_statement(issued["id"], st.ResolveRequest(note="Yeniden düzenlenecek"), AGENCY)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_cancellation_penalty_stays_in_credit_until_the_hotel_agrees_to_a_discount(world):
    penalty = {**COMMISSION, "status": "cancelled", "payment_terms": "prepaid", "gross": 10000.0, "penalty": 10000.0,
               "commission": 0.0, "hotel_owes_agency": 0.0, "agency_owes_hotel": 10000.0}
    st.build_statement.return_value = {"lines": [penalty], "totals": statement_totals([penalty])}
    booking = [{"id": "b1", "status": "cancelled", "currency": "TRY", "credit_exposure_amount": 20000}]
    issued = await _agency_issues()  # with the penalty, then the agency proposes -10.000
    await st.agency_adjust_statement_line(issued["id"], st.LineAdjustment(booking_id="b1", amount=-10000, reason="Ceza affı talebi"), AGENCY)
    assert await _used(world, booking) == 10000.0
    await st.hotel_agree_statement(issued["id"], st.AgreeRequest(revision=2), HOTEL)
    assert await _used(world, booking) == 0.0
