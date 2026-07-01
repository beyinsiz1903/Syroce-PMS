"""Task #427 — Bölünen ekstra masraf için uçtan uca GERÇEK Mongo doğrulaması.

Task #425'in birim testleri (`test_pms_hardening_folio_split_extra_charges.py`)
`extra_charges` taşıma + normalize davranışını FakeDB ile doğrular. Bu modül aynı
akışı GERÇEK MongoDB üzerinde uçtan uca çalıştırır:

  extra_charge oluştur -> folio var (ensure-folio karşılığı) -> split_folio ->
    * yeni folio'da normalize edilmiş `folio_charges` kalemi (split_from_extra_charge_id set),
    * orijinal `extra_charges` satırı silindi,
    * bakiyeler GERÇEK `calculate_folio_balance` ($sum aggregation) ile tutarlı:
      kaynak folio etkilenmez (ekstra masraf zaten bakiyeye dâhil değildi),
      yeni folio bakiyesi taşınan kalemlerin toplamına eşit.

FakeDB'nin yapamadığı şey burada doğrulanır: gerçek find/insert/delete + gerçek
server-side aggregation. Validator gevşetilmez; ekstra masraf gerçek bir folio
kalemine dönüşür.

Gerçek MongoDB gerektirir (mongomock yüklü değil). Doctrine gereği mongod, pytest
ile AYNI bash komutunda başlatılmalıdır (forked daemon reaping tuzağı). Bağlanıla-
mazsa testler atlanır. Her test atılabilir (throwaway) bir veritabanı kullanır ve
sonunda düşürür; pilot/üretim verisine dokunmaz.
"""
from __future__ import annotations

import os
import uuid

import pytest

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - motor always present in backend
    AsyncIOMotorClient = None  # type: ignore

from modules.pms_core import folio_hardening_service as fhs_mod
from modules.pms_core.folio_hardening_service import FolioHardeningService

pytestmark = pytest.mark.asyncio

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


async def _mongo_or_skip():
    """Gerçek Mongo'ya bağlan; erişilemezse testi atla."""
    if AsyncIOMotorClient is None:
        pytest.skip("motor yüklü değil")
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=1500)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"MongoDB erişilemez ({MONGO_URL})")
    return client


@pytest.fixture
async def live_db(monkeypatch):
    """Atılabilir gerçek bir veritabanı sağlar; servis ve util `db`'lerini ona bağlar.

    split_folio modül seviyesindeki `db`'yi (TenantAwareDBProxy) kullanır;
    `generate_folio_number`/`calculate_folio_balance` ise `core.utils.db`'yi.
    Her ikisini de plain (tenant-aware OLMAYAN) throwaway Motor db'ye yönlendiriyoruz
    — sorgular zaten filtrelerinde tenant_id taşıdığı için izolasyon korunur ve
    STRICT_TENANT_MODE proxy'sine takılmadan gerçek Mongo'ya yazarız.
    """
    client = await _mongo_or_skip()
    db_name = f"test_split_extra_{uuid.uuid4().hex[:12]}"
    db = client[db_name]

    import core.utils as utils_mod

    monkeypatch.setattr(fhs_mod, "db", db)
    monkeypatch.setattr(utils_mod, "db", db)
    try:
        yield db
    finally:
        await client.drop_database(db_name)
        client.close()


async def _seed_open_folio(db, tenant_id: str, booking_id: str, *, room_charge_total: float):
    """Açık bir folio + üstünde bir oda kalemi tohumla (kaynak folio bakiyesi)."""
    folio_id = str(uuid.uuid4())
    await db.folios.insert_one({
        "id": folio_id,
        "tenant_id": tenant_id,
        "status": "open",
        "booking_id": booking_id,
        "folio_number": "1001",
        "balance": 0.0,
    })
    await db.folio_charges.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "folio_id": folio_id,
        "description": "Oda ücreti",
        "amount": room_charge_total,
        "total": room_charge_total,
        "voided": False,
    })
    return folio_id


