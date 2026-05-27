"""Backend tests for the BEO e-mail endpoint (Task #84).

Locks in regressions for `POST /api/mice/events/{id}/beo/email`:

1. Happy path: 2xx, audit row written, `send_email` called once per
   recipient with the rendered PDF attached.
2. Cross-tenant event id resolves to 404 (inherits from `beo()` guard).
3. Empty / invalid-only recipient lists -> 400, no e-mail attempted.
4. Note field is HTML-escaped via `safe_html_value` — raw `<script>` tags
   must never reach the rendered body.
5. Permission gate (`require_op("manage_sales")`) is enforced — a role
   without VIEW_COMPANIES gets 403 and no e-mail is sent.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import email as core_email
from routers import mice as mice_router
from routers.mice import router as mice_api_router


TENANT_ID = "t-beo-1"
OTHER_TENANT = "t-beo-2"

_FULL_EVENT = {
    "id": "evt-full",
    "tenant_id": TENANT_ID,
    "name": "Yıl Sonu Galası",
    "client_name": "Şirket A.Ş.",
    "client_email": "ops@example.com",
    "event_type": "gala",
    "status": "definite",
    "expected_pax": 250,
    "start_date": "2026-06-01",
    "end_date": "2026-06-02",
}


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *_a, **_kw): return self
    def limit(self, *_a, **_kw): return self
    def __aiter__(self):
        self._it = iter(self._docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration


class _EventsCollection:
    def __init__(self, events): self._events = events
    async def find_one(self, flt, _proj=None):
        for d in self._events:
            if (d["id"] == flt.get("id")
                    and d["tenant_id"] == flt.get("tenant_id")):
                return {k: v for k, v in d.items() if k != "_id"}
        return None


class _SpacesCollection:
    def __init__(self, spaces): self._spaces = spaces
    def find(self, flt, *_a, **_kw):
        tid = flt.get("tenant_id")
        return _FakeCursor([s for s in self._spaces if s["tenant_id"] == tid])


class _AuditCollection:
    def __init__(self): self.inserted: list[dict] = []
    async def insert_one(self, doc):
        self.inserted.append(doc)
        return SimpleNamespace(inserted_id=str(len(self.inserted)))


class _FakeDB:
    def __init__(self):
        self.mice_events = _EventsCollection([_FULL_EVENT])
        self.mice_spaces = _SpacesCollection([])
        self.audit_logs = _AuditCollection()


@pytest.fixture
def env(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(mice_router, "get_system_db", lambda: fake_db)

    # Also patch the audit module's _safe_get_db so log_audit_event writes
    # land on our fake collection when the router doesn't pass `db=`.
    try:
        from core import audit as _audit
        monkeypatch.setattr(_audit, "_safe_get_db", lambda: fake_db,
                            raising=False)
    except Exception:
        pass

    sent: list[dict[str, Any]] = []

    async def _fake_send_email(**kwargs):
        sent.append(kwargs)
        return {"sent": True, "provider": "test", "id": f"msg-{len(sent)}"}

    monkeypatch.setattr(core_email, "send_email", _fake_send_email)

    app = FastAPI()
    app.include_router(mice_api_router)

    from core.security import get_current_user

    async def _admin_user():
        return SimpleNamespace(
            id="u1", username="tester",
            tenant_id=TENANT_ID, role="admin",
            granted_permissions=None,
        )

    app.dependency_overrides[get_current_user] = _admin_user
    client = TestClient(app)
    return SimpleNamespace(client=client, db=fake_db, sent=sent, app=app)


def test_beo_email_happy_path_sends_per_recipient_and_audits(env):
    r = env.client.post(
        "/api/mice/events/evt-full/beo/email",
        json={"recipients": ["a@example.com", "b@example.com"],
              "note": "Lütfen onaylayın."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] == 2
    assert body["total"] == 2
    assert body["recipients"] == ["a@example.com", "b@example.com"]
    assert body["failures"] == []

    # send_email called once per recipient with the PDF attached.
    assert len(env.sent) == 2
    tos = sorted(c["to"] for c in env.sent)
    assert tos == ["a@example.com", "b@example.com"]
    for call in env.sent:
        atts = call.get("attachments") or []
        assert len(atts) == 1
        assert atts[0]["content_type"] == "application/pdf"
        assert atts[0]["content"][:4] == b"%PDF"
        assert atts[0]["filename"].endswith(".pdf")

    # Audit row written, scoped to the correct tenant/entity.
    assert len(env.db.audit_logs.inserted) == 1
    row = env.db.audit_logs.inserted[0]
    assert row["tenant_id"] == TENANT_ID
    assert row["action"] == "email"
    assert row["entity_type"] == "mice_event_beo"
    assert row["entity_id"] == "evt-full"
    after = row["after_value"]
    assert after["ok"] == 2
    assert sorted(after["recipients"]) == ["a@example.com", "b@example.com"]


def test_beo_email_dedupes_and_drops_invalid(env):
    r = env.client.post(
        "/api/mice/events/evt-full/beo/email",
        json={"recipients": [
            "a@example.com", " A@Example.com ",  # dup (case-insensitive)
            "not-an-email", "", "   ", "@x",     # invalid entries
            "c@example.com",
        ]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["recipients"] == ["a@example.com", "c@example.com"]
    assert len(env.sent) == 2


def test_beo_email_cross_tenant_returns_404(env):
    from core.security import get_current_user

    async def _other_tenant_user():
        return SimpleNamespace(
            id="u2", username="other",
            tenant_id=OTHER_TENANT, role="admin",
            granted_permissions=None,
        )

    env.app.dependency_overrides[get_current_user] = _other_tenant_user
    r = env.client.post(
        "/api/mice/events/evt-full/beo/email",
        json={"recipients": ["a@example.com"]},
    )
    assert r.status_code == 404
    assert env.sent == []
    assert env.db.audit_logs.inserted == []


def test_beo_email_empty_recipient_list_returns_400(env):
    r = env.client.post(
        "/api/mice/events/evt-full/beo/email",
        json={"recipients": []},
    )
    assert r.status_code == 400
    assert env.sent == []
    assert env.db.audit_logs.inserted == []


def test_beo_email_all_invalid_recipients_returns_400(env):
    r = env.client.post(
        "/api/mice/events/evt-full/beo/email",
        json={"recipients": ["", "nope", "@x", "  "]},
    )
    assert r.status_code == 400
    assert env.sent == []
    assert env.db.audit_logs.inserted == []


def test_beo_email_note_is_html_escaped(env):
    payload = "<script>alert('xss')</script> & friends"
    r = env.client.post(
        "/api/mice/events/evt-full/beo/email",
        json={"recipients": ["a@example.com"], "note": payload},
    )
    assert r.status_code == 200, r.text
    assert len(env.sent) == 1
    html = env.sent[0]["html"]
    # Raw tag must not appear; angle brackets must be entity-encoded.
    assert "<script>" not in html
    assert "alert('xss')" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html  # `&` was escaped

    # The note is also persisted verbatim in the audit row (raw, not HTML)
    # so operators see what was actually requested.
    row = env.db.audit_logs.inserted[0]
    assert row["after_value"]["note"] == payload


def test_beo_email_permission_gate_blocks_unprivileged_role(env):
    from core.security import get_current_user

    async def _staff_user():
        # STAFF role lacks VIEW_COMPANIES → manage_sales gate denies.
        return SimpleNamespace(
            id="u3", username="staffy",
            tenant_id=TENANT_ID, role="staff",
            granted_permissions=None,
        )

    env.app.dependency_overrides[get_current_user] = _staff_user
    r = env.client.post(
        "/api/mice/events/evt-full/beo/email",
        json={"recipients": ["a@example.com"]},
    )
    assert r.status_code == 403, r.text
    assert env.sent == []
    assert env.db.audit_logs.inserted == []
