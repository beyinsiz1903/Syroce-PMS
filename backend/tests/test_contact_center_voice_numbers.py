"""Contact Center — numara→otel/ajan eşleme yönetim uçları (operatör admin ekranı).

İki katman:
  1. Güvenlik-kritik saf birim testleri (HTTP yok): tenant izolasyonu ve doğrulama
     mantığını doğrudan kanıtlar — istemci ``tenant_id``'si super_admin DIŞINDA
     yok sayılır; kapsam filtresi non-super-admin'de daima ``tenant_id`` taşır;
     ajan kimliği kiracı-kapsamlı olmalı; numara E.164 olmalı.
  2. Uçtan uca HTTP testleri (TestClient, super_admin override): create/list/update/
     delete + global-unique çakışma (409) + allowlist DTO (``_id`` sızmaz).

Doktrin (no fake-green): RBAC gerçekten çalışır (super_admin bypass require_module/
require_op'u GERÇEK dependency üzerinden geçer); allowlist DTO ``_id``/beklenmeyen
alan sızdırmaz; tenant izolasyonu gevşetilmez.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import domains.contact_center.voice_router as voice_router
from core.security import get_current_user
from domains.contact_center.voice_router import (
    _normalize_number,
    _resolve_target_tenant,
    _scope_filter,
    _validate_agent_identity,
)

_TENANT = "tenant-A"
_OTHER = "tenant-B"


def _user(*, super_admin: bool, tenant_id: str = _TENANT, uid: str = "u1"):
    return SimpleNamespace(
        id=uid,
        tenant_id=tenant_id,
        role="admin",
        roles=(["super_admin"] if super_admin else []),
        granted_permissions=[],
    )


# ── motor benzeri sahte Mongo (global-unique to_number'ı zorlar) ───────


class _DelRes:
    def __init__(self, n):
        self.deleted_count = n


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    async def to_list(self, length=None):
        return [dict(d) for d in self._docs]


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    @staticmethod
    def _match(doc, flt):
        return all(doc.get(k) == v for k, v in flt.items())

    @staticmethod
    def _project(doc, proj):
        d = dict(doc)
        if proj:
            d.pop("_id", None)
        return d

    async def insert_one(self, doc):
        if any(d.get("to_number") == doc.get("to_number") for d in self.docs):
            raise DuplicateKeyError("ux_cc_voice_number")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    def find(self, flt, proj=None):
        matched = [self._project(d, proj) for d in self.docs if self._match(d, flt)]
        return _Cursor(matched)

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return self._project(d, proj)
        return None

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._match(d, flt):
                new_number = update.get("$set", {}).get("to_number")
                if new_number is not None and any(
                    o is not d and o.get("to_number") == new_number for o in self.docs
                ):
                    raise DuplicateKeyError("ux_cc_voice_number")
                d.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if self._match(d, flt):
                del self.docs[i]
                return _DelRes(1)
        return _DelRes(0)


class _FakeDB:
    def __init__(self):
        self.contact_center_voice_numbers = _Coll()
        self.tenants = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


# ── 1. Güvenlik-kritik saf birim testleri ──────────────────────────────


def test_normalize_number_strips_and_validates():
    assert _normalize_number(" +90 532-123 45 67 ") == "+905321234567"
    for bad in ["", "5321234567", "+0123", "+90abc", "12345"]:
        with pytest.raises(Exception):
            _normalize_number(bad)


def test_agent_identity_must_be_tenant_scoped():
    assert _validate_agent_identity(None, _TENANT) is None
    assert _validate_agent_identity("  ", _TENANT) is None
    assert _validate_agent_identity(f"{_TENANT}:u5", _TENANT) == f"{_TENANT}:u5"
    with pytest.raises(Exception):
        _validate_agent_identity(f"{_OTHER}:u5", _TENANT)


@pytest.mark.asyncio
async def test_resolve_target_tenant_isolation(monkeypatch):
    db = _FakeDB()
    db.tenants.docs.append({"id": _OTHER})
    monkeypatch.setattr(voice_router, "db", db)

    # non-super-admin: gövdedeki tenant_id YOK SAYILIR → kendi kiracısı.
    forced = await _resolve_target_tenant(
        _user(super_admin=False, tenant_id=_TENANT), _OTHER
    )
    assert forced == _TENANT

    # super_admin: var olan hedef kiracıyı seçebilir.
    chosen = await _resolve_target_tenant(_user(super_admin=True), _OTHER)
    assert chosen == _OTHER

    # super_admin: olmayan kiracı → 404.
    with pytest.raises(Exception):
        await _resolve_target_tenant(_user(super_admin=True), "yok-tenant")


def test_scope_filter_enforces_tenant_for_non_super_admin():
    f = _scope_filter(_user(super_admin=False, tenant_id=_TENANT), "id1")
    assert f == {"id": "id1", "tenant_id": _TENANT}
    fs = _scope_filter(_user(super_admin=True), "id1")
    assert fs == {"id": "id1"}


# ── 2. Uçtan uca HTTP testleri (super_admin) ───────────────────────────


@pytest.fixture()
def fake_db(monkeypatch):
    db = _FakeDB()
    db.tenants.docs.append({"id": _TENANT})
    db.tenants.docs.append({"id": _OTHER})
    monkeypatch.setattr(voice_router, "db", db)
    return db


@pytest.fixture()
def client(fake_db):
    app = FastAPI()
    app.include_router(voice_router.router)
    app.dependency_overrides[get_current_user] = lambda: _user(super_admin=True)
    return TestClient(app)


def test_create_then_list_allowlist_dto(client, fake_db):
    r = client.post(
        "/api/contact-center/voice/numbers",
        json={"to_number": "+905321234567", "label": "Resepsiyon", "tenant_id": _OTHER},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["to_number"] == "+905321234567"
    assert body["tenant_id"] == _OTHER
    assert "_id" not in body
    assert "created_by" not in body

    lst = client.get("/api/contact-center/voice/numbers")
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1
    assert all("_id" not in it and "created_by" not in it for it in items)


def test_create_duplicate_number_conflict_409(client, fake_db):
    payload = {"to_number": "+905321234567"}
    assert client.post("/api/contact-center/voice/numbers", json=payload).status_code == 201
    dup = client.post("/api/contact-center/voice/numbers", json=payload)
    assert dup.status_code == 409


def test_create_invalid_number_422(client, fake_db):
    r = client.post("/api/contact-center/voice/numbers", json={"to_number": "12345"})
    assert r.status_code == 422


def test_create_rejects_cross_tenant_agent_identity(client, fake_db):
    r = client.post(
        "/api/contact-center/voice/numbers",
        json={
            "to_number": "+905321234567",
            "tenant_id": _OTHER,
            "agent_identity": f"{_TENANT}:u9",  # hedef kiracı _OTHER değil → red
        },
    )
    assert r.status_code == 422


def test_update_changes_label_and_agent(client, fake_db):
    created = client.post(
        "/api/contact-center/voice/numbers",
        json={"to_number": "+905321234567", "tenant_id": _OTHER},
    ).json()
    upd = client.put(
        f"/api/contact-center/voice/numbers/{created['id']}",
        json={"label": "Çağrı Merkezi", "agent_identity": f"{_OTHER}:agentX"},
    )
    assert upd.status_code == 200
    body = upd.json()
    assert body["label"] == "Çağrı Merkezi"
    assert body["agent_identity"] == f"{_OTHER}:agentX"


def test_delete_then_404(client, fake_db):
    created = client.post(
        "/api/contact-center/voice/numbers", json={"to_number": "+905321234567"}
    ).json()
    d = client.delete(f"/api/contact-center/voice/numbers/{created['id']}")
    assert d.status_code == 204
    again = client.delete(f"/api/contact-center/voice/numbers/{created['id']}")
    assert again.status_code == 404


# ── 3. Non-super-admin tenant izolasyonu (HTTP) ────────────────────────
#
# role="admin" → RBAC (require_module + require_op) GERÇEKTEN geçer (admin tüm
# operasyonları yapar) ama _is_super_admin False → kapsam filtresi daima
# tenant_id taşır. Bu fixture başka bir kiracının kaydına erişimi kanıtlar.


@pytest.fixture()
def tenant_admin_client(fake_db):
    app = FastAPI()
    app.include_router(voice_router.router)
    app.dependency_overrides[get_current_user] = lambda: _user(
        super_admin=False, tenant_id=_TENANT
    )
    return TestClient(app)


def _seed(db, *, number, tenant, agent=None, nid="seed-1"):
    db.contact_center_voice_numbers.docs.append(
        {
            "id": nid,
            "tenant_id": tenant,
            "to_number": number,
            "agent_identity": agent,
            "label": None,
        }
    )


def test_non_super_admin_cannot_update_other_tenant_record(tenant_admin_client, fake_db):
    _seed(fake_db, number="+908509998877", tenant=_OTHER, nid="other-1")
    r = tenant_admin_client.put(
        "/api/contact-center/voice/numbers/other-1", json={"label": "ele geçir"}
    )
    assert r.status_code == 404
    # Kayıt değişmedi (cross-tenant yazma engellendi).
    assert fake_db.contact_center_voice_numbers.docs[0].get("label") is None


def test_non_super_admin_cannot_delete_other_tenant_record(tenant_admin_client, fake_db):
    _seed(fake_db, number="+908509998877", tenant=_OTHER, nid="other-1")
    r = tenant_admin_client.delete("/api/contact-center/voice/numbers/other-1")
    assert r.status_code == 404
    assert len(fake_db.contact_center_voice_numbers.docs) == 1


def test_non_super_admin_list_only_own_tenant(tenant_admin_client, fake_db):
    _seed(fake_db, number="+905321111111", tenant=_TENANT, nid="own-1")
    _seed(fake_db, number="+908509998877", tenant=_OTHER, nid="other-1")
    lst = tenant_admin_client.get("/api/contact-center/voice/numbers")
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1
    assert items[0]["tenant_id"] == _TENANT


def test_non_super_admin_create_ignores_body_tenant_id(tenant_admin_client, fake_db):
    r = tenant_admin_client.post(
        "/api/contact-center/voice/numbers",
        json={"to_number": "+905321234567", "tenant_id": _OTHER},
    )
    assert r.status_code == 201
    # Gövdedeki _OTHER yok sayıldı → kayıt kendi kiracısına yazıldı.
    assert r.json()["tenant_id"] == _TENANT
