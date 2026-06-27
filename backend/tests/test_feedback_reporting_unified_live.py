"""Task #322 — Birleşik geri bildirim raporlaması için GERÇEK Mongo doğrulaması.

Task #320'nin birim testleri (`test_feedback_reporting_unified.py`,
`test_migrate_feedback_unified.py`) sahte (in-memory) koleksiyonlar kullanır.
Bu modül aynı davranışı GERÇEK MongoDB üzerinde uçtan uca çalıştırır; böylece
FakeDB'nin taklit edemediği şeyler kanıtlanır:

  * `by_room` server-side aggregation: gerçek `$nin` / `$avg` / `$round` / `$group`,
  * `responded_at` ISO tarih penceresi (`$gte`) gerçek karşılaştırması,
  * migration `dedup_key` üzerinde GERÇEK unique-index idempotency'si,
  * migration --apply / rerun / --rollback gerçek upsert/delete semantiği,
  * çok-kiracılı izolasyon (iki tenant verisi karışmaz),
  * canlı NPS sayısının migration sonrası DEĞİŞMEDİĞİ (parity).

Doctrine: gerçek MongoDB gerektirir (mongomock yok). Bağlanılamazsa testler
atlanır. Her test atılabilir (throwaway) bir veritabanı kullanır ve sonunda
düşürür; pilot/üretim verisine dokunmaz. Validator/assertion gevşetilmez.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - motor always present in backend
    AsyncIOMotorClient = None  # type: ignore

from pymongo.errors import DuplicateKeyError

from modules.guest_journey import feedback_reporting_service as fr
import scripts.migrate_feedback_unified as mig

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

TENANT_A = "tenant-a-live"
TENANT_B = "tenant-b-live"


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
    """Atılabilir gerçek bir veritabanı; servis `db`'sini ona bağlar.

    `feedback_reporting_service` modül seviyesinde `from core.database import db`
    yapar (TenantAwareDBProxy). Sorgular zaten filtrelerinde `tenant_id` taşıdığı
    için izolasyon korunur; proxy'yi by-pass edip plain throwaway Motor db'ye
    yönlendiriyoruz (folio live testindeki desenle aynı).
    """
    client = await _mongo_or_skip()
    db_name = f"test_feedback_unified_{uuid.uuid4().hex[:12]}"
    db = client[db_name]
    monkeypatch.setattr(fr, "db", db)
    try:
        yield db
    finally:
        await client.drop_database(db_name)
        client.close()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _old_iso() -> str:
    return (datetime.now(UTC) - timedelta(days=400)).isoformat()


async def _seed(db) -> dict:
    """Üç kaynak koleksiyonu iki tenant için tohumla. Beklenen sayıları döndür."""
    now = _now_iso()
    old = _old_iso()

    # ── Tenant A — nps_surveys (NPS matematiğine giren tek kaynak) ──
    nps_a = [
        {"id": "a-s1", "tenant_id": TENANT_A, "nps_score": 9, "category": "promoter",
         "room_number": "101", "feedback": "great", "responded_at": now},
        {"id": "a-s2", "tenant_id": TENANT_A, "nps_score": 10, "category": "promoter",
         "room_number": "101", "feedback": "perfect", "responded_at": now},
        {"id": "a-s3", "tenant_id": TENANT_A, "nps_score": 3, "category": "detractor",
         "room_number": "102", "feedback": "bad", "responded_at": now},
        {"id": "a-s4", "tenant_id": TENANT_A, "nps_score": 8, "category": "passive",
         "room_number": None, "feedback": "ok", "responded_at": now},
        {"id": "a-s5", "tenant_id": TENANT_A, "nps_score": 9, "category": "promoter",
         "feedback": "no-room", "responded_at": now},  # room_number alanı YOK
        {"id": "a-s6", "tenant_id": TENANT_A, "nps_score": 10, "category": "promoter",
         "room_number": "103", "feedback": "old", "responded_at": old},  # pencere DIŞI
    ]
    # ── Tenant A — survey_responses (NPS'e KARIŞMAZ) ──
    surveys_a = [
        {"id": "a-sr1", "tenant_id": TENANT_A, "overall_rating": 4.0,
         "survey_name": "Lobby", "submitted_at": now},
        {"tenant_id": TENANT_A, "overall_rating": 5.0, "submitted_at": now},  # id YOK
    ]
    # ── Tenant A — guest_reviews (NPS'e KARIŞMAZ) ──
    reviews_a = [
        {"id": "a-gr1", "tenant_id": TENANT_A, "rating": 5, "comment": "x",
         "created_at": now},
        {"id": "a-gr2", "tenant_id": TENANT_A, "rating": 3, "comment": "y",
         "created_at": now},
    ]
    # ── Tenant B (izolasyon kanıtı) ──
    nps_b = [
        {"id": "b-s1", "tenant_id": TENANT_B, "nps_score": 10, "category": "promoter",
         "room_number": "201", "responded_at": now},
        {"id": "b-s2", "tenant_id": TENANT_B, "nps_score": 0, "category": "detractor",
         "room_number": "202", "responded_at": now},
    ]

    await db.nps_surveys.insert_many(nps_a + nps_b)
    await db.survey_responses.insert_many(surveys_a)
    await db.guest_reviews.insert_many(reviews_a)

    return {
        # migration kanonik sayıları (date filtresi YOK → hepsi materyalize)
        "a_canonical": len(nps_a) + 1 + len(reviews_a),  # 6 + 1(id'li) + 2 = 9
        "a_eligible": len(nps_a),                          # 6 (tüm nps_surveys)
        "b_canonical": len(nps_b),                         # 2
    }


# ── Servis: gerçek Mongo find/aggregate ─────────────────────────

async def test_compute_nps_score_real_mongo_date_window(live_db):
    """NPS skoru gerçek Mongo'dan; pencere DIŞI kayıt (a-s6) sayılmaz."""
    await _seed(live_db)
    out = await fr.compute_nps_score(TENANT_A, days=30)
    # Pencere içi: 3 promoter + 1 passive + 1 detractor = 5 (a-s6 hariç).
    assert out["total_responses"] == 5
    assert out["promoters"] == 3
    assert out["passives"] == 1
    assert out["detractors"] == 1
    assert out["nps_score"] == 40.0  # (3-1)/5*100
    assert out["period_days"] == 30


