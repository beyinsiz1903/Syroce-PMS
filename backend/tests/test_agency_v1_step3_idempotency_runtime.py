"""
Agency v1 — Adim 3 idempotency runtime birim testleri (ADR Karar 4).

Saf test: gercek Mongo/Redis yok. Sahte koleksiyon donmus 5'li scope uzerinde
benzersizligi (ux_idempotency_cache_scope, partial-on-string) emule eder.
Sahte-yesil URETILMEZ: davranis matrisi gercek runtime kodundan dogrulanir;
PII-at-rest gercek seal/unseal yolundan (sahte crypto zarfi ile) dogrulanir.
"""
from __future__ import annotations

import base64
import json

import pytest
from pymongo.errors import DuplicateKeyError

from routers.agency_v1.idempotency_runtime import begin_agency_idempotency


class _UpdateResult:
    def __init__(self, matched: int):
        self.matched_count = matched


class _FakeCache:
    """idempotency_cache emulasyonu: 5'li scope uzerinde compound-unique."""

    def __init__(self) -> None:
        self._docs: list[dict] = []

    def _scope_key(self, d: dict):
        k = d.get("idempotency_key")
        if not isinstance(k, str):
            return None  # partial-on-string: None key collision'a girmez
        return (d["tenant_id"], d["agency_id"], d["method"], d["path"], k)

    @staticmethod
    def _matches(doc: dict, flt: dict) -> bool:
        return all(doc.get(f) == v for f, v in flt.items())

    async def insert_one(self, doc: dict) -> None:
        sk = self._scope_key(doc)
        if sk is not None:
            for d in self._docs:
                if self._scope_key(d) == sk:
                    raise DuplicateKeyError("dup scope")
        self._docs.append(dict(doc))

    async def find_one(self, flt: dict, projection=None):
        for d in self._docs:
            if self._matches(d, flt):
                return dict(d)
        return None

    async def update_one(self, flt: dict, update: dict):
        matched = 0
        for d in self._docs:
            if self._matches(d, flt):
                d.update(update.get("$set", {}))
                matched += 1
        return _UpdateResult(matched)

    async def delete_one(self, flt: dict) -> None:
        self._docs = [d for d in self._docs if not self._matches(d, flt)]


class _FakeDB:
    def __init__(self) -> None:
        self.idempotency_cache = _FakeCache()


class _FakeCrypto:
    """seal_response_body envelope-prefix kontrolu icin gercekci prefix uretir."""

    def encrypt(self, s: str) -> str:
        return "aes256gcm:" + base64.b64encode(s.encode()).decode()

    def decrypt(self, c: str) -> str:
        return base64.b64decode(c[len("aes256gcm:"):]).decode()


@pytest.fixture
def fake_crypto(monkeypatch):
    monkeypatch.setattr(
        "core.crypto.service.get_crypto_service", lambda: _FakeCrypto()
    )


_SCOPE = dict(
    tenant_id="T-1",
    agency_id="A-1",
    method="POST",
    path="/api/agency/v1/reservations",
    idempotency_key="key-1",
)


@pytest.mark.asyncio
async def test_first_claim_acquired():
    db = _FakeDB()
    res = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    assert res.status == "acquired"
    assert res.lock is not None


@pytest.mark.asyncio
async def test_in_progress_same_key_same_fp():
    db = _FakeDB()
    await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    res = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    assert res.status == "in_progress"


@pytest.mark.asyncio
async def test_conflict_same_key_diff_fp():
    db = _FakeDB()
    await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    res = await begin_agency_idempotency(
        db, request_fingerprint="fp-DIFFERENT", **_SCOPE
    )
    assert res.status == "conflict"


@pytest.mark.asyncio
async def test_replay_after_complete(fake_crypto):
    db = _FakeDB()
    first = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    await first.lock.complete(
        {"pms_reservation_id": "R-9", "status": "confirmed"}, status_code=201
    )
    # PII-at-rest: plaintext response_body YOK, yalniz sifreli zarf.
    stored = db.idempotency_cache._docs[0]
    assert "response_body" not in stored
    assert stored["response_body_enc"].startswith("aes256gcm:")

    replay = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    assert replay.status == "replay"
    assert replay.status_code == 201
    assert replay.response == {"pms_reservation_id": "R-9", "status": "confirmed"}


@pytest.mark.asyncio
async def test_conflict_after_complete_diff_fp(fake_crypto):
    db = _FakeDB()
    first = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    await first.lock.complete({"pms_reservation_id": "R-9"}, status_code=201)
    res = await begin_agency_idempotency(db, request_fingerprint="fp-OTHER", **_SCOPE)
    assert res.status == "conflict"


@pytest.mark.asyncio
async def test_release_allows_retry():
    db = _FakeDB()
    first = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    await first.lock.release()
    again = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    assert again.status == "acquired"


@pytest.mark.asyncio
async def test_complete_on_stale_lock_returns_false(fake_crypto):
    """Processing slotu complete'ten ONCE silinirse (TTL sweep/yavas handler):
    completion DUSURULUR (False), yeni satir OLUSTURULMAZ (upsert yok, yaris-acmaz)."""
    db = _FakeDB()
    first = await begin_agency_idempotency(db, request_fingerprint="fp-1", **_SCOPE)
    # Slotu TTL silmis gibi davran.
    db.idempotency_cache._docs.clear()
    ok = await first.lock.complete({"pms_reservation_id": "R-9"}, status_code=201)
    assert ok is False
    assert db.idempotency_cache._docs == []  # yeniden olusturulmadi


class _DupThenMissingCache:
    """DuplicateKeyError sonrasi find_one None doner (insert-find arasi TTL yarisi)."""

    async def insert_one(self, doc):
        raise DuplicateKeyError("dup scope")

    async def find_one(self, flt, projection=None):
        return None


@pytest.mark.asyncio
async def test_duplicate_then_missing_returns_in_progress():
    class _DB:
        idempotency_cache = _DupThenMissingCache()

    res = await begin_agency_idempotency(_DB(), request_fingerprint="fp-1", **_SCOPE)
    assert res.status == "in_progress"


def test_agency_error_response_shape():
    from routers.agency_v1.dtos import SCHEMA_VERSION
    from routers.agency_v1.errors import agency_error_response

    resp = agency_error_response(
        409,
        "inventory_conflict",
        conflict_date="2026-07-01",
        room_type_id="RT-1",
        available=0,
    )
    body = json.loads(resp.body)
    assert resp.status_code == 409
    assert body["error_code"] == "inventory_conflict"
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["conflict_date"] == "2026-07-01"
    assert body["available"] == 0
