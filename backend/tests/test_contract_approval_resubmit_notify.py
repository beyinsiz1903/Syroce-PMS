"""Backend tests for approver notification on contract resubmit (Task #230).

When an owner resubmits a rejected corporate contract (rejected → draft →
pending), the people who can approve it must be alerted. This locks in
``_notify_approvers_of_resubmit`` and the resubmit detection inside
``transition_corporate_contract_approval`` in
``backend/domains/revenue/rms_router/sales.py``:

1. A draft → pending hop with a prior rejection in history fires the approver
   alert; a fresh draft → pending (no prior rejection) does NOT.
2. The in-app notification is tenant-scoped and role-targeted to the approver
   roles (whoever holds VIEW_COMPANIES), with a link to the approvals page.
3. One e-mail per active approver-role user; the resubmitter is skipped and
   invalid e-mails are skipped.
4. Both channels are best-effort — a provider/DB failure never raises.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import email as core_email
import domains.revenue.rms_router.sales as sales
from domains.revenue.rms_router.sales import (
    ContractApprovalTransition,
    transition_corporate_contract_approval,
)


# ── Fakes ────────────────────────────────────────────────────────


class _FakeContracts:
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


class _FakeNotifications:
    def __init__(self):
        self.inserted: list[dict] = []

    async def insert_one(self, doc):
        self.inserted.append(doc)
        return MagicMock(inserted_id="x")


class _FakeUsersCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return list(self._docs[:n])


class _FakeUsers:
    def __init__(self, docs):
        self.docs = docs
        self.last_query = None

    def find(self, query, projection=None):
        self.last_query = query
        out = []
        for d in self.docs:
            ok = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
                        ok = False
                        break
                elif d.get(k) != v:
                    ok = False
                    break
            if ok:
                out.append(d)
        return _FakeUsersCursor(out)


def _contract(**over):
    base = {
        "id": "c-1",
        "tenant_id": "t-1",
        "company_name": "Acme A.Ş.",
        "rate_code": "CORP10",
        "contact_email": "owner@example.com",
        "approval_status": "draft",
        "approval_history": [],
    }
    base.update(over)
    return base


@pytest.fixture
def sent(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def _fake_send_email(**kwargs):
        captured.append(kwargs)
        return {"sent": True, "provider": "test", "id": f"msg-{len(captured)}"}

    monkeypatch.setattr(core_email, "send_email", _fake_send_email)
    return captured


@pytest.fixture
def env(monkeypatch):
    """Endpoint wired to in-memory contracts/notifications/users, t-1 caller."""
    docs: list[dict] = []
    notifs = _FakeNotifications()
    users = _FakeUsers([
        {"tenant_id": "t-1", "email": "admin@example.com", "username": "boss",
         "role": "admin", "is_active": True},
        {"tenant_id": "t-1", "email": "fin@example.com", "username": "finance1",
         "role": "finance", "is_active": True},
        {"tenant_id": "t-1", "email": "hk@example.com", "username": "hk1",
         "role": "housekeeping", "is_active": True},
    ])
    fake_db = MagicMock()
    fake_db.corporate_contracts = _FakeContracts(docs)
    fake_db.notifications = notifs
    fake_db.users = users
    monkeypatch.setattr(sales, "db", fake_db)

    user = MagicMock(tenant_id="t-1", username="boss")
    monkeypatch.setattr(sales, "get_current_user", AsyncMock(return_value=user))
    monkeypatch.setattr(
        sales, "_notify_contract_owner_approval", AsyncMock(return_value=True))
    return {"contracts": docs, "notifs": notifs, "users": users}


async def _call(to_status, reason=None, contract_id="c-1"):
    return await transition_corporate_contract_approval(
        contract_id,
        ContractApprovalTransition(to_status=to_status, reason=reason),
        credentials=None,
        _perm=None,
    )


# ── Approver-role derivation ─────────────────────────────────────


def test_approver_roles_include_view_companies_holders():
    roles = sales.CONTRACT_APPROVER_ROLES
    for r in ("admin", "supervisor", "sales", "finance"):
        assert r in roles
    # Roles without VIEW_COMPANIES must not be targeted.
    assert "housekeeping" not in roles
    assert "guest" not in roles


# ── Resubmit detection ───────────────────────────────────────────


async def test_fresh_submit_does_not_notify_approvers(env, sent):
    """A brand-new draft → pending (no prior rejection) must not alert."""
    env["contracts"].append(_contract(approval_status="draft"))
    res = await _call("pending")
    assert res["approval_status"] == "pending"
    assert res["approvers_notified"] is None
    assert env["notifs"].inserted == []
    assert sent == []


async def test_resubmit_pending_notifies_approvers(env, sent):
    """rejected → draft → pending fires the approver alert on the pending hop."""
    env["contracts"].append(_contract(approval_status="rejected", approval_history=[
        {"from_status": "draft", "to_status": "pending"},
        {"from_status": "pending", "to_status": "rejected", "reason": "fix it"},
    ]))
    # rejected → draft : no alert (not yet back in the queue)
    await _call("draft")
    assert env["notifs"].inserted == []
    assert sent == []

    # draft → pending : back in the queue → alert fires
    res = await _call("pending")
    assert res["approval_status"] == "pending"
    info = res["approvers_notified"]
    assert info["in_app"] is True
    # admin + finance are approvers; housekeeping is not; boss (resubmitter)
    # is an approver but skipped → exactly one e-mail (finance).
    assert info["approver_count"] == 2
    assert info["emails_sent"] == 1
    assert [c["to"] for c in sent] == ["fin@example.com"]


async def test_inapp_notification_shape(env, sent):
    env["contracts"].append(_contract(approval_status="rejected", approval_history=[
        {"from_status": "pending", "to_status": "rejected", "reason": "x"},
    ]))
    await _call("draft")
    await _call("pending")
    assert len(env["notifs"].inserted) == 1
    n = env["notifs"].inserted[0]
    assert n["tenant_id"] == "t-1"
    assert n["type"] == "corporate_contract_resubmitted"
    assert n["read"] is False
    assert n["related_entity"] == "corporate_contract"
    assert n["related_id"] == "c-1"
    assert "Acme A.Ş." in n["title"]
    assert "boss" in n["message"]
    assert n["link"] == "/reports/corporate-contract-approvals"
    # role-targeted so clerks/housekeeping don't see it
    assert "admin" in n["target_roles"]
    assert "housekeeping" not in n["target_roles"]


async def test_users_query_is_tenant_and_role_scoped(env, sent):
    env["contracts"].append(_contract(approval_status="rejected", approval_history=[
        {"to_status": "rejected", "reason": "x"},
    ]))
    await _call("draft")
    await _call("pending")
    q = env["users"].last_query
    assert q["tenant_id"] == "t-1"
    assert q["is_active"] is True
    assert set(q["role"]["$in"]) == set(sales.CONTRACT_APPROVER_ROLES)


async def test_invalid_approver_email_is_skipped(env):
    captured: list[dict] = []

    async def _fake_send(**kwargs):
        captured.append(kwargs)
        return {"sent": True}

    import core.email as ce
    orig = ce.send_email
    ce.send_email = _fake_send
    try:
        env["users"].docs = [
            {"tenant_id": "t-1", "email": "not-an-email", "username": "u1",
             "role": "admin", "is_active": True},
            {"tenant_id": "t-1", "email": "good@example.com", "username": "u2",
             "role": "finance", "is_active": True},
        ]
        env["contracts"].append(_contract(approval_status="rejected", approval_history=[
            {"to_status": "rejected", "reason": "x"},
        ]))
        await _call("draft")
        res = await _call("pending")
        assert res["approvers_notified"]["emails_sent"] == 1
        assert [c["to"] for c in captured] == ["good@example.com"]
    finally:
        ce.send_email = orig


# ── Best-effort isolation ────────────────────────────────────────


async def test_inapp_failure_is_swallowed(env, sent, monkeypatch):
    async def _boom(_doc):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(env["notifs"], "insert_one", _boom)
    env["contracts"].append(_contract(approval_status="rejected", approval_history=[
        {"to_status": "rejected", "reason": "x"},
    ]))
    await _call("draft")
    res = await _call("pending")  # must not raise
    assert res["approval_status"] == "pending"
    assert res["approvers_notified"]["in_app"] is False
    # e-mail channel still ran independently
    assert res["approvers_notified"]["emails_sent"] == 1


async def test_email_failure_is_swallowed(env, monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(core_email, "send_email", _boom)
    env["contracts"].append(_contract(approval_status="rejected", approval_history=[
        {"to_status": "rejected", "reason": "x"},
    ]))
    await _call("draft")
    res = await _call("pending")  # must not raise
    assert res["approval_status"] == "pending"
    # in-app still succeeded; e-mail count stayed 0
    assert res["approvers_notified"]["in_app"] is True
    assert res["approvers_notified"]["emails_sent"] == 0
