"""Task #426 — Tutar tabanlı folyo bölmede ekstra masrafların dikkate alınması.

Task #425 ekstra masrafları (extra_charges) yalnızca "Kaleme Göre" (by_item)
bölme akışında bölünebilir yapmıştı. "Eşit" ve "Özel tutar" (by-amount) modları
`folio.balance` üzerinden çalışır; ekstra masraflar ise booking kapsamlıdır ve
`calculate_folio_balance`'a dâhil DEĞİLDİR, dolayısıyla tutar tabanlı bölmede
hesaba katılmıyordu.

Bu testler `split_folio_by_amounts`'ın bölmeden önce kaynak booking'in voided
olmayan ekstra masraflarını kaynak folioya normalize edip absorbe ettiğini ve
bölünebilir bakiyeye dâhil ettiğini doğrular:

  * Ekstra masraf, kaynak folioya bir `folio_charges` kalemi olarak yazılır ve
    `extra_charges`'tan silinir; kaynak folio bakiyesi ekstra masraf toplamı
    kadar artar.
  * `folio.balance`'tan büyük ama `folio.balance + ekstra` toplamından küçük bir
    aktarım — eskiden reddedilirken — artık başarılıdır.
  * Çift sayım olmaz: bölme sonrası (kaynak bakiye + tüm hedef bakiyeleri) ==
    (orijinal folio.balance + ekstra masraf toplamı).
  * Sonuçta `absorbed_extra_total` raporlanır.
  * Ekstra masrafı OLMAYAN booking'lerde davranış değişmez (regresyon yok).
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
            if self._match(d, flt):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if self._match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(list(self.docs)):
            if self._match(d, flt):
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
    # Açık kaynak folio: gerçek 100.0'lık bir folio kalemiyle desteklenir,
    # böylece bakiye yeniden hesabı anlamlıdır.
    db.folios.docs.append({
        "id": "F1",
        "tenant_id": "t1",
        "status": "open",
        "booking_id": "BK1",
        "folio_number": "1001",
        "balance": 100.0,
        "guest_id": "G1",
    })
    db.folio_charges.docs.append({
        "id": "C-SRC",
        "tenant_id": "t1",
        "folio_id": "F1",
        "voided": False,
        "total": 100.0,
    })
    monkeypatch.setattr(fhs_mod, "db", db)

    utils_stub = _types.ModuleType("core.utils")

    async def _gen_folio_number(_tenant_id):
        utils_stub._n = getattr(utils_stub, "_n", 2000) + 1
        return str(utils_stub._n)

    async def _calc_balance(folio_id, tenant_id):
        total = 0.0
        for c in db.folio_charges.docs:
            if (
                c.get("folio_id") == folio_id
                and c.get("tenant_id") == tenant_id
                and not c.get("voided")
            ):
                total += float(c.get("total", c.get("amount", 0)) or 0)
        paid = 0.0
        for p in db.payments.docs:
            if (
                p.get("folio_id") == folio_id
                and p.get("tenant_id") == tenant_id
                and not p.get("voided")
            ):
                paid += float(p.get("amount", 0) or 0)
        return round(total - paid, 2)

    utils_stub.generate_folio_number = _gen_folio_number
    utils_stub.calculate_folio_balance = _calc_balance
    sys.modules["core.utils"] = utils_stub

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(FolioHardeningService, "_log_audit", _noop)
    return db


def _add_extra(db, eid="E1", total=50.0, **extra):
    doc = {
        "id": eid,
        "tenant_id": "t1",
        "booking_id": "BK1",
        "description": "SPA Masaj",
        "total": total,
        "amount": total,
        "voided": False,
    }
    doc.update(extra)
    db.extra_charges.docs.append(doc)


async def test_absorbs_extra_charges_into_source_before_split(fake_db):
    _add_extra(fake_db, "E1", 50.0)

    # Aktarım 120 > folio.balance(100) ama < bölünebilir(150) → başarılı olmalı.
    res = await FolioHardeningService().split_folio_by_amounts(
        "t1", "F1", [{"amount": 120.0}], "tutar bölme", "u1"
    )

    assert res["success"] is True
    assert res["absorbed_extra_total"] == 50.0
    assert round(res["transferred_amount"], 2) == 120.0

    # Ekstra masraf kaynak folioya folio kalemi olarak yazıldı + extra_charges silindi.
    assert fake_db.extra_charges.docs == []
    absorbed = [
        c for c in fake_db.folio_charges.docs
        if c.get("split_from_extra_charge_id") == "E1"
    ]
    assert len(absorbed) == 1
    assert absorbed[0]["folio_id"] == "F1"
    assert absorbed[0]["total"] == 50.0


async def test_no_double_counting_after_amount_split(fake_db):
    _add_extra(fake_db, "E1", 50.0)

    res = await FolioHardeningService().split_folio_by_amounts(
        "t1", "F1", [{"amount": 120.0}], "tutar bölme", "u1"
    )
    assert res["success"] is True

    src = await fake_db.folios.find_one({"id": "F1"})
    targets = [
        f for f in fake_db.folios.docs
        if f["id"] != "F1" and f.get("booking_id") == "BK1"
    ]
    target_sum = sum(round(float(f.get("balance", 0)), 2) for f in targets)

    # Çift sayım yok: kaynak kalan + hedefler == orijinal folio.balance + ekstra.
    assert round(src["balance"] + target_sum, 2) == 150.0
    # Kaynak ekstra dâhil 150'den 120 aktardı → 30 kaldı.
    assert round(src["balance"], 2) == 30.0


async def test_amount_split_without_extra_charges_is_unchanged(fake_db):
    # Ekstra masraf yok → absorbed_extra_total 0, davranış aynı.
    res = await FolioHardeningService().split_folio_by_amounts(
        "t1", "F1", [{"amount": 60.0}], "tutar bölme", "u1"
    )
    assert res["success"] is True
    assert res["absorbed_extra_total"] == 0.0
    src = await fake_db.folios.find_one({"id": "F1"})
    assert round(src["balance"], 2) == 40.0


async def test_voided_extra_charge_is_not_absorbed(fake_db):
    _add_extra(fake_db, "E-VOID", 50.0, voided=True)

    res = await FolioHardeningService().split_folio_by_amounts(
        "t1", "F1", [{"amount": 60.0}], "tutar bölme", "u1"
    )
    assert res["success"] is True
    assert res["absorbed_extra_total"] == 0.0
    # Voided ekstra masraf silinmedi / absorbe edilmedi.
    assert any(d["id"] == "E-VOID" for d in fake_db.extra_charges.docs)
    # 60 > folio.balance(100) değil; ama voided ekstra dâhil edilmediği için
    # bölünebilir bakiye 100 → 60 aktarım geçerli, 40 kalır.
    src = await fake_db.folios.find_one({"id": "F1"})
    assert round(src["balance"], 2) == 40.0
