"""Task #239 — corporate-contract approval state-machine endpoint guard.

Targeted unit coverage (no live server) for
``transition_corporate_contract_approval`` in
``backend/domains/revenue/rms_router/sales.py``. Task #234 covered the React UI;
these tests lock in the server-side guard that actually protects the data:

  * a rejection without a non-empty reason is refused with 400;
  * invalid ``to_status`` values are refused with 400;
  * disallowed state-machine hops (e.g. approved → pending) are refused with 409;
  * a valid approve/reject persists ``approval_status`` and appends an
    ``approval_history`` entry (from/to_status, reason, by, at), tenant-scoped;
  * a contract owned by another tenant is invisible (404) — no cross-tenant write.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import domains.revenue.rms_router.sales as sales
from domains.revenue.rms_router.sales import (
    ContractApprovalTransition,
    transition_corporate_contract_approval,
)


class _FakeContracts:
    """Minimal tenant-scoped stand-in for db.corporate_contracts.

    Supports the only two operations the endpoint uses — ``find_one`` and
    ``update_one`` — against an in-memory list, applying ``$set``/``$push`` so
    persistence and history appends can be asserted directly.
    """

    def __init__(self, docs):
        self.docs = docs

    @staticmethod
    def _matches(doc, flt):
        return all(doc.get(k) == v for k, v in flt.items())

    async def find_one(self, flt, *args, **kwargs):
        for doc in self.docs:
            if self._matches(doc, flt):
                return doc
        return None

    async def update_one(self, flt, update):
        for doc in self.docs:
            if self._matches(doc, flt):
                for k, v in update.get("$set", {}).items():
                    doc[k] = v
                for k, v in update.get("$push", {}).items():
                    doc.setdefault(k, []).append(v)
                return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)


def _contract(**over):
    base = {
        "id": "c-1",
        "tenant_id": "t-1",
        "company_name": "Acme A.Ş.",
        "rate_code": "CORP10",
        "contact_email": "owner@example.invalid",
        "approval_status": "draft",
        "approval_history": [],
    }
    base.update(over)
    return base


@pytest.fixture
def env(monkeypatch):
    """Wire the endpoint to an in-memory store + a fixed t-1 caller.

    Email notification is stubbed so terminal transitions don't touch the
    mail provider; the state machine is what's under test here.
    """
    docs = []
    fake_db = MagicMock()
    fake_db.corporate_contracts = _FakeContracts(docs)
    monkeypatch.setattr(sales, "db", fake_db)

    user = MagicMock(tenant_id="t-1", username="boss")
    monkeypatch.setattr(sales, "get_current_user", AsyncMock(return_value=user))
    monkeypatch.setattr(
        sales, "_notify_contract_owner_approval", AsyncMock(return_value=True))
    return docs


async def _call(to_status, reason=None, contract_id="c-1"):
    return await transition_corporate_contract_approval(
        contract_id,
        ContractApprovalTransition(to_status=to_status, reason=reason),
        credentials=None,
        _perm=None,
    )


# ── Validation guards ────────────────────────────────────────────


async def test_unknown_contract_returns_404(env):
    with pytest.raises(HTTPException) as exc:
        await _call("pending", contract_id="missing")
    assert exc.value.status_code == 404


async def test_reject_without_reason_is_400(env):
    env.append(_contract(approval_status="pending"))
    for reason in (None, "", "   "):
        with pytest.raises(HTTPException) as exc:
            await _call("rejected", reason=reason)
        assert exc.value.status_code == 400
    # the contract is untouched — still pending, no history appended
    assert env[0]["approval_status"] == "pending"
    assert env[0]["approval_history"] == []


async def test_invalid_to_status_is_400(env):
    env.append(_contract(approval_status="draft"))
    for bad in ("done", "cancelled", "", "  ", "garbage"):
        with pytest.raises(HTTPException) as exc:
            await _call(bad)
        assert exc.value.status_code == 400
    assert env[0]["approval_status"] == "draft"
    assert env[0]["approval_history"] == []


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("draft", "approved"),   # skip pending
        ("draft", "rejected"),   # skip pending
        ("pending", "draft"),    # no reopen to draft from pending
        ("approved", "pending"), # terminal — no outgoing hops
        ("approved", "draft"),
        ("rejected", "approved"),  # rejected only resubmits to draft
    ],
)
async def test_disallowed_transition_is_409(env, from_status, to_status):
    env.append(_contract(approval_status=from_status))
    reason = "x" if to_status == "rejected" else None
    with pytest.raises(HTTPException) as exc:
        await _call(to_status, reason=reason)
    assert exc.value.status_code == 409
    # state machine refused the hop — nothing persisted
    assert env[0]["approval_status"] == from_status
    assert env[0]["approval_history"] == []


# ── Happy-path persistence + history ─────────────────────────────


async def test_valid_submit_persists_status_and_history(env):
    env.append(_contract(approval_status="draft"))
    res = await _call("pending")

    assert res["from_status"] == "draft"
    assert res["approval_status"] == "pending"
    assert env[0]["approval_status"] == "pending"
    assert env[0]["updated_by"] == "boss"

    hist = env[0]["approval_history"]
    assert len(hist) == 1
    entry = hist[0]
    assert entry["from_status"] == "draft"
    assert entry["to_status"] == "pending"
    assert entry["by"] == "boss"
    assert entry["at"]  # ISO timestamp recorded


async def test_valid_approve_persists_and_appends(env):
    env.append(_contract(approval_status="pending"))
    res = await _call("approved")

    assert res["approval_status"] == "approved"
    assert env[0]["approval_status"] == "approved"
    hist = env[0]["approval_history"]
    assert len(hist) == 1
    assert hist[0]["to_status"] == "approved"
    assert hist[0]["by"] == "boss"


async def test_valid_reject_with_reason_records_reason(env):
    env.append(_contract(approval_status="pending"))
    res = await _call("rejected", reason="Fiyatlar bütçeyi aşıyor.")

    assert res["approval_status"] == "rejected"
    assert env[0]["approval_status"] == "rejected"
    entry = env[0]["approval_history"][-1]
    assert entry["to_status"] == "rejected"
    assert entry["reason"] == "Fiyatlar bütçeyi aşıyor."


async def test_to_status_is_normalised(env):
    """Surrounding whitespace / case is normalised before the machine runs."""
    env.append(_contract(approval_status="draft"))
    res = await _call("  Pending  ")
    assert res["approval_status"] == "pending"
    assert env[0]["approval_status"] == "pending"


async def test_history_accumulates_across_transitions(env):
    env.append(_contract(approval_status="draft"))
    await _call("pending")
    await _call("rejected", reason="needs rework")
    await _call("draft")  # resubmit cycle
    await _call("pending")
    await _call("approved")

    statuses = [h["to_status"] for h in env[0]["approval_history"]]
    assert statuses == ["pending", "rejected", "draft", "pending", "approved"]
    assert env[0]["approval_status"] == "approved"


# ── Tenant scoping ───────────────────────────────────────────────


async def test_other_tenant_contract_is_invisible(env):
    """A caller in t-1 cannot transition (or even see) a t-2 contract."""
    env.append(_contract(id="c-foreign", tenant_id="t-2",
                         approval_status="pending"))
    with pytest.raises(HTTPException) as exc:
        await _call("approved", contract_id="c-foreign")
    assert exc.value.status_code == 404
    # foreign contract untouched
    assert env[0]["approval_status"] == "pending"
    assert env[0]["approval_history"] == []


async def test_update_is_tenant_scoped(env, monkeypatch):
    """The persisting update_one filter carries the caller's tenant_id."""
    env.append(_contract(approval_status="draft"))
    captured = {}
    real = sales.db.corporate_contracts.update_one

    async def _spy(flt, update):
        captured["flt"] = flt
        return await real(flt, update)

    monkeypatch.setattr(sales.db.corporate_contracts, "update_one", _spy)
    await _call("pending")
    assert captured["flt"]["tenant_id"] == "t-1"
    assert captured["flt"]["id"] == "c-1"
