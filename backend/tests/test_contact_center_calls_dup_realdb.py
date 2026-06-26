"""Contact Center Faz 2 — GERÇEK MongoDB ile çift-çağrı (race) kanıtı.

Bu dosya, sahte-Mongo entegrasyon testlerinin (``test_contact_center_faz2_voice_webhooks.py``)
kanıtlayamadığı tek şeyi kanıtlar: Twilio aynı gelen çağrı webhook'unu eşzamanlı /
retry ile gönderdiğinde **veritabanı seviyesinde** tek bir çağrı satırı oluştuğunu.
Bunu garanti eden tek şey ``ux_cc_calls_provider_sid`` PARTIAL-UNIQUE index'idir;
sahte Mongo bu index ve eşzamanlı upsert semantiğini birebir yansıtmaz.

Doktrin (no fake-green):
- Index gerçek Mongo'da kurulur (perf_indexes.py ile birebir aynı spec) ve gerçekten
  zorlanır. Eşzamanlı ``record_inbound_call`` çağrıları gerçek ``find_one_and_update``
  upsert + DuplicateKeyError yolundan geçer.
- Pilot/uretim verisi KİRLETİLMEZ: testler tek-kullanımlık, rastgele adlı ayrı bir
  veritabaninda çalışır ve test sonunda bu veritabani drop edilir (pilot_drift=0).
- Canlı Mongo yoksa kibarca SKIP olur; sahte yeşil üretmez.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from domains.contact_center.voice_ingest import record_inbound_call

_COLLECTION = "contact_center_calls"
_STALE_DB_PREFIX = "syroce_duptest_"
_TENANT = f"dup-test-{uuid.uuid4().hex[:8]}"
_SID = f"CA{uuid.uuid4().hex}{uuid.uuid4().hex}"[:34]
_FROM = "+905551112233"

# perf_indexes.py ile BİREBİR aynı index spec (tek doğruluk kaynağı orası; burada
# gerçek index'in davranışını DB seviyesinde kanıtlamak için yeniden kuruyoruz).
_INDEX_NAME = "ux_cc_calls_provider_sid"
_INDEX_KEYS = [("tenant_id", 1), ("provider_call_sid", 1)]
_INDEX_OPTS = {
    "name": _INDEX_NAME,
    "unique": True,
    "partialFilterExpression": {"provider_call_sid": {"$type": "string"}},
}


def _mongo_url() -> str | None:
    # conftest, MONGO_URL yoksa MONGO_ATLAS_URI'den doldurur.
    return os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")


async def _make_test_db():
    """Tek-kullanımlık, rastgele adlı bir test veritabanı + index hazırlar.

    Canlı Mongo'ya kısa zaman aşımıyla ping atar; erişilemezse SKIP döner.
    """
    url = _mongo_url()
    if not url:
        pytest.skip("Canlı Mongo yok (MONGO_URL/MONGO_ATLAS_URI set degil)")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=4000)
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001 — canlı DB yoksa kibar skip
        client.close()
        pytest.skip(f"Canlı Mongo'ya baglanilamadi: {type(exc).__name__}")
    # Sertleştirme: finally-dışı sonlanma (ör. SIGKILL) bıraktıysa eski test
    # veritabanlarını best-effort temizle. Paralel CI koşularının TAZE DB'lerini
    # silmemek için YALNIZCA yeterince eski (>1 saat) olanları drop et — adın
    # içine gömülü epoch saniyesinden yaşı çözeriz. Yetki/erişim kısıtı varsa geç.
    now = int(time.time())
    try:
        for name in await client.list_database_names():
            if not name.startswith(_STALE_DB_PREFIX):
                continue
            try:
                created = int(name[len(_STALE_DB_PREFIX):].split("_", 1)[0])
            except (ValueError, IndexError):
                continue
            if now - created > 3600:
                await client.drop_database(name)
    except Exception:  # noqa: BLE001 — temizlik best-effort, testi bloklamaz
        pass
    db_name = f"{_STALE_DB_PREFIX}{now}_{uuid.uuid4().hex[:12]}"
    db = client[db_name]
    await db[_COLLECTION].create_index(_INDEX_KEYS, **_INDEX_OPTS)
    return client, db, db_name


class _RaiseOnUpdateColl:
    """find_one_and_update'i GERÇEK ``DuplicateKeyError`` ile reddeder (yarışın
    kaybeden tarafını deterministik canlandırır); find_one'ı gerçek koleksiyona
    geçirir → fallback gerçek satırı okur."""

    def __init__(self, real_coll):
        self._real = real_coll

    async def find_one_and_update(self, *a, **k):
        raise DuplicateKeyError("E11000 duplicate key (simulated race loser)")

    async def find_one(self, *a, **k):
        return await self._real.find_one(*a, **k)


class _ProxyDB:
    """Yalnızca hedef koleksiyon için find_one_and_update'i reddeden ince proxy.
    Diğer her şey gerçek veritabanına gider."""

    def __init__(self, real_db, coll_name):
        self._real_db = real_db
        self._coll_name = coll_name

    def __getitem__(self, name):
        coll = self._real_db[name]
        if name == self._coll_name:
            return _RaiseOnUpdateColl(coll)
        return coll


@pytest.mark.asyncio
async def test_concurrent_inbound_webhook_creates_single_row():
    """Aynı (tenant, CallSid) için EŞZAMANLI 8 record_inbound_call → tek satır."""
    client, db, db_name = await _make_test_db()
    try:
        results = await asyncio.gather(
            *[
                record_inbound_call(
                    db,
                    tenant_id=_TENANT,
                    provider_call_sid=_SID,
                    from_phone=_FROM,
                )
                for _ in range(8)
            ]
        )
        # Yalnızca tek satır oluşmalı (unique index race'i kazananı belirler).
        count = await db[_COLLECTION].count_documents(
            {"tenant_id": _TENANT, "provider_call_sid": _SID}
        )
        assert count == 1, f"beklenen 1 satir, bulunan {count}"
        # Tüm eşzamanlı çağrılar AYNI id'yi döndürmeli (kaybeden DuplicateKeyError
        # yolu mevcut satırı okuyup aynı id'yi verir).
        assert all(r is not None for r in results)
        assert len(set(results)) == 1, f"id'ler ayrismis: {set(results)}"
        # Dönen id, gerçekten DB'deki satırın id'si olmalı.
        doc = await db[_COLLECTION].find_one(
            {"tenant_id": _TENANT, "provider_call_sid": _SID}
        )
        assert doc is not None and doc["id"] == results[0]
        # PII düz saklanmaz: ham telefon hiçbir alanda görünmemeli; hash+enc var.
        assert "905551112233" not in str(doc)
        assert doc.get("caller_id_hash") and doc.get("caller_id_enc")
    finally:
        await client.drop_database(db_name)
        client.close()


@pytest.mark.asyncio
async def test_sequential_retry_is_idempotent():
    """Twilio retry'ı (ardışık aynı webhook) yeni satır üretmez, aynı id döner."""
    client, db, db_name = await _make_test_db()
    try:
        first = await record_inbound_call(
            db, tenant_id=_TENANT, provider_call_sid=_SID, from_phone=_FROM
        )
        second = await record_inbound_call(
            db, tenant_id=_TENANT, provider_call_sid=_SID, from_phone=_FROM
        )
        assert first is not None and first == second
        count = await db[_COLLECTION].count_documents(
            {"tenant_id": _TENANT, "provider_call_sid": _SID}
        )
        assert count == 1
    finally:
        await client.drop_database(db_name)
        client.close()


