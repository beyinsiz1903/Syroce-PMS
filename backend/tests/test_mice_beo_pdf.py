"""Backend tests for the BEO PDF endpoint (Task #54 / #69 follow-up).

Tests are split into two groups:

A) Guard / routing tests (``client`` fixture)
   ─────────────────────────────────────────
   ``_beo_pdf_bytes`` is stubbed so these tests run without weasyprint system
   libraries.  They cover:
   - banquet_operations feature guard → 200 (enabled) or 403 (disabled)
   - Tenant-scope isolation → 404 for cross-tenant event id
   - Content-Disposition header correctness
   - Routing with sparse / optional-field payloads (no renderer crash)

B) Real renderer tests (``renderer_client`` fixture)
   ──────────────────────────────────────────────────
   Require weasyprint *and* its native system libraries (cairo/pango/glib).
   Skipped automatically when the libraries are absent via
   ``pytest.importorskip``.  They cover:
   - Happy path: response body starts with ``%PDF`` and is > 500 bytes
   - Sparse payload: non-ASCII client name rendered without crash
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

# Sparse event: every optional section is missing so we exercise fallback
# branches in the renderer.  Client name uses non-ASCII Turkish diacritics
# to lock the html.escape path.
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


# ──────────────────────────────────────────────────────────────────────────────
# Shared fake infrastructure
# ──────────────────────────────────────────────────────────────────────────────

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

    async def to_list(self, length=None):
        return list(self._docs) if length is None else list(self._docs)[:length]


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


def _setup_app(monkeypatch, *, stub_renderer: bool = True, tenant_id: str = TENANT_ID):
    """Build a minimal FastAPI app with the MICE router for testing.

    Args:
        stub_renderer: Replace ``_beo_pdf_bytes`` with a fake that returns
            ``b"%PDF-1.4 stub"`` — use this for guard/routing tests that must
            not depend on weasyprint system libs.
        tenant_id: The tenant_id the fake user belongs to.
    """
    fake_db = _FakeDB()
    monkeypatch.setattr(mice_router, "get_system_db", lambda: fake_db)

    import core.entitlements.enforcement as _enf

    async def _async_true(*_a, **_kw):
        return True

    monkeypatch.setattr(_enf, "tenant_has_feature", _async_true)

    if stub_renderer:
        _FAKE_PDF = b"%PDF-1.4 stub"
        monkeypatch.setattr(mice_router, "_beo_pdf_bytes", lambda _payload: _FAKE_PDF)

    app = FastAPI()
    app.include_router(mice_api_router)

    from core.security import get_current_user

    _tid = tenant_id

    async def _fake_user():
        return SimpleNamespace(id="u1", username="tester", tenant_id=_tid, role="admin")

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


# ──────────────────────────────────────────────────────────────────────────────
# A) Guard / routing tests  (renderer stubbed — no weasyprint required)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    """Guard/routing fixture: renderer is stubbed."""
    return _setup_app(monkeypatch, stub_renderer=True)


def test_beo_pdf_returns_200_and_pdf_content_type(client):
    """Endpoint returns 200 + application/pdf with correct Content-Disposition."""
    r = client.get("/api/mice/events/evt-full/beo.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    cd = r.headers.get("content-disposition", "")
    assert "evt-full" in cd and ".pdf" in cd


def test_beo_pdf_cross_tenant_returns_404(monkeypatch, client):
    """Cross-tenant event id must resolve to 404 (tenant isolation)."""
    from core.security import get_current_user

    async def _other_tenant_user():
        return SimpleNamespace(
            id="u2", username="other", tenant_id=OTHER_TENANT, role="admin",
        )

    client.app.dependency_overrides[get_current_user] = _other_tenant_user
    r = client.get("/api/mice/events/evt-full/beo.pdf")
    assert r.status_code == 404


def test_beo_pdf_sparse_event_no_crash(client):
    """Sparse event (no optional sections, non-ASCII client name) must not
    crash the endpoint.  Routing + payload correctness only — renderer is
    stubbed, so byte size is not checked here (see renderer tests below).
    """
    r = client.get("/api/mice/events/evt-sparse/beo.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 0


def test_beo_pdf_feature_guard_blocks_when_disabled(monkeypatch):
    """banquet_operations feature guard must return 403 when feature is off."""
    import core.entitlements.enforcement as _enf

    async def _deny(*_a, **_kw):
        return False

    # Build a client where tenant_has_feature returns False
    # so require_feature raises 403.
    fake_db = _FakeDB()
    monkeypatch.setattr(mice_router, "get_system_db", lambda: fake_db)
    monkeypatch.setattr(_enf, "tenant_has_feature", _deny)

    monkeypatch.setenv("ENTITLEMENT_ENFORCEMENT_MODE", "enforce")

    _FAKE_PDF = b"%PDF-1.4 stub"
    monkeypatch.setattr(mice_router, "_beo_pdf_bytes", lambda _payload: _FAKE_PDF)

    app = FastAPI()
    app.include_router(mice_api_router)

    from core.security import get_current_user

    async def _fake_user():
        return SimpleNamespace(id="u1", username="tester", tenant_id=TENANT_ID, role="admin")

    app.dependency_overrides[get_current_user] = _fake_user
    tc = TestClient(app, raise_server_exceptions=False)
    r = tc.get("/api/mice/events/evt-full/beo.pdf")
    assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# B) Real renderer tests  (skipped when weasyprint / system libs absent)
# ──────────────────────────────────────────────────────────────────────────────

# Attempt to import weasyprint AND actually load the native libs (the import
# succeeds on systems without cairo/glib, but the first HTML() call would fail).
# We detect this by trying a minimal render here at collection time.
def _weasyprint_available() -> bool:
    try:
        from weasyprint import HTML  # type: ignore
        HTML(string="<p>ok</p>").write_pdf()
        return True
    except Exception:
        return False


_WEASYPRINT_REASON = (
    "weasyprint + system libs (cairo/pango/glib) not available in this environment"
)
_needs_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(), reason=_WEASYPRINT_REASON
)


@pytest.fixture
def renderer_client(monkeypatch):
    """Real-renderer fixture: _beo_pdf_bytes is NOT stubbed."""
    return _setup_app(monkeypatch, stub_renderer=False)


@_needs_weasyprint
def test_beo_pdf_real_render_returns_valid_pdf(renderer_client):
    """Real weasyprint render: body must be >500 bytes and start with %PDF."""
    r = renderer_client.get("/api/mice/events/evt-full/beo.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 500


@_needs_weasyprint
def test_beo_pdf_real_render_sparse_event(renderer_client):
    """Real render with sparse payload (non-ASCII name, no optional sections)."""
    r = renderer_client.get("/api/mice/events/evt-sparse/beo.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 500
