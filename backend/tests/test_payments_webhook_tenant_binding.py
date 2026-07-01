"""Task #312 — Iyzico webhook tenant-binding guvenlik siniri (uctan uca, saf birim).

Kritik dogrulama: webhook tenant'i ASLA client-controlled ``Idempotency-Key``
uzerinden cozmez. Iki kiraci AYNI ``idempotency_key``'i kullansa bile, PSP'ye
gonderilen ``conversationId`` sunucu-uretimi ``conversation_token`` oldugundan
webhook YALNIZCA dogru kiracinin intent'ini gunceller; digerine dokunulmaz.

Ayrica fail-closed sinirlar: secret yoksa 503, imza gecersiz 401, ayni olay
duplicate. Saf testtir: calisan backend / canli Mongo / Iyzico gerektirmez;
sahte-yesil URETILMEZ — davranis gercek handler kodundan gozlenir. Secret test
sabitidir (gercek deger degil); HMAC gercek hesaplanir.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import pytest
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request

from routers import payments_router

_SECRET = "test-webhook-secret"  # test sabiti — gercek secret degil
_SHARED_IDEM = "client-supplied-same-key"  # iki kiracinin AYNI client key'i


class _UpdRes:
    def __init__(self, matched=0):
        self.matched_count = matched


class _FakeColl:
    def __init__(self, *, unique_id=False):
        self.docs: list[dict] = []
        self._unique_id = unique_id

    @staticmethod
    def _match(doc, flt):
        return all(doc.get(k) == v for k, v in flt.items())

    @staticmethod
    def _clean(doc):
        out = dict(doc)
        out.pop("_id", None)
        return out

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return self._clean(d) if proj else dict(d)
        return None

    async def insert_one(self, doc):
        if self._unique_id and any(
            x.get("_id") == doc.get("_id") for x in self.docs
        ):
            raise DuplicateKeyError("dup _id")
        self.docs.append(dict(doc))
        return None

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return _UpdRes(matched=1)
        return _UpdRes(matched=0)


class _FakeDB:
    def __init__(self):
        self.payment_intents = _FakeColl()
        self.payment_webhook_events = _FakeColl(unique_id=True)

    def __getitem__(self, name):
        return getattr(self, name)


def _sign(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _make_request(raw: bytes, *, signature: str | None = None) -> Request:
    headers = [(b"content-type", b"application/json")]
    if signature is not None:
        headers.append((b"x-iyz-signature", signature.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/payments/webhook/iyzico",
        "raw_path": b"/api/payments/webhook/iyzico",
        "query_string": b"",
        "headers": headers,
        "scheme": "https",
        "server": ("testserver", 443),
        "client": ("203.0.113.9", 12345),
    }

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(scope, receive)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(payments_router, "db", db)
    return db


@pytest.fixture
def secret_set(monkeypatch):
    monkeypatch.setenv("IYZICO_WEBHOOK_SECRET", _SECRET)


def _seed_two_tenants(db: _FakeDB) -> None:
    # Iki kiraci AYNI client idempotency_key, FARKLI sunucu-uretimi conversation_token.
    db.payment_intents.docs.extend([
        {
            "id": "intent-A", "tenant_id": "tenant-A",
            "idempotency_key": _SHARED_IDEM, "conversation_token": "tokA",
            "status": "requires_action",
        },
        {
            "id": "intent-B", "tenant_id": "tenant-B",
            "idempotency_key": _SHARED_IDEM, "conversation_token": "tokB",
            "status": "requires_action",
        },
    ])


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_webhook_binds_only_correct_tenant_via_conversation_token(fake_db, secret_set):
    """conversationId=tokA -> YALNIZCA tenant-A intent'i guncellenir; tenant-B intact."""
    _seed_two_tenants(fake_db)
    raw = json.dumps({"conversationId": "tokA", "status": "success",
                      "paymentId": "pay-1"}).encode()
    req = _make_request(raw, signature=_sign(_SECRET, raw))

    res = _run(payments_router.iyzico_webhook(req))
    assert res["status"] == "processed"

    a = next(d for d in fake_db.payment_intents.docs if d["id"] == "intent-A")
    b = next(d for d in fake_db.payment_intents.docs if d["id"] == "intent-B")
    assert a.get("webhook_status") == "webhook_success"
    # KRITIK: ayni idempotency_key'e ragmen tenant-B'ye DOKUNULMADI.
    assert "webhook_status" not in b


def test_webhook_missing_secret_fail_closed_503(fake_db, monkeypatch):
    monkeypatch.delenv("IYZICO_WEBHOOK_SECRET", raising=False)
    raw = json.dumps({"conversationId": "tokA"}).encode()
    req = _make_request(raw, signature="deadbeef")
    with pytest.raises(Exception) as ei:
        _run(payments_router.iyzico_webhook(req))
    assert getattr(ei.value, "status_code", None) == 503


def test_webhook_invalid_signature_401(fake_db, secret_set):
    _seed_two_tenants(fake_db)
    raw = json.dumps({"conversationId": "tokA", "status": "success"}).encode()
    req = _make_request(raw, signature="00" * 32)  # gecersiz imza
    with pytest.raises(Exception) as ei:
        _run(payments_router.iyzico_webhook(req))
    assert getattr(ei.value, "status_code", None) == 401


def test_webhook_unknown_token_ignored_not_leaked(fake_db, secret_set):
    _seed_two_tenants(fake_db)
    raw = json.dumps({"conversationId": "tok-UNKNOWN", "status": "success"}).encode()
    req = _make_request(raw, signature=_sign(_SECRET, raw))
    res = _run(payments_router.iyzico_webhook(req))
    assert res["status"] == "ignored"


def test_webhook_duplicate_event_idempotent(fake_db, secret_set):
    _seed_two_tenants(fake_db)
    raw = json.dumps({"conversationId": "tokA", "status": "success",
                      "paymentId": "pay-1"}).encode()
    sig = _sign(_SECRET, raw)
    first = _run(payments_router.iyzico_webhook(_make_request(raw, signature=sig)))
    second = _run(payments_router.iyzico_webhook(_make_request(raw, signature=sig)))
    assert first["status"] == "processed"
    assert second["status"] == "duplicate"
