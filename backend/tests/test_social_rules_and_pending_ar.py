from __future__ import annotations

import os
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-thirty-two-characters")

from domains.ai.router import concierge_social
from routers.finance import folio


def _matches(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$gt" in expected and not (actual is not None and actual > expected["$gt"]):
                return False
        elif actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = deepcopy(docs)

    def sort(self, key, direction):
        self.docs.sort(key=lambda row: row.get(key) or "", reverse=direction < 0)
        return self

    async def to_list(self, _length):
        return deepcopy(self.docs)


class Collection:
    def __init__(self, docs=()):
        self.docs = [deepcopy(doc) for doc in docs]

    def find(self, query, _projection=None):
        return Cursor([doc for doc in self.docs if _matches(doc, query)])

    async def find_one(self, query, _projection=None):
        return next((deepcopy(doc) for doc in self.docs if _matches(doc, query)), None)

    async def insert_one(self, doc):
        self.docs.append(deepcopy(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, query, update):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(deepcopy(update.get("$set", {})))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                self.docs.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


def _user(tenant_id="tenant-a"):
    return SimpleNamespace(id="user-a", tenant_id=tenant_id, name="Admin", role="admin")


@pytest.mark.asyncio
async def test_social_rule_crud_is_persisted_and_tenant_scoped(monkeypatch):
    collection = Collection()
    monkeypatch.setattr(concierge_social, "db", SimpleNamespace(social_automation_rules=collection))

    created = await concierge_social.create_social_automation_rule(
        concierge_social.SocialAutomationRuleIn(
            name="  Wi-Fi  ", keywords=[" Wifi ", "wifi", "internet"], reply="  Yanıt  "
        ),
        _user(),
    )
    assert created["name"] == "Wi-Fi"
    assert created["keywords"] == ["wifi", "internet"]

    listed = await concierge_social.list_social_automation_rules(_user())
    assert [row["id"] for row in listed] == [created["id"]]
    assert await concierge_social.list_social_automation_rules(_user("tenant-b")) == []

    updated = await concierge_social.update_social_automation_rule(
        created["id"],
        concierge_social.SocialAutomationRuleIn(
            name="Geç giriş", keywords=["erken"], reply="Resepsiyona danışın", active=False
        ),
        _user(),
    )
    assert updated["active"] is False
    assert updated["name"] == "Geç giriş"

    deleted = await concierge_social.delete_social_automation_rule(created["id"], _user())
    assert deleted == {"deleted": True, "id": created["id"]}
    with pytest.raises(HTTPException) as exc:
        await concierge_social.delete_social_automation_rule(created["id"], _user())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_pending_ar_details_include_room_guest_and_reservation(monkeypatch):
    fake_db = SimpleNamespace(
        companies=Collection([{"id": "company-a", "tenant_id": "tenant-a", "name": "Acente", "contact_email": "ar@example.com"}]),
        folios=Collection([{
            "id": "folio-a", "tenant_id": "tenant-a", "company_id": "company-a", "booking_id": "booking-a",
            "folio_number": "F-100", "status": "open", "balance": 6500, "created_at": "2026-09-01T00:00:00+00:00",
        }]),
        bookings=Collection([{
            "id": "booking-a", "tenant_id": "tenant-a", "reservation_number": "RES-42", "guest_name": "Ada Lovelace",
            "room_number": "101", "check_in": "2026-09-05", "check_out": "2026-09-06",
        }]),
    )
    monkeypatch.setattr(folio, "db", fake_db)

    result = await folio.get_pending_ar_details("company-a", _user(), None)
    assert result["total_outstanding"] == 6500
    assert result["folios"] == [{
        "folio_id": "folio-a", "folio_number": "F-100", "booking_id": "booking-a",
        "reservation_number": "RES-42", "guest_name": "Ada Lovelace", "room_number": "101",
        "check_in": "2026-09-05", "check_out": "2026-09-06",
        "created_at": "2026-09-01T00:00:00+00:00", "balance": 6500.0,
    }]


@pytest.mark.asyncio
async def test_pending_ar_reminder_sends_real_email_and_records_audit(monkeypatch):
    sent = []
    audits = []

    async def fake_send_email(**kwargs):
        sent.append(kwargs)
        return {"sent": True, "provider": "test", "id": "message-a"}

    async def fake_audit(**kwargs):
        audits.append(kwargs)

    fake_db = SimpleNamespace(
        companies=Collection([{
            "id": "company-a", "tenant_id": "tenant-a", "name": "Acente <A>",
            "contact_person": "Ali <script>", "contact_email": "ar@example.com",
        }]),
        folios=Collection([{
            "id": "folio-a", "tenant_id": "tenant-a", "company_id": "company-a", "booking_id": "booking-a",
            "folio_number": "F-100", "status": "open", "balance": 125.50, "created_at": "2026-09-01T00:00:00+00:00",
        }]),
        bookings=Collection([{
            "id": "booking-a", "tenant_id": "tenant-a", "guest_name": "Ada <b>", "room_number": "101",
        }]),
        tenants=Collection([{"id": "tenant-a", "name": "Test Hotel"}]),
        ar_reminders=Collection(),
    )
    monkeypatch.setattr(folio, "db", fake_db)
    monkeypatch.setattr(folio, "create_audit_log", fake_audit)
    monkeypatch.setattr("core.email.send_email", fake_send_email)

    result = await folio.send_pending_ar_reminder("company-a", _user(), None)
    assert result["sent"] is True
    assert sent[0]["to"] == "ar@example.com"
    assert "<script>" not in sent[0]["html"]
    assert "&lt;script&gt;" in sent[0]["html"]
    assert fake_db.ar_reminders.docs[0]["folio_ids"] == ["folio-a"]
    assert audits[0]["action"] == "pending_ar_reminder_sent"
