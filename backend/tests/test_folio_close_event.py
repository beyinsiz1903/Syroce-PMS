"""Unit tests for the pure folio.closed.v1 event/token helpers (Mongo-free)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import core.folio_close_event as fce


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("FOLIO_FETCH_SECRET", "unit-test-secret-key")
    monkeypatch.delenv("FOLIO_FETCH_TTL_SECONDS", raising=False)
    yield


def test_token_round_trip_ok():
    closed = "2026-06-11T10:00:00+00:00"
    token, exp = fce.make_fetch_token("t1", "f1", closed)
    assert fce.verify_fetch_token(
        token, tenant_id="t1", folio_id="f1", closed_at_norm=closed, exp_epoch=exp
    ) == "ok"


def test_token_expired():
    closed = "2026-06-11T10:00:00+00:00"
    past = datetime.now(UTC) - timedelta(hours=200)
    token, exp = fce.make_fetch_token("t1", "f1", closed, now=past)
    assert fce.verify_fetch_token(
        token, tenant_id="t1", folio_id="f1", closed_at_norm=closed, exp_epoch=exp
    ) == "expired"


def test_token_tamper_field():
    closed = "2026-06-11T10:00:00+00:00"
    token, exp = fce.make_fetch_token("t1", "f1", closed)
    # Wrong tenant => signature mismatch => invalid (not a leak of expired).
    assert fce.verify_fetch_token(
        token, tenant_id="OTHER", folio_id="f1", closed_at_norm=closed, exp_epoch=exp
    ) == "invalid"
    # Tampered exp => signature recomputed over the new exp => invalid.
    assert fce.verify_fetch_token(
        token, tenant_id="t1", folio_id="f1", closed_at_norm=closed, exp_epoch=exp + 999999
    ) == "invalid"
    # Tampered closed_at => invalid.
    assert fce.verify_fetch_token(
        token, tenant_id="t1", folio_id="f1", closed_at_norm="2000-01-01T00:00:00+00:00",
        exp_epoch=exp,
    ) == "invalid"


def test_token_bad_exp_type():
    assert fce.verify_fetch_token(
        "abc", tenant_id="t1", folio_id="f1", closed_at_norm="x", exp_epoch="not-int"
    ) == "invalid"


def test_missing_secret_fail_closed(monkeypatch):
    monkeypatch.delenv("FOLIO_FETCH_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(fce.FetchSecretMissing):
        fce.sign_fetch_token("t1", "f1", "x", 123)


def test_jwt_secret_fallback(monkeypatch):
    monkeypatch.delenv("FOLIO_FETCH_SECRET", raising=False)
    monkeypatch.setenv("JWT_SECRET", "jwt-fallback")
    # Should not raise; produces a 64-char hex digest.
    sig = fce.sign_fetch_token("t1", "f1", "x", 123)
    assert len(sig) == 64 and all(c in "0123456789abcdef" for c in sig)


def test_normalize_closed_at():
    dt = datetime(2026, 6, 11, 10, 0, tzinfo=UTC)
    assert fce.normalize_closed_at(dt) == dt.isoformat()
    assert fce.normalize_closed_at("2026-06-11T10:00:00+00:00") == "2026-06-11T10:00:00+00:00"
    assert fce.normalize_closed_at(None) == ""


def test_message_id_stability_and_reclose():
    a = fce.build_message_id("f1", "2026-06-11T10:00:00+00:00")
    assert a == "folio.closed.v1:f1:2026-06-11T10:00:00+00:00"
    # A reclose (new closed_at) yields a distinct id => re-emittable.
    b = fce.build_message_id("f1", "2026-06-12T09:00:00+00:00")
    assert a != b


def test_ttl_env_override(monkeypatch):
    monkeypatch.setenv("FOLIO_FETCH_TTL_SECONDS", "3600")
    assert fce.fetch_ttl_seconds() == 3600
    monkeypatch.setenv("FOLIO_FETCH_TTL_SECONDS", "bogus")
    assert fce.fetch_ttl_seconds() == 72 * 3600
    monkeypatch.setenv("FOLIO_FETCH_TTL_SECONDS", "-5")
    assert fce.fetch_ttl_seconds() == 72 * 3600


_PII_KEYS = {
    "guest_name", "name", "first_name", "last_name", "email", "phone",
    "tax_no", "tax_number", "vkn", "tckn", "national_id", "passport",
    "address", "guest", "customer", "billing_address",
}


def test_event_payload_has_no_pii():
    folio = {
        "id": "f1",
        "tenant_id": "t1",
        "folio_number": "F-001",
        "booking_id": "b1",
        "folio_type": "guest",
        "closed_at": "2026-06-11T10:00:00+00:00",
        "currency": "TRY",
        "balance": 0.0,
        # Simulate stray PII on the source doc — it must NOT propagate.
        "guest_name": "Ahmet Yilmaz",
        "email": "ahmet@example.com",
    }
    payload = fce.build_event_payload(folio, base_url="https://app.example.com")
    for k in payload:
        assert k.lower() not in _PII_KEYS, f"PII key leaked: {k}"
    blob = repr(payload).lower()
    assert "ahmet" not in blob and "yilmaz" not in blob
    assert "@example.com" not in blob
    assert payload["event"] == "folio.closed.v1"
    assert payload["folio_id"] == "f1"
    assert payload["fetch_url"].startswith(
        "https://app.example.com/api/public/finance/folio/f1/einvoice-data?"
    )
    assert "token=" in payload["fetch_url"] and "exp=" in payload["fetch_url"]


def test_event_payload_token_verifies_against_endpoint_inputs():
    folio = {
        "id": "f9", "tenant_id": "t9", "folio_number": "F-9",
        "booking_id": "b9", "closed_at": "2026-06-11T10:00:00+00:00",
    }
    payload = fce.build_event_payload(folio, base_url="https://x.test")
    # Extract exp + token the way the endpoint would from the query string.
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(payload["fetch_url"]).query)
    token = q["token"][0]
    exp = int(q["exp"][0])
    assert fce.verify_fetch_token(
        token, tenant_id="t9", folio_id="f9",
        closed_at_norm="2026-06-11T10:00:00+00:00", exp_epoch=exp,
    ) == "ok"