@pytest.mark.asyncio
async def test_duplicate_key_fallback_returns_existing_id():
    """Yarışın KAYBEDEN tarafı (DuplicateKeyError) deterministik kanıt.

    Görev #284 bitiş kriteri: "DuplicateKeyError yolunun mevcut satırı okuyup aynı
    id'yi döndürdüğü gerçek index'le doğrulanır." Burada:
      1) Gerçek unique index kurulu DB'ye ilk satır gerçek upsert ile yazılır (id X).
      2) find_one_and_update GERÇEK DuplicateKeyError ile reddedilir (kaybeden taraf);
         find_one gerçek koleksiyona gider.
      3) _record_call fallback'i mevcut (index-korumalı) satırı okuyup X'i döndürmeli;
         yeni satır OLUŞMAMALI.
    """
    client, db, db_name = await _make_test_db()
    try:
        first = await record_inbound_call(
            db, tenant_id=_TENANT, provider_call_sid=_SID, from_phone=_FROM
        )
        assert first is not None
        proxy = _ProxyDB(db, _COLLECTION)
        # Bu çağrı find_one_and_update'te DuplicateKeyError alır → fallback find_one.
        loser = await record_inbound_call(
            proxy, tenant_id=_TENANT, provider_call_sid=_SID, from_phone=_FROM
        )
        assert loser == first, "fallback mevcut satirin id'sini dondurmeli"
        count = await db[_COLLECTION].count_documents(
            {"tenant_id": _TENANT, "provider_call_sid": _SID}
        )
        assert count == 1, f"fallback yeni satir uretmemeli, bulunan {count}"
    finally:
        await client.drop_database(db_name)
        client.close()


@pytest.mark.asyncio
async def test_distinct_sids_create_distinct_rows():
    """Farklı CallSid'ler ayrı satır üretir (index aşırı-kısıtlama yapmaz)."""
    client, db, db_name = await _make_test_db()
    try:
        sid_a = f"CA{uuid.uuid4().hex}{uuid.uuid4().hex}"[:34]
        sid_b = f"CA{uuid.uuid4().hex}{uuid.uuid4().hex}"[:34]
        id_a = await record_inbound_call(
            db, tenant_id=_TENANT, provider_call_sid=sid_a, from_phone=_FROM
        )
        id_b = await record_inbound_call(
            db, tenant_id=_TENANT, provider_call_sid=sid_b, from_phone=_FROM
        )
        assert id_a and id_b and id_a != id_b
        count = await db[_COLLECTION].count_documents({"tenant_id": _TENANT})
        assert count == 2
    finally:
        await client.drop_database(db_name)
        client.close()
