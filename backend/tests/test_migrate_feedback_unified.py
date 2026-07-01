"""Birleşik geri bildirim migration — birim testleri.

Kanıtlanan davranışlar:
- Üç kaynak kanonik ``feedback_entries``'e materyalize edilir (source ayrımı korunur).
- Idempotent: re-run çift kayıt ÜRETMEZ (dedup_key upsert).
- ``id``'siz kaynak doc atlanır (kararlı dedup anahtarı yok → çift sayım riski).
- Dry-run hiçbir şey yazmaz.
- Rollback yalnız migrate marker'lı kayıtları siler.
- Fail-closed: ALLOW_FEEDBACK_MIGRATION olmadan --apply reddedilir.

Gerçek Mongo'ya bağlanmaz; sahte koleksiyonlar kullanılır.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import scripts.migrate_feedback_unified as mig
from modules.guest_journey import feedback_reporting_service as fr


# ── Sahte DB ────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def max_time_ms(self, *a, **k):
        return self

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def _match(doc, flt):
    return all(doc.get(k) == v for k, v in flt.items())


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])   # kaynak koleksiyon içeriği
        self.store: dict = {}          # birleşik koleksiyon: dedup_key -> doc

    def find(self, query=None, projection=None, *a, **k):
        if query:
            return _Cursor([d for d in self.docs if _match(d, query)])
        return _Cursor(self.docs)

    async def find_one(self, flt, projection=None, *a, **k):
        return self.store.get(flt.get("dedup_key"))

    async def update_one(self, flt, update, upsert=False, *a, **k):
        key = flt["dedup_key"]
        if key in self.store:
            return SimpleNamespace(upserted_id=None)
        if upsert:
            self.store[key] = dict(update["$setOnInsert"])
            return SimpleNamespace(upserted_id=key)
        return SimpleNamespace(upserted_id=None)

    async def count_documents(self, flt, *a, **k):
        return len([d for d in self.store.values() if _match(d, flt)])

    async def delete_many(self, flt, *a, **k):
        keys = [k2 for k2, d in self.store.items() if _match(d, flt)]
        for k2 in keys:
            del self.store[k2]
        return SimpleNamespace(deleted_count=len(keys))

    async def create_index(self, *a, **k):
        return "idx"

    async def distinct(self, key, *a, **k):
        return list({d.get(key) for d in self.docs if d.get(key)})


class _DB:
    def __init__(self, **colls):
        self._colls = dict(colls)

    def __getitem__(self, name):
        return self._colls.setdefault(name, _Coll())


def _seeded_db():
    return _DB(
        nps_surveys=_Coll([
            {"id": "n1", "tenant_id": "t1", "nps_score": 9, "category": "promoter",
             "responded_at": "2026-06-01T00:00:00"},
            {"id": "n2", "tenant_id": "t1", "nps_score": 3, "category": "detractor",
             "responded_at": "2026-06-02T00:00:00"},
        ]),
        survey_responses=_Coll([
            {"id": "s1", "tenant_id": "t1", "overall_rating": 4.0,
             "submitted_at": "2026-06-03T00:00:00"},
            {"tenant_id": "t1", "overall_rating": 5.0},  # id YOK → atlanır
        ]),
        guest_reviews=_Coll([
            {"id": "g1", "tenant_id": "t1", "rating": 5,
             "created_at": "2026-06-04T00:00:00"},
        ]),
        feedback_entries=_Coll(),
    )


# ── Migration ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_migrate_apply_materializes_all_sources():
    db = _seeded_db()
    per_source = await mig._migrate_tenant(db, "t1", apply=True)
    store = db["feedback_entries"].store
    # 2 nps + 1 survey (id'li) + 1 review = 4 kanonik kayıt
    assert len(store) == 4
    sources = sorted(d["source"] for d in store.values())
    assert sources == [
        fr.SOURCE_GUEST_REVIEW, fr.SOURCE_NPS_SURVEY,
        fr.SOURCE_NPS_SURVEY, fr.SOURCE_SURVEY_RESPONSE,
    ]
    # id'siz survey_response atlandı.
    assert per_source[fr.SOURCE_SURVEY_RESPONSE]["written"] == 1
    assert per_source[fr.SOURCE_SURVEY_RESPONSE]["skipped"] == 1
    # Yalnız nps_survey kaynağı nps_eligible.
    eligible = [d for d in store.values() if d["nps_eligible"]]
    assert all(d["source"] == fr.SOURCE_NPS_SURVEY for d in eligible)
    assert len(eligible) == 2
    # Marker'lar yazıldı.
    assert all(d["migrated_by"] == mig.MIGRATION_MARKER for d in store.values())


@pytest.mark.asyncio
async def test_migrate_is_idempotent():
    db = _seeded_db()
    await mig._migrate_tenant(db, "t1", apply=True)
    before = dict(db["feedback_entries"].store)
    second = await mig._migrate_tenant(db, "t1", apply=True)
    # Re-run yeni kayıt yazmaz (çift sayım yok).
    assert db["feedback_entries"].store == before
    assert second[fr.SOURCE_NPS_SURVEY]["written"] == 0
    assert second[fr.SOURCE_NPS_SURVEY]["skipped"] == 2


@pytest.mark.asyncio
async def test_migrate_streams_all_records_no_artificial_cap():
    """Büyük tenant regresyonu: yapay tavan olmadan TÜM kayıtlar tek çalıştırmada
    migrate edilir (kayıt atlanmaz). Idempotent rerun yeni kayıt yazmaz."""
    big = [
        {"id": f"n{i}", "tenant_id": "t1", "nps_score": 9, "category": "promoter",
         "responded_at": "2026-06-01T00:00:00"}
        for i in range(250)
    ]
    db = _DB(
        nps_surveys=_Coll(big),
        survey_responses=_Coll(),
        guest_reviews=_Coll(),
        feedback_entries=_Coll(),
    )
    first = await mig._migrate_tenant(db, "t1", apply=True)
    assert first[fr.SOURCE_NPS_SURVEY]["found"] == 250
    assert first[fr.SOURCE_NPS_SURVEY]["written"] == 250
    assert len(db["feedback_entries"].store) == 250
    second = await mig._migrate_tenant(db, "t1", apply=True)
    assert second[fr.SOURCE_NPS_SURVEY]["written"] == 0
    assert len(db["feedback_entries"].store) == 250


@pytest.mark.asyncio
async def test_migrate_dry_run_writes_nothing():
    db = _seeded_db()
    per_source = await mig._migrate_tenant(db, "t1", apply=False)
    assert db["feedback_entries"].store == {}
    # Dry-run yine de ne yazılacağını sayar.
    assert per_source[fr.SOURCE_NPS_SURVEY]["written"] == 2


# ── Rollback ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rollback_deletes_only_migrated():
    db = _seeded_db()
    await mig._migrate_tenant(db, "t1", apply=True)
    # Migrate olmamış bir kaydı elle ekle (rollback dokunmamalı).
    db["feedback_entries"].store["manual"] = {
        "tenant_id": "t1", "source": fr.SOURCE_NPS_SURVEY, "migrated_by": "other",
    }
    deleted = await mig._rollback_tenant(db, "t1", apply=True)
    assert deleted == 4
    remaining = list(db["feedback_entries"].store.values())
    assert remaining == [{"tenant_id": "t1", "source": fr.SOURCE_NPS_SURVEY,
                          "migrated_by": "other"}]


@pytest.mark.asyncio
async def test_rollback_dry_run_keeps_data():
    db = _seeded_db()
    await mig._migrate_tenant(db, "t1", apply=True)
    count = await mig._rollback_tenant(db, "t1", apply=False)
    assert count == 4
    assert len(db["feedback_entries"].store) == 4  # silinmedi


# ── Fail-closed ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_without_env_is_refused(monkeypatch):
    monkeypatch.delenv(mig.ALLOW_ENV, raising=False)
    called = {"system_db": False}

    def _boom():
        called["system_db"] = True
        raise AssertionError("get_system_db çağrılmamalıydı")

    monkeypatch.setattr(mig, "get_system_db", _boom)
    args = SimpleNamespace(apply=True, rollback=False, tenant_id=None)
    rc = await mig.run(args)
    assert rc == 2
    assert called["system_db"] is False


@pytest.mark.asyncio
async def test_apply_with_env_proceeds(monkeypatch):
    monkeypatch.setenv(mig.ALLOW_ENV, "true")
    db = _seeded_db()
    monkeypatch.setattr(mig, "get_system_db", lambda: db)
    args = SimpleNamespace(apply=True, rollback=False, tenant_id="t1")
    rc = await mig.run(args)
    assert rc == 0
    assert len(db["feedback_entries"].store) == 4
