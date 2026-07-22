"""Task #638 — public certificate verification PII/enumeration/rate-limit guards.

Locks down the privacy contract of the unauthenticated
``GET /api/academy/verify/{code}`` surface (``backend/routers/academy_public.py``
+ ``backend/core/academy.py``) so a future change to ``public_certificate_view``
or ``_mask_name`` cannot silently start leaking PII or turn the route into an
enumeration oracle:

  1. A valid 200 response carries ONLY the minimal, PII-safe field set and a
     MASKED recipient name — never user_id/tenant_id/score/email/user_name.
  2. A malformed code AND a well-formed-but-not-found code return the SAME
     ``200 {valid: false}`` (no format/existence oracle).
  3. The per-IP rate limit returns 429 once exceeded (in-memory counter).

Router/engine unit test against an in-memory fake Mongo + fake cache — no live
backend or DB, and it never touches pilot data (matches the
``test_academy_security.py`` pattern).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import academy
from routers import academy_public

VALID_CODE = "SYR-ACAD-0123456789"
UNKNOWN_VALID_CODE = "SYR-ACAD-ABCDEF0123"
MALFORMED_CODE = "not-a-code"

# A full certificate row as persisted in Mongo — deliberately carrying every
# sensitive field the public view must strip.
_CERT_ROW = {
    "id": "cert-1",
    "tenant_id": "t1",
    "user_id": "u1",
    "user_name": "John Doe",
    "email": "john.doe@example.com",
    "score": 95,
    "course_id": "reception-temelleri",
    "course_title": "Resepsiyon Temelleri",
    "department_label": "Ön Büro",
    "verification_code": VALID_CODE,
    "issued_at": "2026-06-01T09:30:00",
}

# Exactly the fields the public verification view is allowed to expose.
_ALLOWED_FIELDS = {
    "valid",
    "verification_code",
    "course_title",
    "department_label",
    "issued_at",
    "recipient_name",
}
# Fields that must NEVER appear in the public response.
_FORBIDDEN_FIELDS = {"user_id", "tenant_id", "score", "email", "user_name", "id"}


class _FakeCertificates:
    def __init__(self, rows: list[dict]):
        self.docs = rows

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None


class _FakeDB:
    def __init__(self, rows: list[dict]):
        self.academy_certificates = _FakeCertificates(rows)


class _FakeCache:
    """In-memory stand-in for the Redis-backed rate-limit counter.

    ``incr_with_ttl`` returns a monotonically increasing per-key count so the
    route's ``count <= _RL_MAX_HITS`` gate trips deterministically. A
    ``return_zero`` mode simulates the counter backend being unavailable
    (fail-open path).
    """

    def __init__(self, *, return_zero: bool = False):
        self.counts: dict[str, int] = {}
        self.return_zero = return_zero

    def incr_with_ttl(self, key: str, ttl: int) -> int:
        if self.return_zero:
            return 0
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


def _build_client(monkeypatch, rows, cache):
    fake_db = _FakeDB(rows)
    monkeypatch.setattr(academy, "_db", lambda: fake_db)
    monkeypatch.setattr(academy_public, "_cache", cache)

    app = FastAPI()
    app.include_router(academy_public.router)
    return TestClient(app)


# ── 1. Valid response is PII-minimized + name masked ──────────────────


def test_valid_verify_returns_only_pii_safe_fields(monkeypatch):
    with _build_client(monkeypatch, [dict(_CERT_ROW)], _FakeCache()) as client:
        r = client.get(f"/api/academy/verify/{VALID_CODE}")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["valid"] is True
        # Exact field set — no extra keys leak now or after a refactor.
        assert set(body.keys()) == _ALLOWED_FIELDS, body
        for forbidden in _FORBIDDEN_FIELDS:
            assert forbidden not in body, forbidden

        assert body["verification_code"] == VALID_CODE
        assert body["course_title"] == "Resepsiyon Temelleri"
        assert body["department_label"] == "Ön Büro"
        assert body["issued_at"] == "2026-06-01"  # date-only, no time component

        # Recipient name is masked: initials + asterisks, full name absent.
        assert body["recipient_name"] == "J*** D***"
        assert "John" not in r.text
        assert "Doe" not in r.text

        # Defence in depth: sensitive values never appear anywhere in the payload.
        assert "john.doe@example.com" not in r.text
        assert "95" not in r.text
        assert "t1" not in r.text
        assert "u1" not in r.text


# ── 2. No enumeration oracle: malformed == not-found ──────────────────


def test_unknown_and_malformed_codes_return_identical_negative(monkeypatch):
    with _build_client(monkeypatch, [dict(_CERT_ROW)], _FakeCache()) as client:

        r_unknown = client.get(f"/api/academy/verify/{UNKNOWN_VALID_CODE}")
        r_malformed = client.get(f"/api/academy/verify/{MALFORMED_CODE}")

        assert r_unknown.status_code == 200, r_unknown.text
        assert r_malformed.status_code == 200, r_malformed.text
        # Byte-identical negative response — no format/existence distinction.
        assert r_unknown.json() == {"valid": False}
        assert r_malformed.json() == {"valid": False}
        assert r_unknown.json() == r_malformed.json()


def test_malformed_code_never_reads_db(monkeypatch):
    """A malformed code is rejected by the format gate before any DB lookup."""
    reads: list = []

    class _SpyCerts(_FakeCertificates):
        async def find_one(self, query, projection=None):
            reads.append(query)
            return await super().find_one(query, projection)

    fake_db = _FakeDB([dict(_CERT_ROW)])
    fake_db.academy_certificates = _SpyCerts([dict(_CERT_ROW)])
    monkeypatch.setattr(academy, "_db", lambda: fake_db)
    monkeypatch.setattr(academy_public, "_cache", _FakeCache())

    app = FastAPI()
    app.include_router(academy_public.router)
    with TestClient(app) as client:

        r = client.get(f"/api/academy/verify/{MALFORMED_CODE}")
        assert r.status_code == 200
        assert r.json() == {"valid": False}
        assert reads == [], "malformed code must not hit the database"


# ── 3. Rate limit ─────────────────────────────────────────────────────


def test_rate_limit_returns_429_once_exceeded(monkeypatch):
    cache = _FakeCache()
    with _build_client(monkeypatch, [dict(_CERT_ROW)], cache) as client:

        # The first _RL_MAX_HITS attempts are allowed (count <= max).
        for i in range(academy_public._RL_MAX_HITS):
            r = client.get(f"/api/academy/verify/{VALID_CODE}")
            assert r.status_code == 200, f"attempt {i + 1}: {r.text}"

        # The next attempt trips the limit.
        r = client.get(f"/api/academy/verify/{VALID_CODE}")
        assert r.status_code == 429, r.text
        # A 429 must not leak certificate data.
        assert "John" not in r.text
        assert "verification_code" not in r.text


def test_rate_limit_fails_open_when_counter_unavailable(monkeypatch):
    """When the counter backend is down (incr returns 0) the read-only surface
    fails open — requests are still served rather than blanket-429'd."""
    with _build_client(monkeypatch, [dict(_CERT_ROW)],
                           _FakeCache(return_zero=True)) as client:
        for _ in range(academy_public._RL_MAX_HITS + 5):
            r = client.get(f"/api/academy/verify/{VALID_CODE}")
            assert r.status_code == 200, r.text


