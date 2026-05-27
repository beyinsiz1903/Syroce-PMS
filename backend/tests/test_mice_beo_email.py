"""Backend tests for the BEO PDF email endpoint (Task #84).

Locks in seven regressions for `POST /api/mice/events/{id}/beo/email`:

1. Happy path — valid recipients trigger one `send_email` per address with
   the PDF bytes attached, and an `email` audit row is written.
2. Cross-tenant event id 404 — `beo()` helper guards tenant scope before
   the email loop ever runs (no audit row written, no send_email called).
3. Empty recipients → 400 (`Alıcı bulunamadı...`) — no send, no audit.
4. Invalid / non-string entries dropped silently; if NONE remain valid,
   the endpoint returns 400 instead of sending to garbage.
5. Duplicate recipients (case-insensitive) deduped to a single send.
6. `note` is HTML-escaped via `safe_html_value` — raw `<script>` tags
   from the caller must NOT appear unescaped in the email HTML body.
7. `send_email` failures are reported in the response `failures` list,
   not raised — partial-success contract.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import mice as mice_router
from routers.mice import router as mice_api_router


TENANT_ID = "t-beo-email-1"
OTHER_TENANT = "t-beo-email-2"

_EVENT = {
    "id": "evt-mail",
    "tenant_id": TENANT_ID,
    "name": "Mail Test Gala",
    "client_name": "Çağrı Öztürk",
    "event_type": "gala",
    "status": "definite",
    "expected_pax": 100,
    "start_date": "2026-08-01",
    "end_date": "2026-08-02",
    "totals": {"space_total": 10000.0, "resources_total": 5000.0, "grand_total": 15000.0},
}


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = list(docs)

    def sort(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:  # noqa: PERF203
            raise StopAsyncIteration


class _EventsCollection:
    def __init__(self, events: list[dict]):
        self._events = events

    async def find_one(self, flt: dict, _proj: dict | None = None):
        for doc in self._events:
            if (doc["id"] == flt.get("id")
                    and doc["tenant_id"] == flt.get("tenant_id")):
                return {k: v for k, v in doc.items() if k != "_id"}
        return None


class _SpacesCollection:
    def find(self, flt: dict, *_a: Any, **_kw: Any) -> _FakeCursor:
        return _FakeCursor([])


class _AuditCollection:
    def __init__(self):
        self.rows: list[dict] = []

    async def insert_one(self, doc: dict):
        self.rows.append(doc)
        return SimpleNamespace(inserted_id="audit-1")


class _FakeDB:
    def __init__(self):
        self.mice_events = _EventsCollection([_EVENT])
        self.mice_spaces = _SpacesCollection()
        self.audit_logs = _AuditCollection()

    # Some callers (`log_audit_event`) access collections by attribute; the
    # audit util in this codebase uses `db.audit_logs.insert_one`. If your
    # repo's audit helper writes elsewhere, this fixture still won't break
    # — the tests inspect the call counter on `send_email_calls`, not the
    # audit row directly except in test #1.


@pytest.fixture
def fake_db():
    return _FakeDB()


@pytest.fixture
def send_email_calls():
    return []


@pytest.fixture
def audit_calls():
    return []


@pytest.fixture
def client(monkeypatch, fake_db, send_email_calls, audit_calls):
    # Patch the data layer.
    monkeypatch.setattr(mice_router, "get_system_db", lambda: fake_db)

    # Patch send_email at its source module (the endpoint imports lazily
    # from `core.email`, so we patch there).
    from core import email as core_email

    async def _fake_send_email(*, to, subject, html, attachments=None, **_kw):
        send_email_calls.append({
            "to": to, "subject": subject, "html": html,
            "attachments": attachments or [],
        })
        return {"sent": True, "provider": "fake"}

    monkeypatch.setattr(core_email, "send_email", _fake_send_email)

    # Patch log_audit_event at its source so we can assert it was called
    # (and only once per request).
    from core import audit as core_audit

    async def _fake_log_audit_event(**kwargs):
        audit_calls.append(kwargs)
        return None

    monkeypatch.setattr(core_audit, "log_audit_event", _fake_log_audit_event)
    # mice.py imports log_audit_event at module scope — patch there too.
    monkeypatch.setattr(mice_router, "log_audit_event", _fake_log_audit_event,
                        raising=False)

    # Patch the PDF renderer so weasyprint isn't required at test time.
    monkeypatch.setattr(mice_router, "_beo_pdf_bytes",
                        lambda _payload: b"%PDF-1.4 fake-bytes-for-test")

    # Wire auth.
    app = FastAPI()
    app.include_router(mice_api_router)
    from core.security import get_current_user

    # super_admin role short-circuits require_op via `_is_super_admin`
    # (see modules/pms_core/role_permission_service.py:137), so we don't
    # need to seed RBAC operations or override the permission dependency.
    async def _user():
        return SimpleNamespace(
            id="u1", username="tester", tenant_id=TENANT_ID,
            role="super_admin", granted_permissions=None,
        )

    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# 1. Happy path
# ─────────────────────────────────────────────────────────────────────
def test_beo_email_happy_path(client, send_email_calls, audit_calls):
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": ["ops@example.com", "manager@example.com"],
              "note": "Lütfen onaylayın."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] == 2
    assert body["total"] == 2
    assert body["failures"] == []
    assert set(body["recipients"]) == {"ops@example.com", "manager@example.com"}

    # send_email called once per recipient, with PDF attachment.
    assert len(send_email_calls) == 2
    for call in send_email_calls:
        assert call["subject"].startswith("Banquet Event Order")
        assert call["attachments"]
        att = call["attachments"][0]
        assert att["content_type"] == "application/pdf"
        assert att["content"].startswith(b"%PDF")
        assert "evt-mail" in att["filename"]

    # Audit row written exactly once with action=email.
    assert len(audit_calls) == 1
    aud = audit_calls[0]
    assert aud["tenant_id"] == TENANT_ID
    assert aud["action"] == "email"
    assert aud["entity_type"] == "mice_event_beo"
    assert aud["entity_id"] == "evt-mail"


# ─────────────────────────────────────────────────────────────────────
# 2. Cross-tenant → 404 (no send, no audit)
# ─────────────────────────────────────────────────────────────────────
def test_beo_email_cross_tenant_404(client, send_email_calls, audit_calls):
    from core.security import get_current_user

    async def _other():
        return SimpleNamespace(
            id="u9", username="other", tenant_id=OTHER_TENANT, role="admin",
        )

    client.app.dependency_overrides[get_current_user] = _other
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": ["ops@example.com"]},
    )
    assert r.status_code == 404
    assert send_email_calls == []
    assert audit_calls == []


# ─────────────────────────────────────────────────────────────────────
# 3. Empty recipients → 400
# ─────────────────────────────────────────────────────────────────────
def test_beo_email_empty_recipients_400(client, send_email_calls, audit_calls):
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": []},
    )
    assert r.status_code == 400
    assert "Alıcı" in r.json()["detail"]
    assert send_email_calls == []
    assert audit_calls == []


# ─────────────────────────────────────────────────────────────────────
# 4. Invalid recipients dropped; all-invalid → 400
# ─────────────────────────────────────────────────────────────────────
def test_beo_email_drops_invalid_then_400(client, send_email_calls):
    # Pydantic rejects non-strings at the schema layer (422); we exercise
    # the endpoint-level filter, which drops empty/blank/malformed strings.
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": ["not-an-email", "", "   ", "@nodomain", "noatsign.com"]},
    )
    assert r.status_code == 400
    assert send_email_calls == []


def test_beo_email_pydantic_rejects_non_string_items(client, send_email_calls):
    # Defence-in-depth: the request schema is list[str]; non-string items
    # must be 422'd before the endpoint body runs.
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": [None, 42, {"x": 1}]},
    )
    assert r.status_code == 422
    assert send_email_calls == []


def test_beo_email_mixed_invalid_keeps_valid(client, send_email_calls):
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": ["good@example.com", "not-an-email", ""]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipients"] == ["good@example.com"]
    assert len(send_email_calls) == 1
    assert send_email_calls[0]["to"] == "good@example.com"


# ─────────────────────────────────────────────────────────────────────
# 5. Dedupe (case-insensitive)
# ─────────────────────────────────────────────────────────────────────
def test_beo_email_dedupes_case_insensitive(client, send_email_calls):
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": ["ops@example.com", "OPS@example.com",
                             "  ops@Example.COM  "]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] == 1
    assert body["total"] == 1
    assert len(send_email_calls) == 1


# ─────────────────────────────────────────────────────────────────────
# 6. Note HTML-escaped (no XSS into recipient inbox)
# ─────────────────────────────────────────────────────────────────────
def test_beo_email_note_html_escaped(client, send_email_calls):
    hostile = "<script>alert('xss')</script>&\"'"
    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": ["ops@example.com"], "note": hostile},
    )
    assert r.status_code == 200, r.text
    html = send_email_calls[0]["html"]
    # Raw <script> tag must not appear — must be entity-escaped.
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    # Quote / ampersand escaped too.
    assert "&amp;" in html
    assert "&#x27;" in html or "&#39;" in html


# ─────────────────────────────────────────────────────────────────────
# 7. send_email failures surfaced in `failures`, not raised
# ─────────────────────────────────────────────────────────────────────
def test_beo_email_send_failure_reported(monkeypatch, client, send_email_calls):
    from core import email as core_email
    call_count = {"n": 0}

    async def _flaky_send(*, to, subject, html, attachments=None, **_kw):
        call_count["n"] += 1
        send_email_calls.append({"to": to})
        if to == "bad@example.com":
            return {"sent": False, "provider": "fake", "error": "smtp 550"}
        return {"sent": True, "provider": "fake"}

    monkeypatch.setattr(core_email, "send_email", _flaky_send)

    r = client.post(
        "/api/mice/events/evt-mail/beo/email",
        json={"recipients": ["good@example.com", "bad@example.com"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] == 1
    assert body["total"] == 2
    assert len(body["failures"]) == 1
    assert body["failures"][0]["to"] == "bad@example.com"
    assert "smtp 550" in body["failures"][0]["error"]
