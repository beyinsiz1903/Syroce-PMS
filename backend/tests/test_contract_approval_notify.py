"""Backend tests for corporate-contract approval owner notification (Task #235).

Locks in the behaviour of `_notify_contract_owner_approval` in
`backend/domains/revenue/rms_router/sales.py`:

1. Approved contract -> one email to the contact_email, no rejection reason.
2. Rejected contract -> email includes the rejection reason.
3. Invalid / missing contact_email -> no email attempted, returns False.
4. Reason and company name are HTML-escaped (no raw <script> in the body).
5. Provider failure / exception is swallowed (best-effort), never raises.
"""
from __future__ import annotations

from typing import Any

import pytest

from core import email as core_email
from domains.revenue.rms_router import sales as sales_router


def _contract(**over: Any) -> dict:
    base = {
        "id": "c-1",
        "tenant_id": "t-1",
        "company_name": "Acme A.Ş.",
        "contact_person": "Ali Demir",
        "contact_email": "ali@example.com",
        "rate_code": "CORP10",
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


@pytest.mark.asyncio
async def test_approved_sends_email_without_reason(sent):
    ok = await sales_router._notify_contract_owner_approval(
        _contract(), to_status="approved", reason=None, actor="boss",
    )
    assert ok is True
    assert len(sent) == 1
    call = sent[0]
    assert call["to"] == "ali@example.com"
    assert "onayland" in call["subject"].lower()
    assert "Acme A.Ş." in call["html"]
    assert "Reddetme gerekçesi" not in call["html"]


@pytest.mark.asyncio
async def test_rejected_includes_reason(sent):
    ok = await sales_router._notify_contract_owner_approval(
        _contract(), to_status="rejected",
        reason="Fiyatlar bütçeyi aşıyor.", actor="boss",
    )
    assert ok is True
    assert len(sent) == 1
    html = sent[0]["html"]
    assert "reddedildi" in sent[0]["subject"].lower()
    assert "Reddetme gerekçesi" in html
    assert "Fiyatlar bütçeyi aşıyor." in html


@pytest.mark.asyncio
async def test_invalid_email_skips_send(sent):
    ok = await sales_router._notify_contract_owner_approval(
        _contract(contact_email="not-an-email"),
        to_status="approved", reason=None, actor="boss",
    )
    assert ok is False
    assert sent == []

    ok2 = await sales_router._notify_contract_owner_approval(
        _contract(contact_email=None),
        to_status="rejected", reason="x", actor="boss",
    )
    assert ok2 is False
    assert sent == []


@pytest.mark.asyncio
async def test_reason_and_company_are_html_escaped(sent):
    ok = await sales_router._notify_contract_owner_approval(
        _contract(company_name="<b>Acme</b>"),
        to_status="rejected",
        reason="<script>alert('xss')</script>", actor="boss",
    )
    assert ok is True
    html = sent[0]["html"]
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    # company name escaped too (template's own styled <b ...> tags are fine)
    assert "<b>Acme</b>" not in html
    assert "&lt;b&gt;Acme&lt;/b&gt;" in html


@pytest.mark.asyncio
async def test_provider_failure_is_swallowed(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(core_email, "send_email", _boom)
    ok = await sales_router._notify_contract_owner_approval(
        _contract(), to_status="approved", reason=None, actor="boss",
    )
    assert ok is False


@pytest.mark.asyncio
async def test_send_returns_not_sent(monkeypatch):
    async def _not_sent(**kwargs):
        return {"sent": False, "provider": "console"}

    monkeypatch.setattr(core_email, "send_email", _not_sent)
    ok = await sales_router._notify_contract_owner_approval(
        _contract(), to_status="approved", reason=None, actor="boss",
    )
    assert ok is False
