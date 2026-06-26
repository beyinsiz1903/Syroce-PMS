"""
Agency v1 — Adim 3 imza kimlik deposu birim testleri (ADR Karar 2, secret-at-rest).

Saf test: gercek Mongo yok (fake koleksiyon). Sifreleme GERCEK AESGCMEngine ile
(deterministik test keyring) yapilir — boylece AAD-mismatch fail-closed (gercek
GCM InvalidTag) dogrulanir; sahte-yesil URETILMEZ. Sir at-rest sifreli; plaintext
shared_secret hicbir dokumanda tutulmaz.
"""
from __future__ import annotations

import pytest

import routers.agency_v1.signing_store as store
from core.crypto.engine import AESGCMEngine
from core.crypto.keys import KeyRing


class _FakeSigningColl:
    def __init__(self) -> None:
        self._docs: list[dict] = []

    @staticmethod
    def _matches(doc: dict, flt: dict) -> bool:
        return all(doc.get(f) == v for f, v in flt.items())

    async def insert_one(self, doc: dict) -> None:
        for d in self._docs:
            if d.get("_id") == doc.get("_id"):
                from pymongo.errors import DuplicateKeyError

                raise DuplicateKeyError("dup _id")
        self._docs.append(dict(doc))

    async def find_one(self, flt: dict, projection=None):
        for d in self._docs:
            if self._matches(d, flt):
                return dict(d)
        return None

    async def update_one(self, flt: dict, update: dict) -> None:
        for d in self._docs:
            if self._matches(d, flt):
                d.update(update.get("$set", {}))
                return


class _FakeSysDB:
    def __init__(self) -> None:
        self.agency_signing_secrets = _FakeSigningColl()


@pytest.fixture(autouse=True)
def deterministic_engine(monkeypatch):
    keyring = KeyRing._from_test(current_key=b"\x11" * 32, kid="test-v1")
    engine = AESGCMEngine(keyring)
    monkeypatch.setattr(store, "_engine", lambda: engine)


_KEY = dict(key_id="api-key-1", tenant_id="T-1", agency_id="AG-1")


@pytest.mark.asyncio
async def test_mint_then_resolve_roundtrip():
    db = _FakeSysDB()
    raw = await store.mint_agency_signing_secret(db, **_KEY)
    assert isinstance(raw, str) and len(raw) > 20

    resolved = await store.resolve_signing_secret(db, "api-key-1")
    assert resolved is not None
    assert resolved["shared_secret"] == raw
    assert resolved["tenant_id"] == "T-1"
    assert resolved["agency_id"] == "AG-1"
    assert resolved["key_id"] == "api-key-1"


@pytest.mark.asyncio
async def test_secret_at_rest_no_plaintext():
    db = _FakeSysDB()
    raw = await store.mint_agency_signing_secret(db, **_KEY)
    stored = db.agency_signing_secrets._docs[0]
    assert "shared_secret" not in stored
    assert stored["secret_enc"].startswith("SYR1:")
    assert raw not in stored["secret_enc"]  # ham sir zarfta gozukmez


@pytest.mark.asyncio
async def test_resolve_missing_returns_none():
    db = _FakeSysDB()
    assert await store.resolve_signing_secret(db, "yok") is None
    assert await store.resolve_signing_secret(db, "") is None


@pytest.mark.asyncio
async def test_aad_mismatch_fail_closed():
    """Sifreli sir baska bir tenant'a tasinirsa (AAD degisir) -> GCM InvalidTag
    -> resolve fail-closed None doner (cross-tenant yeniden-kullanim reddi)."""
    db = _FakeSysDB()
    await store.mint_agency_signing_secret(db, **_KEY)
    db.agency_signing_secrets._docs[0]["tenant_id"] = "T-EVIL"
    assert await store.resolve_signing_secret(db, "api-key-1") is None


@pytest.mark.asyncio
async def test_double_mint_rejected():
    db = _FakeSysDB()
    await store.mint_agency_signing_secret(db, **_KEY)
    from pymongo.errors import DuplicateKeyError

    with pytest.raises(DuplicateKeyError):
        await store.mint_agency_signing_secret(db, **_KEY)


@pytest.mark.asyncio
async def test_revoke_then_resolve_none():
    db = _FakeSysDB()
    await store.mint_agency_signing_secret(db, **_KEY)
    await store.revoke_signing_secret(db, "api-key-1")
    assert await store.resolve_signing_secret(db, "api-key-1") is None
