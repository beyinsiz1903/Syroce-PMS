"""Task #425 — Ekstra masrafların (extra_charges) folyo bölme akışına dâhil edilmesi.

`extra_charges` booking kapsamlıdır ve folio_id taşımaz; eskiden split_folio
yalnızca `folio_charges` üzerinden çalıştığı için ekstra masraflar bölünemiyordu.
Bu testler split servisinin:

  * Seçilen ekstra masrafı hedef folioya normalize edilmiş bir `folio_charges`
    kalemi olarak yazdığını ve `extra_charges`'tan sildiğini,
  * folio kalemleri + ekstra masrafları aynı çağrıda birlikte taşıyabildiğini,
  * tek-tip OLMAYAN ekstra masraf şekillerini (yalnız charge_amount vs. tam alanlı)
    doğru normalize ettiğini,
  * geçersiz/yabancı id'lerde fail-closed kaldığını (yeni folio yazılmaz)

doğrular. Validator gevşetilmez; ekstra masraf gerçek bir folio kalemine dönüşür.
"""
from __future__ import annotations

import sys
import types as _types
from types import SimpleNamespace

import pytest

from modules.pms_core import folio_hardening_service as fhs_mod
from modules.pms_core.folio_hardening_service import FolioHardeningService


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(list(self.docs)):
            if all(d.get(k) == v for k, v in flt.items()):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    @staticmethod
    def _match(d, flt):
        for k, v in flt.items():
            dv = d.get(k)
            if isinstance(v, dict):
                if "$in" in v:
                    if dv not in v["$in"]:
                        return False
                elif "$ne" in v:
                    if dv == v["$ne"]:
                        return False
                else:
                    if dv != v:
                        return False
            else:
                if dv != v:
                    return False
        return True

    def find(self, flt, proj=None):
        matches = [dict(d) for d in self.docs if self._match(d, flt)]
        return _Cursor(matches)


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _limit):
        return list(self._docs)


class _FakeDB:
    def __init__(self):
        self.folios = _Coll()
        self.folio_charges = _Coll()
        self.extra_charges = _Coll()
        self.payments = _Coll()
        self.folio_operations = _Coll()
        self.pms_audit_trail = _Coll()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    db.folios.docs.append({
        "id": "F1",
        "tenant_id": "t1",
        "status": "open",
        "booking_id": "BK1",
        "folio_number": "1001",
        "balance": 0.0,
    })
    monkeypatch.setattr(fhs_mod, "db", db)

    # split_folio imports generate_folio_number from core.utils at runtime.
    utils_stub = _types.ModuleType("core.utils")

    async def _gen_folio_number(_tenant_id):
        utils_stub._n = getattr(utils_stub, "_n", 2000) + 1
        return str(utils_stub._n)

    utils_stub.generate_folio_number = _gen_folio_number
    monkeypatch.setitem(sys.modules, "core.utils", utils_stub)

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(FolioHardeningService, "_recalculate_folio_balance", _noop)
    monkeypatch.setattr(FolioHardeningService, "_log_audit", _noop)
    return db


async def test_split_moves_extra_charge_into_new_folio(fake_db):
    # Full-shaped extra charge (ek hizmet) — folio_id YOK.
    fake_db.extra_charges.docs.append({
        "id": "E1",
        "tenant_id": "t1",
        "booking_id": "BK1",
        "description": "SPA Masaj",
        "charge_name": "SPA Masaj",
        "category": "spa",
        "charge_category": "spa",
        "amount": 150.0,
        "quantity": 1,
        "total": 150.0,
        "voided": False,
    })

    res = await FolioHardeningService().split_folio(
        "t1", "F1", ["E1"], "guest", "ekstra ayrıştırma", "u1"
    )

    assert res["success"] is True
    assert res["transferred_charges"] == 1
    assert res["transferred_amount"] == 150.0

    new_folio_id = res["new_folio"]["id"]
    # Ekstra masraf yeni folioya folio kalemi olarak yazıldı.
    moved = [c for c in fake_db.folio_charges.docs if c["folio_id"] == new_folio_id]
    assert len(moved) == 1
    assert moved[0]["description"] == "SPA Masaj"
    assert moved[0]["total"] == 150.0
    assert moved[0]["split_from_extra_charge_id"] == "E1"
    assert moved[0]["voided"] is False
    # Orijinal extra_charges satırı silindi (artık folio kalemi).
    assert fake_db.extra_charges.docs == []