async def test_compute_nps_score_only_nps_surveys_source(live_db):
    """Çift sayım kanıtı: survey_responses / guest_reviews skoru DEĞİŞTİRMEZ."""
    await _seed(live_db)
    out = await fr.compute_nps_score(TENANT_A, days=30)
    # Sadece nps_surveys sayılır; 1 anket + 2 yorum eklendiği hâlde total=5.
    assert out["total_responses"] == 5


async def test_by_room_real_aggregation(live_db):
    """by_room gerçek $nin/$avg/$round/$group pipeline'ı doğru çalışır."""
    await _seed(live_db)
    out = await fr.by_room(TENANT_A, days=30)
    assert out["period_days"] == 30
    rooms = {r["room_number"]: r for r in out["rooms"]}
    # room_number None (a-s4) ve eksik (a-s5) $nin ile dışlanır; eski (a-s6) tarih
    # filtresiyle dışlanır → yalnız 101 ve 102.
    assert set(rooms.keys()) == {"101", "102"}
    assert rooms["101"]["avg_score"] == 9.5     # (9+10)/2
    assert rooms["101"]["response_count"] == 2
    assert rooms["101"]["promoters"] == 2
    assert rooms["102"]["avg_score"] == 3.0
    assert rooms["102"]["detractors"] == 1


async def test_recent_feedback_real_filters(live_db):
    """recent_feedback gerçek sort/limit + category/room filtreleri."""
    await _seed(live_db)
    base = await fr.recent_feedback(TENANT_A, days=30)
    assert base["count"] == 5  # a-s1..a-s5 (a-s6 pencere dışı)

    promo = await fr.recent_feedback(TENANT_A, days=30, category="promoter")
    assert promo["count"] == 3
    assert {i["id"] for i in promo["items"]} == {"a-s1", "a-s2", "a-s5"}

    room101 = await fr.recent_feedback(TENANT_A, days=30, room_number="101")
    assert {i["id"] for i in room101["items"]} == {"a-s1", "a-s2"}


async def test_service_tenant_isolation(live_db):
    """Tenant A ve B birbirinden bağımsız; sızma yok."""
    await _seed(live_db)
    a = await fr.compute_nps_score(TENANT_A, days=30)
    b = await fr.compute_nps_score(TENANT_B, days=30)
    assert a["total_responses"] == 5
    assert b["total_responses"] == 2
    assert b["nps_score"] == 0.0  # (1-1)/2*100
    recent_a = await fr.recent_feedback(TENANT_A, days=30, limit=200)
    assert all(i["tenant_id"] == TENANT_A for i in recent_a["items"])


# ── Migration: gerçek upsert / idempotency / rollback ───────────

async def test_migration_apply_and_idempotent(live_db):
    counts = await _seed(live_db)
    first = await mig._migrate_tenant(live_db, TENANT_A, apply=True)
    total = await live_db.feedback_entries.count_documents({"tenant_id": TENANT_A})
    assert total == counts["a_canonical"]  # 9
    eligible = await live_db.feedback_entries.count_documents(
        {"tenant_id": TENANT_A, "nps_eligible": True})
    assert eligible == counts["a_eligible"]  # 6 → yalnız nps_surveys
    # id'siz survey_response atlandı.
    assert first[fr.SOURCE_SURVEY_RESPONSE]["written"] == 1
    assert first[fr.SOURCE_SURVEY_RESPONSE]["skipped"] == 1

    # Rerun: yeni kayıt YAZILMAZ (gerçek dedup_key upsert).
    second = await mig._migrate_tenant(live_db, TENANT_A, apply=True)
    total2 = await live_db.feedback_entries.count_documents({"tenant_id": TENANT_A})
    assert total2 == counts["a_canonical"]
    assert second[fr.SOURCE_NPS_SURVEY]["written"] == 0