async def test_live_split_moves_extra_charge_into_new_folio_with_real_balances(live_db):
    db = live_db
    tenant_id = "t-live-1"
    booking_id = "BK-live-1"

    source_folio_id = await _seed_open_folio(db, tenant_id, booking_id, room_charge_total=500.0)

    # Ekstra masraf (booking kapsamlı, folio_id YOK) oluştur.
    extra_id = "EC-live-1"
    await db.extra_charges.insert_one({
        "id": extra_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "description": "SPA Masaj",
        "charge_name": "SPA Masaj",
        "category": "spa",
        "charge_category": "spa",
        "amount": 150.0,
        "quantity": 1,
        "total": 150.0,
        "voided": False,
    })

    # Kaynak folio bakiyesi (gerçek aggregation) split ÖNCESİ.
    from core.utils import calculate_folio_balance
    source_balance_before = await calculate_folio_balance(source_folio_id, tenant_id)
    assert source_balance_before == 500.0

    res = await FolioHardeningService().split_folio(
        tenant_id, source_folio_id, [extra_id], "guest", "ekstra ayrıştırma", "u1"
    )

    assert res["success"] is True
    assert res["transferred_charges"] == 1
    assert res["transferred_amount"] == 150.0
    new_folio_id = res["new_folio"]["id"]

    # Yeni folio'da normalize edilmiş folio kalemi yazıldı (gerçek find).
    moved = await db.folio_charges.find(
        {"folio_id": new_folio_id, "tenant_id": tenant_id}, {"_id": 0}
    ).to_list(100)
    assert len(moved) == 1
    assert moved[0]["description"] == "SPA Masaj"
    assert moved[0]["total"] == 150.0
    assert moved[0]["split_from_extra_charge_id"] == extra_id
    assert moved[0]["voided"] is False

    # Orijinal extra_charges satırı GERÇEKTEN silindi.
    assert await db.extra_charges.find_one({"id": extra_id}) is None

    # Bakiyeler gerçek aggregation ile tutarlı: kaynak etkilenmedi, yeni = 150.
    source_balance_after = await calculate_folio_balance(source_folio_id, tenant_id)
    new_balance = await calculate_folio_balance(new_folio_id, tenant_id)
    assert source_balance_after == 500.0
    assert new_balance == 150.0

    # Persist edilen folio bakiyesi de güncellendi.
    new_folio_doc = await db.folios.find_one({"id": new_folio_id})
    assert new_folio_doc["balance"] == 150.0


async def test_live_split_mixed_folio_and_extra_charge_balances(live_db):
    db = live_db
    tenant_id = "t-live-2"
    booking_id = "BK-live-2"

    source_folio_id = await _seed_open_folio(db, tenant_id, booking_id, room_charge_total=400.0)

    # Kaynak folioya ek bir folio kalemi (bu split'te taşınacak).
    moveable_charge_id = "FC-live-1"
    await db.folio_charges.insert_one({
        "id": moveable_charge_id,
        "tenant_id": tenant_id,
        "folio_id": source_folio_id,
        "description": "Minibar",
        "amount": 60.0,
        "total": 60.0,
        "voided": False,
    })
    # Booking kapsamlı ekstra masraf (minimal şekil — total/voided YOK).
    extra_id = "EC-live-2"
    await db.extra_charges.insert_one({
        "id": extra_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "charge_name": "Geç Çıkış Ücreti",
        "charge_amount": 40.0,
        "category": "room",
    })

    from core.utils import calculate_folio_balance
    # Split öncesi kaynak bakiye = oda(400) + minibar(60) = 460 (ekstra hariç).
    assert await calculate_folio_balance(source_folio_id, tenant_id) == 460.0

    res = await FolioHardeningService().split_folio(
        tenant_id, source_folio_id, [moveable_charge_id, extra_id],
        "company", "kurumsal ayrıştırma", "u1"
    )

    assert res["success"] is True
    assert res["transferred_charges"] == 2
    assert res["transferred_amount"] == 100.0
    new_folio_id = res["new_folio"]["id"]

    # Folio kalemi folio_id taşındı.
    moved_charge = await db.folio_charges.find_one({"id": moveable_charge_id})
    assert moved_charge["folio_id"] == new_folio_id

    # Ekstra masraf normalize edildi + silindi.
    moved_extra = await db.folio_charges.find(
        {"split_from_extra_charge_id": extra_id, "tenant_id": tenant_id}, {"_id": 0}
    ).to_list(10)
    assert len(moved_extra) == 1
    assert moved_extra[0]["folio_id"] == new_folio_id
    assert moved_extra[0]["total"] == 40.0
    assert moved_extra[0]["description"] == "Geç Çıkış Ücreti"
    assert await db.extra_charges.find_one({"id": extra_id}) is None

    # Bakiyeler: kaynak = oda(400), yeni = minibar(60) + ekstra(40) = 100.
    assert await calculate_folio_balance(source_folio_id, tenant_id) == 400.0
    assert await calculate_folio_balance(new_folio_id, tenant_id) == 100.0


async def test_live_split_rejects_foreign_booking_extra_charge_fail_closed(live_db):
    db = live_db
    tenant_id = "t-live-3"
    booking_id = "BK-live-3"

    source_folio_id = await _seed_open_folio(db, tenant_id, booking_id, room_charge_total=200.0)

    # Başka bir booking'e ait ekstra masraf — kaynak folionun booking'i ile eşleşmez.
    foreign_id = "EC-foreign"
    await db.extra_charges.insert_one({
        "id": foreign_id,
        "tenant_id": tenant_id,
        "booking_id": "OTHER-BOOKING",
        "description": "Başka rezervasyon",
        "total": 99.0,
        "voided": False,
    })

    folios_before = await db.folios.count_documents({"tenant_id": tenant_id})

    res = await FolioHardeningService().split_folio(
        tenant_id, source_folio_id, [foreign_id], "guest", "yabancı", "u1"
    )

    assert res["success"] is False
    # Fail-closed: yeni folio yazılmadı, yabancı ekstra masraf silinmedi.
    assert await db.folios.count_documents({"tenant_id": tenant_id}) == folios_before
    assert await db.extra_charges.find_one({"id": foreign_id}) is not None
