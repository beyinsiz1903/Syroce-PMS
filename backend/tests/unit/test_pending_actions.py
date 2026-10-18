"""Pending work per Agency Extranet party: who must act, on what."""

from datetime import date

import pytest

from core.pending_actions import contract_items, pending_actions, statement_items

TODAY = date(2026, 10, 18)


def owners(items):
    return [(i["kind"], i["owner"]) for i in items]


def statement(**extra):
    base = {"id": "s1", "number": "EKS-2026-0001", "tenant_id": "t1", "agency_id": "a1", "agency_name": "Acente",
            "hotel_name": "Otel", "currency": "TRY", "status": "issued", "revision": 1,
            "agreements": {"hotel": 1, "agency": None}, "lines": [], "totals": {"net_balance": 1000.0},
            "payments": [], "payment_notices": []}
    return {**base, **extra}


def test_contract_request_is_the_hotels_to_decide():
    contract = {"id": "c1", "contract_code": "SOZ-1", "status": "pending", "agency_name": "Acente", "hotel_name": "Otel"}
    assert owners(contract_items(contract, "hotel")) == [("contract_request", "yours")]
    assert owners(contract_items(contract, "agency")) == [("contract_request", "theirs")]


def test_amendment_is_for_the_side_that_did_not_propose_it():
    contract = {"id": "c1", "contract_code": "SOZ-1", "status": "approved",
                "pending_amendment": {"proposed_by_side": "agency", "proposed_at": "2026-10-10", "changes": {"payment_terms": "on_arrival"}}}
    assert owners(contract_items(contract, "hotel")) == [("contract_amendment", "yours")]
    assert owners(contract_items(contract, "agency")) == [("contract_amendment", "theirs")]


def test_statement_approval_follows_the_current_revision():
    issued = statement()                              # hotel issued and agreed to rev 1
    assert owners(statement_items(issued, "agency", TODAY)) == [("statement_approval", "yours")]
    assert owners(statement_items(issued, "hotel", TODAY)) == [("statement_approval", "theirs")]
    corrected = statement(revision=2)                 # a line correction: both must agree again
    assert owners(statement_items(corrected, "hotel", TODAY)) == [("statement_approval", "yours")]


def test_dispute_is_answered_by_the_other_side():
    disputed = statement(status="disputed", dispute={"by_side": "agency", "reason": "fark", "at": "2026-10-11"})
    assert owners(statement_items(disputed, "hotel", TODAY)) == [("dispute", "yours")]
    assert owners(statement_items(disputed, "agency", TODAY)) == [("dispute", "theirs")]


def test_payment_notice_is_verified_by_the_payee_and_hides_the_payment_item():
    notice = {"id": "n1", "status": "pending", "direction": "agency_to_hotel", "amount": 400, "reference": "EFT-1"}
    agreed = statement(status="agreed", agreements={"hotel": 1, "agency": 1}, payment_notices=[notice])
    assert owners(statement_items(agreed, "hotel", TODAY)) == [("payment_notice", "yours")]
    assert owners(statement_items(agreed, "agency", TODAY)) == [("payment_notice", "theirs")]


def test_open_balance_is_the_debtors_to_pay_with_its_due_date():
    agreed = statement(status="agreed", agreements={"hotel": 1, "agency": 1}, agreed_at="2026-10-01",
                       lines=[{"payment_terms": "net_7"}])
    [mine] = statement_items(agreed, "agency", TODAY)
    assert (mine["kind"], mine["owner"], mine["amount"], mine["due_date"], mine["overdue"]) == ("payment", "yours", 1000.0, "2026-10-08", True)
    assert owners(statement_items(agreed, "hotel", TODAY)) == [("payment", "theirs")]
    hotel_owes = statement(status="agreed", agreements={"hotel": 1, "agency": 1}, totals={"net_balance": -250.0}, agreed_at="2026-10-17")
    assert owners(statement_items(hotel_owes, "hotel", TODAY)) == [("payment", "yours")]


def test_settled_and_void_statements_have_nothing_pending():
    assert statement_items(statement(status="settled"), "hotel", TODAY) == []
    assert statement_items(statement(status="void"), "agency", TODAY) == []


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration from None


class _Coll:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def find(self, query, _projection=None):
        self.queries.append(query)
        scope = {k: v for k, v in query.items() if k in ("tenant_id", "agency_id")}
        return _Cursor([d for d in self.docs if all(d.get(k) == v for k, v in scope.items())])


@pytest.mark.asyncio
async def test_lists_split_yours_and_theirs_scoped_to_the_party():
    from types import SimpleNamespace

    db = SimpleNamespace(
        agency_contracts=_Coll([{"id": "c1", "contract_code": "SOZ-1", "status": "pending", "tenant_id": "t1", "agency_id": "a1"},
                                {"id": "c2", "contract_code": "SOZ-2", "status": "pending", "tenant_id": "t2", "agency_id": "a1"}]),
        agency_statements=_Coll([statement(), statement(id="s2", tenant_id="t2")]),
    )
    hotel = await pending_actions(db, side="hotel", scope={"tenant_id": "t1"}, today=TODAY)
    assert hotel["counts"] == {"yours": 1, "theirs": 1, "overdue": 0}
    assert {i["kind"] for i in hotel["yours"]} == {"contract_request"}
    agency = await pending_actions(db, side="agency", scope={"agency_id": "a1"}, today=TODAY)
    assert agency["counts"]["yours"] == 2 and agency["counts"]["theirs"] == 2
    with pytest.raises(ValueError):
        await pending_actions(db, side="x", scope={}, today=TODAY)