async def test_migration_rollback_only_marked(live_db):
    await _seed(live_db)
    await mig._migrate_tenant(live_db, TENANT_A, apply=True)
    # Migrate edilmemiş (marker'sız) bir kayıt — rollback dokunmamalı.
    await live_db.feedback_entries.insert_one({
        "tenant_id": TENANT_A, "source": fr.SOURCE_NPS_SURVEY,
        "dedup_key": "manual-keep", "migrated_by": "other_process",
    })
    deleted = await mig._rollback_tenant(live_db, TENANT_A, apply=True)
    assert deleted == 9
    remaining = await live_db.feedback_entries.find(
        {"tenant_id": TENANT_A}).to_list(100)
    assert len(remaining) == 1
    assert remaining[0]["migrated_by"] == "other_process"


async def test_migration_parity_all_endpoints_unchanged(live_db):
    """Migration üç legacy ucun da çıktısını DEĞİŞTİRMEZ (operatör kararı).

    Acceptance: /nps/score|recent|by-room yanıtları migration öncesi/sonrası
    birebir aynı. Uçlar bu servis fonksiyonlarının ince adaptörü olduğundan
    parity servis seviyesinde kanıtlanır.
    """
    await _seed(live_db)
    score_before = await fr.compute_nps_score(TENANT_A, days=30)
    recent_before = await fr.recent_feedback(TENANT_A, days=30, limit=200)
    by_room_before = await fr.by_room(TENANT_A, days=30)
    nps_before = await live_db.nps_surveys.count_documents({"tenant_id": TENANT_A})

    await mig._migrate_tenant(live_db, TENANT_A, apply=True)

    assert await fr.compute_nps_score(TENANT_A, days=30) == score_before
    assert await fr.recent_feedback(TENANT_A, days=30, limit=200) == recent_before
    assert await fr.by_room(TENANT_A, days=30) == by_room_before
    # Kaynak koleksiyona dokunulmadı (materyalizasyon ayrı koleksiyona yazar).
    nps_after = await live_db.nps_surveys.count_documents({"tenant_id": TENANT_A})
    assert nps_after == nps_before


async def test_migration_tenant_isolation(live_db):
    counts = await _seed(live_db)
    await mig._migrate_tenant(live_db, TENANT_A, apply=True)
    # A migrate edildi; B henüz değil.
    assert await live_db.feedback_entries.count_documents({"tenant_id": TENANT_B}) == 0
    await mig._migrate_tenant(live_db, TENANT_B, apply=True)
    assert await live_db.feedback_entries.count_documents(
        {"tenant_id": TENANT_B}) == counts["b_canonical"]
    # A sayısı değişmedi.
    assert await live_db.feedback_entries.count_documents(
        {"tenant_id": TENANT_A}) == counts["a_canonical"]


# ── Migration run(): gerçek unique index + run-log + fail-closed ─

async def test_run_creates_unique_index_and_runlog(live_db, monkeypatch):
    await _seed(live_db)
    monkeypatch.setattr(mig, "get_system_db", lambda: live_db)
    monkeypatch.setenv(mig.ALLOW_ENV, "true")

    import argparse
    args = argparse.Namespace(apply=True, rollback=False, tenant_id=TENANT_A)
    rc = await mig.run(args)
    assert rc == 0

    # GERÇEK unique index: aynı dedup_key ile elle insert E11000 verir.
    indexes = await live_db.feedback_entries.index_information()
    assert any(
        idx.get("unique") and idx.get("key") == [("dedup_key", 1)]
        for idx in indexes.values()
    )
    existing = await live_db.feedback_entries.find_one({"tenant_id": TENANT_A})
    with pytest.raises(DuplicateKeyError):
        await live_db.feedback_entries.insert_one(
            {"dedup_key": existing["dedup_key"], "tenant_id": TENANT_A})

    # PII'siz run-log özeti yazıldı.
    run_log = await live_db[mig.RUN_LOG_COLLECTION].find_one({})
    assert run_log is not None
    assert run_log["mode"] == "migrate"
    assert run_log["applied"] is True


async def test_run_apply_without_env_refused(live_db, monkeypatch):
    """Fail-closed: ALLOW_FEEDBACK_MIGRATION yoksa --apply reddedilir, yazım yok."""
    await _seed(live_db)
    monkeypatch.delenv(mig.ALLOW_ENV, raising=False)

    def _boom():
        raise AssertionError("get_system_db çağrılmamalıydı")

    monkeypatch.setattr(mig, "get_system_db", _boom)
    import argparse
    args = argparse.Namespace(apply=True, rollback=False, tenant_id=TENANT_A)
    rc = await mig.run(args)
    assert rc == 2
    # Hiçbir kanonik kayıt yazılmadı.
    assert await live_db.feedback_entries.count_documents({}) == 0
