"""
Agency v1 — Adim 4: Outbound imzali webhook teslimi (PMS -> Acente) testleri.
ADR docs/adr/2026-06-agency-pms-integration.md Karar 6.

Saf birim testleri: gercek DB/network/crypto YOK. Bagimliliklar monkeypatch ile
sahtelenir. Dogrulanan davranislar:
  - imza simetrisi (acente, dokumanli sema ile dogrulayabilir),
  - hata siniflandirma (2xx/4xx/5xx/429/408/timeout/EgressDenied),
  - devre kesici OPEN iken HTTP cagrisi YAPILMAZ,
  - sozlesme/webhook_url/shared_secret yok -> permanent (fail-closed),
  - enqueue helper alanlari (provider="agency", max_attempts=8, payload.agency_id),
  - RETRY_BACKOFF 6/7/8 + compute_next_available_at,
  - dispatcher routing (agency event -> dispatch_agency_webhook),
  - shared_secret/imza loglara/mesaja sizmaz.
"""
from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlparse

import pytest

import core.agency_webhook as aw
from integrations.xchange.safety import EgressDenied


# ───────────────────────── Sahte (fake) yardimcilar ─────────────────────────

class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeCB:
    """circuit_breaker_store sahtesi. admit ile try_acquire sonucu kontrol edilir."""

    def __init__(self, enabled=True, admit=True, state="closed"):
        self.enabled = enabled
        self._admit = admit
        self._state = state
        self.failures = 0
        self.successes = 0
        self.acquire_calls = 0

    async def try_acquire(self, key, recovery_timeout, half_open_max):
        self.acquire_calls += 1
        return self._state, self._admit

    async def record_failure(self, key, failure_threshold):
        self.failures += 1
        return "open"

    async def record_success(self, key, half_open_max):
        self.successes += 1
        return "closed"


_RESOLVED = {
    "key_id": "key_abc",
    "tenant_id": "tenantA",
    "agency_id": "agency1",
    "shared_secret": "s3cr3t-shared",
}

_CONTRACT = {
    "agency_id": "agency1",
    "tenant_id": "tenantA",
    "status": "approved",
    "webhook_url": "https://acme.example.com/syroce/hook?b=2&a=1",
}


def _patch_common(monkeypatch, *, contract=_CONTRACT, resolved=_RESOLVED,
                  cb=None, post=None):
    """dispatch_agency_webhook bagimliliklarini sahtele."""
    import routers.agency_contracts as contracts_mod
    import core.tenant_db as tenant_db_mod

    async def _fake_contract(agency_id, tenant_id, on_date=None):
        return contract

    async def _fake_resolve(sysdb, tenant_id, agency_id):
        return resolved

    monkeypatch.setattr(contracts_mod, "has_active_contract", _fake_contract)
    monkeypatch.setattr(aw, "_resolve_outbound_secret", _fake_resolve)
    monkeypatch.setattr(tenant_db_mod, "get_system_db", lambda: object())
    if cb is not None:
        monkeypatch.setattr(aw, "circuit_breaker_store", cb)
    if post is not None:
        monkeypatch.setattr(aw, "safe_post_async", post)


def _event(event_type=aw.AGENCY_INVENTORY_UPDATED):
    return {
        "id": "evt-1",
        "event_type": event_type,
        "tenant_id": "tenantA",
        "payload": {"agency_id": "agency1", "room_type": "STD", "date": "2026-07-01",
                    "availability": 3},
    }


# ───────────────────────────── Imza simetrisi ───────────────────────────────

def test_outbound_signature_is_symmetric():
    from routers.agency_v1.auth import _build_string_to_sign

    url = _CONTRACT["webhook_url"]
    body = b'{"a":1,"agency_id":"agency1"}'
    headers = aw._sign_outbound(
        key_id="key_abc", shared_secret="s3cr3t-shared", webhook_url=url, body=body
    )
    parsed = urlparse(url)
    sts = _build_string_to_sign(
        key_id="key_abc",
        method="POST",
        path=parsed.path,
        canonical_query=aw._outbound_canonical_query(parsed.query),
        timestamp=headers["X-Syroce-Timestamp"],
        nonce=headers["X-Syroce-Nonce"],
        body=body,
    )
    expected = hmac.new(b"s3cr3t-shared", sts.encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, headers["X-Syroce-Signature"])
    assert headers["Authorization"] == "Bearer key_abc"