async def test_split_normalizes_minimal_extra_charge_shape(fake_db):
    # Erken giriş/geç çıkış şekli: yalnız charge_name/charge_amount, total/voided YOK.
    fake_db.extra_charges.docs.append({
        "id": "E2",
        "tenant_id": "t1",
        "booking_id": "BK1",
        "charge_name": "Erken Giriş Ücreti",
        "charge_amount": 80.0,
        "category": "room",
    })

    res = await FolioHardeningService().split_folio(
        "t1", "F1", ["E2"], "guest", "erken giriş ayrıştırma", "u1"
    )

    assert res["success"] is True
    assert res["transferred_amount"] == 80.0
    new_folio_id = res["new_folio"]["id"]
    moved = [c for c in fake_db.folio_charges.docs if c["folio_id"] == new_folio_id]
    assert len(moved) == 1
    assert moved[0]["description"] == "Erken Giriş Ücreti"
    assert moved[0]["charge_category"] == "room"
    assert moved[0]["total"] == 80.0
    assert moved[0]["amount"] == 80.0


async def test_split_mixed_folio_charge_and_extra_charge(fake_db):
    fake_db.folio_charges.docs.append({
        "id": "C1",
        "tenant_id": "t1",
        "folio_id": "F1",
        "voided": False,
        "total": 60.0,
    })
    fake_db.extra_charges.docs.append({
        "id": "E3",
        "tenant_id": "t1",
        "booking_id": "BK1",
        "description": "Minibar",
        "total": 40.0,
        "amount": 40.0,
        "voided": False,
    })

    res = await FolioHardeningService().split_folio(
        "t1", "F1", ["C1", "E3"], "company", "kurumsal ayrıştırma", "u1"
    )

    assert res["success"] is True
    assert res["transferred_charges"] == 2
    assert res["transferred_amount"] == 100.0

    new_folio_id = res["new_folio"]["id"]
    # C1 folio_id taşındı; E3 normalize edilip yazıldı.
    c1 = await fake_db.folio_charges.find_one({"id": "C1"})
    assert c1["folio_id"] == new_folio_id
    moved_extra = [c for c in fake_db.folio_charges.docs if c.get("split_from_extra_charge_id") == "E3"]
    assert len(moved_extra) == 1
    assert moved_extra[0]["folio_id"] == new_folio_id
    assert fake_db.extra_charges.docs == []


async def test_split_rejects_unknown_extra_charge_id(fake_db):
    folios_before = len(fake_db.folios.docs)
    res = await FolioHardeningService().split_folio(
        "t1", "F1", ["NOPE"], "guest", "geçersiz", "u1"
    )
    assert res["success"] is False
    # Fail-closed: hiçbir yeni folio yazılmadı.
    assert len(fake_db.folios.docs) == folios_before


async def test_split_does_not_steal_other_bookings_extra_charge(fake_db):
    # Başka booking'e ait ekstra masraf — kaynak folionun booking'i ile eşleşmez.
    fake_db.extra_charges.docs.append({
        "id": "E4",
        "tenant_id": "t1",
        "booking_id": "OTHER",
        "description": "Başka rezervasyon",
        "total": 99.0,
        "voided": False,
    })
    res = await FolioHardeningService().split_folio(
        "t1", "F1", ["E4"], "guest", "yabancı", "u1"
    )
    assert res["success"] is False
    # Yabancı booking'in ekstra masrafı silinmedi.
    assert any(d["id"] == "E4" for d in fake_db.extra_charges.docs)
