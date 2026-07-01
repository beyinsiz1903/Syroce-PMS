"""
Agency v1 — Adim 3 HMAC imza dependency birim testleri (ADR Karar 2).

Saf test: gercek Starlette Request (ASGI scope) + GERCEK AESGCMEngine
(deterministik test keyring) + fake sysdb. Govde body-cache yolundan okunur
(tuketme tuzagi yok). Negatif yollar fail-closed 401 dogrulanir; sahte-yesil yok.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote_plus, urlencode

import pytest
from starlette.requests import Request

import routers.agency_v1.auth as auth
import routers.agency_v1.signing_store as store
from core.crypto.engine import AESGCMEngine
from core.crypto.keys import KeyRing


# ── Fakes ────────────────────────────────────────────────────────────
class _Coll:
    def __init__(self):
        self._docs: list[dict] = []

    @staticmethod
    def _m(d, f):
        return all(d.get(k) == v for k, v in f.items())

    async def insert_one(self, doc):
        for d in self._docs:
            if d.get("_id") == doc.get("_id"):
                from pymongo.errors import DuplicateKeyError

                raise DuplicateKeyError("dup")
        self._docs.append(dict(doc))

    async def find_one(self, flt, projection=None):
        for d in self._docs:
            if self._m(d, flt):
                return dict(d)
        return None

    async def update_one(self, flt, update):
        for d in self._docs:
            if self._m(d, flt):
                d.update(update.get("$set", {}))
                return


class _SysDB:
    def __init__(self):
        self.agency_signing_secrets = _Coll()
        self.agency_api_keys = _Coll()
        self.agency_nonces = _Coll()


@pytest.fixture(autouse=True)
def wiring(monkeypatch):
    keyring = KeyRing._from_test(current_key=b"\x22" * 32, kid="test-v1")
    engine = AESGCMEngine(keyring)
    monkeypatch.setattr(store, "_engine", lambda: engine)
    sysdb = _SysDB()
    monkeypatch.setattr("core.tenant_db.get_system_db", lambda: sysdb)
    monkeypatch.setattr("core.tenant_db.set_tenant_context", lambda *_a, **_k: None)
    return sysdb


KEY_ID = "api-key-1"
TENANT = "T-1"
AGENCY = "AG-1"


async def _provision(sysdb) -> str:
    await sysdb.agency_api_keys.insert_one(
        {"id": KEY_ID, "tenant_id": TENANT, "agency_id": AGENCY, "is_active": True}
    )
    return await store.mint_agency_signing_secret(
        sysdb, key_id=KEY_ID, tenant_id=TENANT, agency_id=AGENCY
    )


def _sig(secret, *, key_id, method, path, query, ts, nonce, body):
    cq = urlencode(sorted(query), quote_via=quote_plus) if query else ""
    sts = "\n".join(
        [key_id, method, path, cq, ts, nonce, hashlib.sha256(body).hexdigest()]
    )
    return hmac.new(secret.encode(), sts.encode(), hashlib.sha256).hexdigest()


def _request(method, path, query_pairs, headers, body):
    qs = urlencode(query_pairs, quote_via=quote_plus) if query_pairs else ""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": qs.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _headers(key_id, ts, nonce, sig):
    return {
        "authorization": f"Bearer {key_id}",
        "x-agency-timestamp": ts,
        "x-agency-nonce": nonce,
        "x-agency-signature": sig,
    }


# ── Tests ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_valid_signature_authenticates(wiring):
    secret = await _provision(wiring)
    ts, nonce = str(int(time.time())), "n-1"
    body = b'{"x":1}'
    path, qp = "/api/agency/v1/reservations", []
    sig = _sig(secret, key_id=KEY_ID, method="POST", path=path, query=qp,
               ts=ts, nonce=nonce, body=body)
    req = _request("POST", path, qp, _headers(KEY_ID, ts, nonce, sig), body)

    ident = await auth.verify_agency_signature(req)
    assert ident == {"key_id": KEY_ID, "tenant_id": TENANT, "agency_id": AGENCY}


@pytest.mark.asyncio
async def test_body_still_readable_after_dep(wiring):
    """Body-cache: dep govdeyi okuduktan sonra Pydantic yine okuyabilmeli."""
    secret = await _provision(wiring)
    ts, nonce = str(int(time.time())), "n-body"
    body = b'{"hello":"world"}'
    path = "/api/agency/v1/reservations"
    sig = _sig(secret, key_id=KEY_ID, method="POST", path=path, query=[],
               ts=ts, nonce=nonce, body=body)
    req = _request("POST", path, [], _headers(KEY_ID, ts, nonce, sig), body)
    await auth.verify_agency_signature(req)
    assert await req.body() == body  # tukenmedi


@pytest.mark.asyncio
async def test_canonical_query_signed(wiring):
    secret = await _provision(wiring)
    ts, nonce = str(int(time.time())), "n-q"
    body = b""
    path = "/api/agency/v1/availability"
    qp = [("departure_date", "2026-07-03"), ("arrival_date", "2026-07-01")]
    sig = _sig(secret, key_id=KEY_ID, method="GET", path=path, query=qp,
               ts=ts, nonce=nonce, body=body)
    req = _request("GET", path, qp, _headers(KEY_ID, ts, nonce, sig), body)
    ident = await auth.verify_agency_signature(req)
    assert ident["agency_id"] == AGENCY


@pytest.mark.asyncio
async def test_bad_signature_401(wiring):
    await _provision(wiring)
    ts, nonce = str(int(time.time())), "n-bad"
    body = b'{"x":1}'
    path = "/api/agency/v1/reservations"
    req = _request("POST", path, [], _headers(KEY_ID, ts, nonce, "deadbeef"), body)
    with pytest.raises(Exception) as ei:
        await auth.verify_agency_signature(req)
    assert getattr(ei.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_tampered_body_401(wiring):
    secret = await _provision(wiring)
    ts, nonce = str(int(time.time())), "n-tamper"
    signed_body = b'{"amount":100}'
    sent_body = b'{"amount":999}'
    path = "/api/agency/v1/reservations"
    sig = _sig(secret, key_id=KEY_ID, method="POST", path=path, query=[],
               ts=ts, nonce=nonce, body=signed_body)
    req = _request("POST", path, [], _headers(KEY_ID, ts, nonce, sig), sent_body)
    with pytest.raises(Exception) as ei:
        await auth.verify_agency_signature(req)
    assert getattr(ei.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_stale_timestamp_401(wiring):
    secret = await _provision(wiring)
    ts = str(int(time.time()) - 1000)  # pencere disi
    nonce, body = "n-stale", b""
    path = "/api/agency/v1/availability"
    sig = _sig(secret, key_id=KEY_ID, method="GET", path=path, query=[],
               ts=ts, nonce=nonce, body=body)
    req = _request("GET", path, [], _headers(KEY_ID, ts, nonce, sig), body)
    with pytest.raises(Exception) as ei:
        await auth.verify_agency_signature(req)
    assert getattr(ei.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_replay_nonce_401(wiring):
    secret = await _provision(wiring)
    ts, nonce = str(int(time.time())), "n-replay"
    body = b'{"x":1}'
    path = "/api/agency/v1/reservations"
    sig = _sig(secret, key_id=KEY_ID, method="POST", path=path, query=[],
               ts=ts, nonce=nonce, body=body)
    req1 = _request("POST", path, [], _headers(KEY_ID, ts, nonce, sig), body)
    assert (await auth.verify_agency_signature(req1))["key_id"] == KEY_ID
    # Ayni imzali istek tekrar -> nonce replay -> 401.
    req2 = _request("POST", path, [], _headers(KEY_ID, ts, nonce, sig), body)
    with pytest.raises(Exception) as ei:
        await auth.verify_agency_signature(req2)
    assert getattr(ei.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_missing_headers_401(wiring):
    await _provision(wiring)
    req = _request("POST", "/api/agency/v1/reservations", [], {}, b"")
    with pytest.raises(Exception) as ei:
        await auth.verify_agency_signature(req)
    assert getattr(ei.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_unknown_key_id_401(wiring):
    # Hic provision yok -> resolve None -> 401.
    ts, nonce = str(int(time.time())), "n-x"
    req = _request("POST", "/api/agency/v1/reservations", [],
                   _headers("ghost", ts, nonce, "x"), b"")
    with pytest.raises(Exception) as ei:
        await auth.verify_agency_signature(req)
    assert getattr(ei.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_revoked_api_key_401(wiring):
    """Signing secret aktif ama api key devre disi -> 401 (revoke kapisi)."""
    secret = await _provision(wiring)
    await wiring.agency_api_keys.update_one({"id": KEY_ID}, {"$set": {"is_active": False}})
    ts, nonce = str(int(time.time())), "n-rev"
    body = b""
    path = "/api/agency/v1/availability"
    sig = _sig(secret, key_id=KEY_ID, method="GET", path=path, query=[],
               ts=ts, nonce=nonce, body=body)
    req = _request("GET", path, [], _headers(KEY_ID, ts, nonce, sig), body)
    with pytest.raises(Exception) as ei:
        await auth.verify_agency_signature(req)
    assert getattr(ei.value, "status_code", None) == 401
