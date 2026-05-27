"""Backend tests for the BEO PDF endpoint (Task #54 / #69 follow-up).

Locks in three regressions for `GET /api/mice/events/{id}/beo.pdf`:

1. Happy path returns 200 with `application/pdf` and a body that starts
   with `%PDF` (weasyprint signature).
2. Cross-tenant event id resolves to 404 (the JSON `beo()` helper already
   tenant-scopes the lookup; this test pins that the PDF endpoint inherits
   that guard rather than ever returning a renderer error).
3. Optional sections (`agenda`, `payment_schedule`,
   `technical_requirements`, `staff_assignments`, plus `totals` and
   `resources`) may be absent / null without breaking the HTML→PDF render.
   Also exercises a non-ASCII client name so the `html.escape` path is
   covered for UTF-8 payloads.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import mice as mice_router
from routers.mice import router as mice_api_router


TENANT_ID = "t-beo-1"
OTHER_TENANT = "t-beo-2"

_FULL_EVENT = {
    "id": "evt-full",
    "tenant_id": TENANT_ID,
    "name": "Yıl Sonu Galası",
    "client_name": "Şirket A.Ş. (İstanbul)",
    "client_email": "ops@example.com",
    "client_phone": "+90 555 000 0000",
    "event_type": "gala",
    "status": "definite",
    "expected_pax": 250,
    "start_date": "2026-06-01",
    "end_date": "2026-06-02",
    "notes": "VIP — özel menü",
    "totals": {
        "space_total": 35000.0,
        "resources_total": 12500.0,
        "grand_total": 47500.0,
    },
    "space_bookings": [
        {
            "space_id": "sp-1",
            "starts_at": "2026-06-01T18:00:00",
            "ends_at": "2026-06-02T01:00:00",
            "setup_style": "banquet",
            "expected_pax": 250,
        }
    ],
    "resources": [
        {"name": "Gala Menü", "type": "fb",
         "quantity": 250, "unit_price": 850.0},
    ],
    "agenda": [
        {"starts_at": "2026-06-01T19:00:00",
         "ends_at": "2026-06-01T20:00:00",
         "title": "Karşılama Kokteyli",
         "kind": "cocktail", "owner": "F&B"},
    ],
    "payment_schedule": [
        {"due_date": "2026-05-15", "label": "Depozito",
         "amount": 15000.0, "paid": True, "reference": "TX-001"},
    ],
    "technical_requirements": {
        "projector": True, "screen": True,
        "microphone_wired": 2, "microphone_wireless": 1,
        "sound_system": True, "stage": True, "lighting": True,
        "livestream": False, "internet_mbps": 200,
        "translation_booths": 0, "notes": "HDMI hattı",
    },
    "staff_assignments": [
        {"role": "host", "name": "Ayşe Yılmaz", "notes": "Ana sunucu"},
    ],
    "entertainment": {"type": "dj", "name": "DJ Volkan"},
}

# Sparse event: only the fields `beo()` projects are present, and every
# optional section is missing or empty so we exercise the renderer's
# fallback branches. Client name uses non-ASCII chars (Çağrı + emoji-free
# Turkish diacritics) to lock the html.escape path.
_SPARSE_EVENT = {
    "id": "evt-sparse",
    "tenant_id": TENANT_ID,
    "name": "Küçük Toplantı",
    "client_name": "Çağrı Öztürk — Şirket",
    "event_type": "meeting",
    "status": "tentative",
    "expected_pax": 8,
    "start_date": "2026-07-01",
    "end_date": "2026-07-01",
    # No totals / space_bookings / resources / agenda / payment_schedule
    # / technical_requirements / staff_assignments / entertainment.
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
                # Strip Mongo _id semantics — beo() passes `{"_id": 0}`.
                return {k: v for k, v in doc.items() if k != "_id"}
        return None


class _SpacesCollection:
    def __init__(self, spaces: list[dict]):
        self._spaces = spaces

    def find(self, flt: dict, *_a: Any, **_kw: Any) -> _FakeCursor:
        tid = flt.get("tenant_id")
        return _FakeCursor([s for s in self._spaces if s["tenant_id"] == tid])


class _FakeDB:
    def __init__(self):
        self.mice_events = _EventsCollection([_FULL_EVENT, _SPARSE_EVENT])
        self.mice_spaces = _SpacesCollection([
            {"id": "sp-1", "tenant_id": TENANT_ID,
             "name": "Grand Balo Salonu"},
        ])


@pytest.fixture
def client(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(mice_router, "get_system_db", lambda: fake_db)

    app = FastAPI()
    app.include_router(mice_api_router)

    from core.security import get_current_user

    async def _fake_user():
        return SimpleNamespace(
            id="u1", username="tester", tenant_id=TENANT_ID, role="admin",
        )

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def test_beo_pdf_returns_pdf_bytes(client):
    r = client.get("/api/mice/events/evt-full/beo.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    cd = r.headers.get("content-disposition", "")
    assert "evt-full" in cd and ".pdf" in cd


def test_beo_pdf_cross_tenant_returns_404(monkeypatch, client):
    # Flip the caller's tenant: the same event id must now be invisible.
    from core.security import get_current_user

    async def _other_tenant_user():
        return SimpleNamespace(
            id="u2", username="other", tenant_id=OTHER_TENANT, role="admin",
        )

    client.app.dependency_overrides[get_current_user] = _other_tenant_user
    r = client.get("/api/mice/events/evt-full/beo.pdf")
    assert r.status_code == 404


def test_beo_pdf_renders_when_optional_sections_absent(client):
    """Sparse event has no totals/agenda/payment_schedule/tech/staff and a
    non-ASCII client name — the renderer must still produce a valid PDF."""
    r = client.get("/api/mice/events/evt-sparse/beo.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    # Sanity: a meaningful body, not a 0-byte placeholder.
    assert len(r.content) > 500
