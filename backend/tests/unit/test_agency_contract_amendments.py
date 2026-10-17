"""Amend an approved contract without terminating it: one party proposes,
the other approves or rejects; current terms hold until approval."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import agency_contract_amendments as am
from tests.unit.test_agency_statements_symmetric import _Coll

AGENCY = {"agency_id": "a1", "user": {"email": "acente@example.com"}}
HOTEL = SimpleNamespace(id="u", email="ops@hotel.test", tenant_id="t1", role="admin", roles=[])
CONTRACT = {"id": "c1", "tenant_id": "t1", "agency_id": "a1", "contract_code": "SOZ-1", "agency_name": "Acente", "hotel_name": "Otel",
            "status": "approved", "payment_terms": "prepaid", "commission_pct": 15.0, "contract_type": "commission",
            "cancellation_policy": {"free_until_days_before": 7, "penalty_pct": 50.0, "no_show_penalty_pct": 100.0},
            "valid_from": "2026-10-16", "valid_to": "2027-12-31", "credit_limit": 10000, "credit_currency": "TRY"}


@pytest.fixture
def world(monkeypatch):
    sysdb = SimpleNamespace(agency_contracts=_Coll([CONTRACT]), agency_contract_events=_Coll())
    monkeypatch.setattr(am, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(am, "_require_hotel_user", lambda _u: "t1")
    monkeypatch.setattr(am, "_notify", AsyncMock())
    return sysdb


def _contract(world):
    return world.agency_contracts.rows[0]


@pytest.mark.asyncio
async def test_agency_proposes_pay_at_hotel_and_the_hotel_approves_with_a_new_limit(world):
    proposed = (await am.agency_propose_amendment("c1", am.AmendmentCreate(payment_terms="on_arrival", note="Girişte ödemeye geçelim"), AGENCY))["contract"]
    assert proposed["payment_terms"] == "prepaid"  # current terms hold until approval
    assert proposed["pending_amendment"]["changes"] == {"payment_terms": "on_arrival"}
    assert am._notify.await_args.args[2] == "hotel"
    with pytest.raises(HTTPException) as busy:
        await am.agency_propose_amendment("c1", am.AmendmentCreate(commission_pct=12), AGENCY)
    assert busy.value.status_code == 409
    amendment_id = proposed["pending_amendment"]["id"]
    with pytest.raises(HTTPException) as own:
        await am.agency_approve_amendment("c1", amendment_id, am.AmendmentApprove(), AGENCY)
    assert own.value.status_code == 403

    approved = (await am.hotel_approve_amendment("c1", amendment_id, am.AmendmentApprove(credit_limit=15000, credit_currency="TRY"), HOTEL))["contract"]
    assert (approved["payment_terms"], approved["terms_version"], approved["pending_amendment"]) == ("on_arrival", 2, None)
    assert (approved["credit_limit"], approved["contract_code"], approved["status"]) == (15000, "SOZ-1", "approved")
    record = approved["amendments"][-1]
    assert record["status"] == "approved" and record["previous"] == {"payment_terms": "prepaid", "credit_limit": 10000, "credit_currency": "TRY"}
    assert world.agency_contract_events.rows[-1]["event"] == "amendment_approved"


@pytest.mark.asyncio
async def test_hotel_proposes_the_agency_rejects_with_a_reason(world):
    proposed = (await am.hotel_propose_amendment("c1", am.AmendmentCreate(commission_pct=12), HOTEL))["contract"]
    amendment_id = proposed["pending_amendment"]["id"]
    with pytest.raises(ValueError):  # a reason is mandatory
        am.AmendmentReject(reason="yok")
    with pytest.raises(HTTPException) as no_limit:  # the credit limit stays the hotel's decision
        await am.agency_approve_amendment("c1", amendment_id, am.AmendmentApprove(credit_limit=99999, credit_currency="TRY"), AGENCY)
    assert no_limit.value.status_code == 403
    rejected = (await am.agency_reject_amendment("c1", amendment_id, am.AmendmentReject(reason="%15 kalsın lütfen"), AGENCY))["contract"]
    assert rejected["commission_pct"] == 15.0 and rejected["pending_amendment"] is None
    assert rejected["amendments"][-1]["status"] == "rejected"


@pytest.mark.asyncio
async def test_only_the_proposer_withdraws_and_a_decided_proposal_cannot_be_approved(world):
    proposed = (await am.agency_propose_amendment("c1", am.AmendmentCreate(payment_terms="on_arrival"), AGENCY))["contract"]
    amendment_id = proposed["pending_amendment"]["id"]
    with pytest.raises(HTTPException) as foreign:
        await am.hotel_withdraw_amendment("c1", amendment_id, HOTEL)
    assert foreign.value.status_code == 403
    await am.agency_withdraw_amendment("c1", amendment_id, AGENCY)
    with pytest.raises(HTTPException) as gone:
        await am.hotel_approve_amendment("c1", amendment_id, am.AmendmentApprove(), HOTEL)
    assert gone.value.status_code == 409 and _contract(world)["payment_terms"] == "prepaid"


@pytest.mark.asyncio
async def test_invalid_proposals_are_refused(world):
    with pytest.raises(HTTPException) as same:
        await am.agency_propose_amendment("c1", am.AmendmentCreate(payment_terms="prepaid"), AGENCY)
    assert same.value.status_code == 400
    with pytest.raises(HTTPException) as past:
        await am.agency_propose_amendment("c1", am.AmendmentCreate(valid_from="2025-01-01", valid_to="2025-06-30"), AGENCY)
    assert past.value.status_code == 400
    _contract(world)["contract_type"] = "net_rate"
    with pytest.raises(HTTPException) as net:
        await am.agency_propose_amendment("c1", am.AmendmentCreate(commission_pct=10), AGENCY)
    assert net.value.status_code == 400
    _contract(world).update(contract_type="commission", status="terminated")
    with pytest.raises(HTTPException) as ended:
        await am.agency_propose_amendment("c1", am.AmendmentCreate(payment_terms="on_arrival"), AGENCY)
    assert ended.value.status_code == 409
    with pytest.raises(HTTPException) as foreign:
        await am.agency_propose_amendment("c1", am.AmendmentCreate(payment_terms="on_arrival"), {"agency_id": "other"})
    assert foreign.value.status_code == 404


def test_a_proposal_must_change_something():
    with pytest.raises(ValueError):
        am.AmendmentCreate(note="sadece not")


@pytest.mark.asyncio
async def test_dates_are_checked_again_when_approving(world, monkeypatch):
    """Proposed on the 17th to end on the 18th, approved on the 19th."""
    from datetime import UTC, datetime

    clock = {"now": datetime(2026, 10, 17, 9, 0, tzinfo=UTC)}

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    monkeypatch.setattr(am, "datetime", _Clock)
    proposed = (await am.agency_propose_amendment("c1", am.AmendmentCreate(valid_to="2026-10-18"), AGENCY))["contract"]
    clock["now"] = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
    with pytest.raises(HTTPException) as late:
        await am.hotel_approve_amendment("c1", proposed["pending_amendment"]["id"], am.AmendmentApprove(), HOTEL)
    assert late.value.status_code == 409 and _contract(world)["valid_to"] == "2027-12-31"