def test_canonical_query_sorted_and_blank_safe():
    assert aw._outbound_canonical_query("") == ""
    assert aw._outbound_canonical_query("b=2&a=1") == "a=1&b=2"
    assert aw._outbound_canonical_query("x=") == "x="


def test_serialize_body_deterministic():
    a = aw._serialize_body({"b": 2, "a": 1})
    b = aw._serialize_body({"a": 1, "b": 2})
    assert a == b == b'{"a":1,"b":2}'


def test_signature_and_secret_never_in_headers_values():
    body = b"{}"
    headers = aw._sign_outbound(
        key_id="key_abc", shared_secret="s3cr3t-shared", webhook_url="https://x.io/h",
        body=body,
    )
    assert "s3cr3t-shared" not in "".join(headers.values())


# ─────────────────────────── Hata siniflandirma ─────────────────────────────

async def test_2xx_success(monkeypatch):
    cb = _FakeCB()

    async def _post(url, *, timeout, content, headers):
        return _FakeResponse(204)

    _patch_common(monkeypatch, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is True and "delivered" in msg
    assert cb.successes == 1 and cb.failures == 0


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410, 422])
async def test_4xx_permanent_records_cb_success(monkeypatch, code):
    cb = _FakeCB()

    async def _post(url, *, timeout, content, headers):
        return _FakeResponse(code)

    _patch_common(monkeypatch, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and msg.startswith("permanent:")
    assert cb.successes == 1 and cb.failures == 0


@pytest.mark.parametrize("code", [408, 429, 500, 502, 503])
async def test_transient_retryable_records_cb_failure(monkeypatch, code):
    cb = _FakeCB()

    async def _post(url, *, timeout, content, headers):
        return _FakeResponse(code)

    _patch_common(monkeypatch, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and msg.startswith("retryable:")
    assert cb.failures == 1 and cb.successes == 0


async def test_connection_error_retryable_cb_failure(monkeypatch):
    cb = _FakeCB()

    async def _post(url, *, timeout, content, headers):
        raise RuntimeError("connection refused")

    _patch_common(monkeypatch, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and msg.startswith("retryable:")
    assert cb.failures == 1


async def test_failure_message_never_leaks_webhook_url(monkeypatch):
    """Doktrin: dispatch hata mesaji (persiste edilen last_error) tam webhook_url'i
    veya query string'ini ASLA gomemeli (olasi token sizintisi)."""
    secret_url = "https://acme.example.com/syroce/hook?token=SUPERSECRET&a=1"
    contract = {"agency_id": "agency1", "tenant_id": "tenantA",
                "webhook_url": secret_url}

    async def _post(url, *, timeout, content, headers):
        raise RuntimeError(f"failed connecting to {secret_url}")

    cb = _FakeCB()
    _patch_common(monkeypatch, contract=contract, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and msg.startswith("retryable:")
    assert "SUPERSECRET" not in msg
    assert "token=" not in msg
    assert secret_url not in msg


async def test_egress_denied_permanent_no_cb_failure(monkeypatch):
    cb = _FakeCB()

    async def _post(url, *, timeout, content, headers):
        raise EgressDenied("blocked private ip")

    _patch_common(monkeypatch, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and msg.startswith("permanent:")
    # EgressDenied endpoint sagligi sinyali degil -> CB failure sayilmaz.
    assert cb.failures == 0


# ─────────────────────── Devre kesici (circuit breaker) ──────────────────────

async def test_circuit_open_does_not_call_post(monkeypatch):
    cb = _FakeCB(enabled=True, admit=False, state="open")
    calls = {"n": 0}

    async def _post(url, *, timeout, content, headers):
        calls["n"] += 1
        return _FakeResponse(200)

    _patch_common(monkeypatch, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and msg.startswith("retryable: circuit_open")
    assert calls["n"] == 0  # olu endpoint dovulmedi


async def test_cb_disabled_still_delivers(monkeypatch):
    cb = _FakeCB(enabled=False)

    async def _post(url, *, timeout, content, headers):
        return _FakeResponse(200)

    _patch_common(monkeypatch, cb=cb, post=_post)
    ok, _ = await aw.dispatch_agency_webhook(_event())
    assert ok is True
    assert cb.acquire_calls == 0  # disabled -> try_acquire cagrilmaz


# ──────────────────────── Fail-closed (not_configured) ───────────────────────

async def test_no_contract_permanent(monkeypatch):
    cb = _FakeCB()

    async def _post(url, *, timeout, content, headers):
        return _FakeResponse(200)

    _patch_common(monkeypatch, contract=None, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and msg.startswith("permanent: no active agency contract")


async def test_no_webhook_url_permanent(monkeypatch):
    cb = _FakeCB()
    contract = {"agency_id": "agency1", "tenant_id": "tenantA", "webhook_url": None}

    async def _post(url, *, timeout, content, headers):
        return _FakeResponse(200)

    _patch_common(monkeypatch, contract=contract, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and "webhook_url" in msg and msg.startswith("permanent:")


async def test_no_secret_permanent(monkeypatch):
    cb = _FakeCB()

    async def _post(url, *, timeout, content, headers):
        return _FakeResponse(200)

    _patch_common(monkeypatch, resolved=None, cb=cb, post=_post)
    ok, msg = await aw.dispatch_agency_webhook(_event())
    assert ok is False and "not_configured" in msg and msg.startswith("permanent:")


async def test_missing_tenant_or_agency_permanent(monkeypatch):
    _patch_common(monkeypatch)
    ev = _event()
    ev["tenant_id"] = ""
    ok, msg = await aw.dispatch_agency_webhook(ev)
    assert ok is False and msg.startswith("permanent: missing")


# ───────────────────────────── Enqueue helper ───────────────────────────────

async def test_enqueue_agency_webhook_event_fields(monkeypatch):
    captured = {}

    async def _fake_enqueue(db, session=None, **kw):
        captured.update(kw)
        captured["session"] = session
        return {"id": "evt-x", **kw}

    import core.outbox_service as outbox_mod
    monkeypatch.setattr(outbox_mod, "enqueue_outbox_event", _fake_enqueue)

    await aw.enqueue_agency_webhook_event(
        db=object(),
        tenant_id="tenantA",
        agency_id="agency1",
        event_type=aw.AGENCY_RATE_UPDATED,
        entity_type="rate",
        entity_id="r1",
        payload={"room_type": "STD"},
    )
    assert captured["provider"] == "agency"
    assert captured["max_attempts"] == aw.AGENCY_MAX_ATTEMPTS == 8
    assert captured["payload"]["agency_id"] == "agency1"
    assert captured["tenant_id"] == "tenantA"


async def test_enqueue_rejects_unknown_event_type(monkeypatch):
    with pytest.raises(ValueError):
        await aw.enqueue_agency_webhook_event(
            db=object(),
            tenant_id="t",
            agency_id="a",
            event_type="not.an.agency.event",
            entity_type="x",
            entity_id="1",
            payload={},
        )


# ─────────────────────── Backoff (8 deneme ~24h) ────────────────────────────

def test_retry_backoff_has_agency_tail():
    from core.outbox_service import RETRY_BACKOFF, compute_next_available_at

    assert RETRY_BACKOFF[6] == 14400
    assert RETRY_BACKOFF[7] == 28800
    assert RETRY_BACKOFF[8] == 43200
    # OTA paylasimli ilk 5 anahtar degismedi.
    assert RETRY_BACKOFF[5] == 1800
    # attempt 8 icin gercek bir ileri-tarih hesaplanir (default'a dusmez).
    assert isinstance(compute_next_available_at(8), str)


# ───────────────────────────── Dispatcher routing ───────────────────────────

async def test_dispatcher_routes_agency_event(monkeypatch):
    import core.outbox_dispatcher as disp

    called = {}

    async def _fake_dispatch(event):
        called["event"] = event
        return True, "delivered"

    monkeypatch.setattr(aw, "dispatch_agency_webhook", _fake_dispatch)
    ok, msg = await disp.dispatch_outbox_event(_event(aw.AGENCY_RESTRICTION_UPDATED))
    assert ok is True
    assert called["event"]["event_type"] == aw.AGENCY_RESTRICTION_UPDATED
