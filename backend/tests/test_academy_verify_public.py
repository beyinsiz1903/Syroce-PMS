"""Task #637 — public certificate-verification endpoint tests.

Task #636 proved the certificate HTML embeds a QR encoding the correct
verification URL. This suite locks down the OTHER half of the scan flow: the
public endpoint that URL points at — ``GET /api/academy/verify/{code}``
(``backend/routers/academy_public.py`` -> ``verify_certificate``).

The route is unauthenticated and tenant-context-free; the opaque verification
code is the bearer capability. The invariants under test:

  1. A valid code returns the minimal, PII-safe summary (masked recipient name,
     course, department, issue date, ``valid: true``) and NEVER leaks internal
     fields (user_id, tenant_id, e-mail, score, _id).
  2. A well-formed-but-unknown code AND a malformed code both return the SAME
     uniform ``{"valid": false}`` negative (no existence/format oracle, no PII).
  3. The per-IP rate limit (``_rl_check`` / ``_client_ip``) trips with 429 once
     a single IP exceeds the window budget, and a different IP is unaffected.
  4. The rate-limit counter is keyed per-IP and fails OPEN when the counter
     backend is unavailable (``incr_with_ttl`` returns 0).

Pure route/unit test against an in-memory fake cache + fake Mongo — it needs no
running backend, live Redis, or DB, matching the ``test_academy_security.py`` /
``test_academy_certificate_qr.py`` patterns.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import academy
from routers import academy_public
from routers.academy_public import router as public_router

VALID_CODE = "SYR-ACAD-0123456789"

CERT_DOC = {
    "id": "cert-1",
    "tenant_id": "t1",
    "user_id": "u1",
    "user_name": "Ayse Yilmaz",
    "user_email": "ayse@example.com",
    "course_id": "reception-temelleri",
    "course_title": "Resepsiyon Temelleri",
    "department_label": "On Buro",
    "score": 92,
    "verification_code": VALID_CODE,
    "issued_at": datetime(2026, 6, 20),
}

# Internal fields that must never appear on the public surface.
_LEAK_FIELDS = ("user_id", "tenant_id", "user_email", "score", "_id", "course_id")


# ── In-memory fakes ───────────────────────────────────────────────────


class _FakeCertCollection:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None


class _FakeDB:
    def __init__(self, docs: list[dict]):
        self.academy_certificates = _FakeCertCollection(docs)


class _FakeCache:
    """In-memory per-key counter mirroring ``cache.incr_with_ttl``.

    ``available=False`` simulates a downed counter backend (returns 0 → the
    rate-limiter must fail open).
    """

    def __init__(self, *, available: bool = True):
        self.available = available
        self.counts: dict[str, int] = {}

    def incr_with_ttl(self, key: str, ttl: int) -> int:
        if not self.available:
            return 0
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


def _build_client(monkeypatch, *, docs=None, cache=None) -> TestClient:
    fake_db = _FakeDB(docs if docs is not None else [dict(CERT_DOC)])
    monkeypatch.setattr(academy, "_db", lambda: fake_db)
    monkeypatch.setattr(academy_public, "_cache",
                        cache if cache is not None else _FakeCache())
    app = FastAPI()
    app.include_router(public_router)
    return TestClient(app)


# ── 1. Valid code → minimal PII-safe summary ──────────────────────────


def test_valid_code_returns_masked_summary(monkeypatch):
    with _build_client(monkeypatch) as client:
        r = client.get(f"/api/academy/verify/{VALID_CODE}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["valid"] is True
        assert body["course_title"] == "Resepsiyon Temelleri"
        assert body["department_label"] == "On Buro"
        assert body["issued_at"] == "2026-06-20"
        assert body["verification_code"] == VALID_CODE
        # Recipient name is masked, never the raw full name.
        assert body["recipient_name"] == "A*** Y***"
        assert "Ayse" not in r.text
        assert "Yilmaz" not in r.text


def test_valid_code_does_not_leak_internal_fields(monkeypatch):
    with _build_client(monkeypatch) as client:
        r = client.get(f"/api/academy/verify/{VALID_CODE}")
        assert r.status_code == 200, r.text
        body = r.json()
        for field in _LEAK_FIELDS:
            assert field not in body, f"public view leaked {field!r}"
        # The exact public contract — nothing more.
        assert set(body.keys()) == {
            "valid", "verification_code", "course_title",
            "department_label", "issued_at", "recipient_name",
        }
        # Defence in depth: sensitive values never appear in the raw payload.
        assert "ayse@example.com" not in r.text
        assert "92" not in r.text


def test_lowercase_code_is_normalised_and_matches(monkeypatch):
    """The endpoint upper-cases/strips the code before lookup, so a QR scanned
    into a lower-case URL still resolves."""
    with _build_client(monkeypatch) as client:
        r = client.get(f"/api/academy/verify/{VALID_CODE.lower()}")
        assert r.status_code == 200, r.text
        assert r.json()["valid"] is True


# ── 2. Unknown / malformed code → uniform negative ────────────────────


def test_unknown_but_wellformed_code_returns_uniform_negative(monkeypatch):
    with _build_client(monkeypatch) as client:
        r = client.get("/api/academy/verify/SYR-ACAD-AAAAAAAAAA")
        assert r.status_code == 200, r.text
        assert r.json() == {"valid": False}


def test_malformed_code_returns_same_uniform_negative(monkeypatch):
    """A malformed code is rejected pre-DB by the format regex, returning the
    identical negative as an unknown code — no format/existence oracle."""
    with _build_client(monkeypatch) as client:
        r = client.get("/api/academy/verify/not-a-real-code")
        assert r.status_code == 200, r.text
        assert r.json() == {"valid": False}


def test_negative_response_carries_no_pii(monkeypatch):
    with _build_client(monkeypatch) as client:
        for code in ("SYR-ACAD-AAAAAAAAAA", "garbage"):
            r = client.get(f"/api/academy/verify/{code}")
            body = r.json()
            assert body == {"valid": False}
            assert "recipient_name" not in body
            assert "course_title" not in body


# ── 3. Per-IP rate limiting ───────────────────────────────────────────


def test_rate_limit_trips_after_budget_exceeded(monkeypatch):
    cache = _FakeCache()
    with _build_client(monkeypatch, cache=cache) as client:
        # _RL_MAX_HITS allowed requests succeed (200), the next one is 429.
        for i in range(academy_public._RL_MAX_HITS):
            r = client.get(f"/api/academy/verify/{VALID_CODE}")
            assert r.status_code == 200, f"req #{i + 1}: {r.text}"
        blocked = client.get(f"/api/academy/verify/{VALID_CODE}")
        assert blocked.status_code == 429, blocked.text
        # The 429 body must not leak certificate data.
        assert "recipient_name" not in blocked.text
        assert "Ayse" not in blocked.text


def test_rate_limit_is_per_ip(monkeypatch):
    """The counter is keyed on the client IP, so exhausting one IP must not
    block a different IP."""
    cache = _FakeCache()
    with _build_client(monkeypatch, cache=cache) as client:
        # Exhaust IP "1.1.1.1" via a trusted-proxy x-forwarded-for header.
        monkeypatch.setattr(academy_public, "_is_trusted_proxy", lambda ip: True)
        for _ in range(academy_public._RL_MAX_HITS):
            client.get(f"/api/academy/verify/{VALID_CODE}",
                       headers={"x-forwarded-for": "1.1.1.1"})
        blocked = client.get(f"/api/academy/verify/{VALID_CODE}",
                             headers={"x-forwarded-for": "1.1.1.1"})
        assert blocked.status_code == 429
        # A different IP still has its full budget.
        other = client.get(f"/api/academy/verify/{VALID_CODE}",
                           headers={"x-forwarded-for": "2.2.2.2"})
        assert other.status_code == 200, other.text
        # Two distinct per-IP counters exist.
        keys = [k for k in cache.counts if k.startswith("academy:verify:rl:")]
        assert any(k.endswith("1.1.1.1") for k in keys)
        assert any(k.endswith("2.2.2.2") for k in keys)


def test_rate_limit_fails_open_when_counter_unavailable(monkeypatch):
    """When the counter backend is down (incr_with_ttl → 0) verification, being
    read-only and low-risk, must keep serving (fail open)."""
    cache = _FakeCache(available=False)
    with _build_client(monkeypatch, cache=cache) as client:
        for _ in range(academy_public._RL_MAX_HITS + 5):
            r = client.get(f"/api/academy/verify/{VALID_CODE}")
            assert r.status_code == 200, r.text


def test_rate_limit_checked_before_db_lookup(monkeypatch):
    """A blocked request must 429 without ever reaching the certificate store —
    the public surface cannot be used to brute-force codes under throttle."""
    cache = _FakeCache()
    fake_db = _FakeDB([dict(CERT_DOC)])
    hits = {"n": 0}

    orig_find_one = fake_db.academy_certificates.find_one

    async def _counting_find_one(query, projection=None):
        hits["n"] += 1
        return await orig_find_one(query, projection)

    fake_db.academy_certificates.find_one = _counting_find_one
    monkeypatch.setattr(academy, "_db", lambda: fake_db)
    monkeypatch.setattr(academy_public, "_cache", cache)

    app = FastAPI()
    app.include_router(public_router)
    with TestClient(app) as client:
        for _ in range(academy_public._RL_MAX_HITS):
            client.get(f"/api/academy/verify/{VALID_CODE}")
        db_hits_before_block = hits["n"]
        blocked = client.get(f"/api/academy/verify/{VALID_CODE}")
        assert blocked.status_code == 429
        # The blocked request did not query the DB.
        assert hits["n"] == db_hits_before_block