# ── 4. Engine helpers (route-independent unit guards) ─────────────────


def test_public_certificate_view_strips_pii_directly():
    view = academy.public_certificate_view(dict(_CERT_ROW))
    assert set(view.keys()) == _ALLOWED_FIELDS
    for forbidden in _FORBIDDEN_FIELDS:
        assert forbidden not in view
    assert view["recipient_name"] == "J*** D***"
    assert view["issued_at"] == "2026-06-01"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("John Doe", "J*** D***"),
        ("Ayşe", "A***"),
        ("  Mehmet  Ali  Can ", "M*** A*** C***"),
        ("", None),
        (None, None),
        ("   ", None),
    ],
)
def test_mask_name_variants(raw, expected):
    assert academy._mask_name(raw) == expected


@pytest.mark.asyncio
async def test_get_certificate_by_code_rejects_malformed_without_db(monkeypatch):
    """The format gate short-circuits malformed codes before the DB read."""

    class _Boom:
        async def find_one(self, *a, **k):  # pragma: no cover - must not run
            raise AssertionError("DB must not be queried for a malformed code")

    monkeypatch.setattr(academy, "_db", lambda: SimpleNamespace(
        academy_certificates=_Boom()))
    assert await academy.get_certificate_by_code("bad-code") is None
    assert await academy.get_certificate_by_code("") is None
