"""Birleşik geri bildirim raporlama modeli — birim testleri.

NPS Raporlama Birleştirme görevi. Kanıtlanan davranışlar:
- Normalizerlar her kaynağı kanonik kayda doğru çevirir (source ayrımı + nps_eligible).
- NPS skoru/son yorumlar/oda raporu YALNIZ nps_survey kaynağından gelir ve legacy
  davranışla birebir aynıdır (çift sayım YOK; 1-5 yorum/anket NPS'i değiştirmez).
- Migration idempotenttir (dedup_key) ve rollback yalnız migrate kayıtları siler.

Test DB'si gerçek Mongo'ya bağlanmaz; SimpleNamespace tabanlı sahte koleksiyonlar
kullanılır (test_nps_duplicate_guard.py deseni).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.guest_journey import feedback_reporting_service as fr


# ── Sahte DB altyapısı ──────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    async def to_list(self, *a, **k):
        return list(self._docs)


class _FindColl:
    """find()/aggregate() döndüren sahte koleksiyon. Son sorguyu kaydeder."""

    def __init__(self, find_docs=None, aggregate_rows=None):
        self._find_docs = find_docs or []
        self._aggregate_rows = aggregate_rows or []
        self.find_queries = []
        self.aggregate_pipelines = []

    def find(self, query=None, projection=None, *a, **k):
        self.find_queries.append(query)
        return _Cursor(self._find_docs)

    def aggregate(self, pipeline, *a, **k):
        self.aggregate_pipelines.append(pipeline)
        return _Cursor(self._aggregate_rows)


def _db(**colls):
    return SimpleNamespace(**colls)


# ── star_to_nps ─────────────────────────────────────────────────

def test_star_to_nps_bounds():
    assert fr.star_to_nps(1) == 0
    assert fr.star_to_nps(3) == 5
    assert fr.star_to_nps(5) == 10
    assert fr.star_to_nps(None) is None
    # Sonuç 0-10 aralığında kalır (lineer skala).
    for r in (1, 2, 3, 4, 5):
        v = fr.star_to_nps(r)
        assert 0 <= v <= 10


def test_nps_category_thresholds():
    assert fr.nps_category(0) == "detractor"
    assert fr.nps_category(6) == "detractor"
    assert fr.nps_category(7) == "passive"
    assert fr.nps_category(8) == "passive"
    assert fr.nps_category(9) == "promoter"
    assert fr.nps_category(10) == "promoter"


def test_bounded_days_clamps():
    assert fr.bounded_days(0) == 1
    assert fr.bounded_days(-5) == 1
    assert fr.bounded_days(30) == 30
    assert fr.bounded_days(9999) == fr.MAX_DAYS


# ── Normalizerlar ───────────────────────────────────────────────

def test_normalize_nps_survey_is_eligible():
    doc = {
        "id": "n1", "tenant_id": "t1", "nps_score": 9, "category": "promoter",
        "room_number": "101", "guest_name": "A", "feedback": "great",
        "source": "manual", "responded_at": "2026-06-01T00:00:00",
    }
    c = fr.normalize(fr.SOURCE_NPS_SURVEY, doc)
    assert c["source"] == fr.SOURCE_NPS_SURVEY
    assert c["source_id"] == "n1"
    assert c["nps_score"] == 9
    assert c["category"] == "promoter"
    assert c["nps_eligible"] is True
    assert c["comment"] == "great"
    assert c["channel"] == "manual"


def test_normalize_nps_survey_score_zero_preserved():
    # nps_score=0 falsy olsa da düşmemeli (detractor).
    doc = {"id": "n0", "tenant_id": "t1", "nps_score": 0, "responded_at": "x"}
    c = fr.normalize(fr.SOURCE_NPS_SURVEY, doc)
    assert c["nps_score"] == 0
    assert c["category"] == "detractor"
    assert c["nps_eligible"] is True


def test_normalize_guest_review_not_eligible():
    doc = {
        "id": "g1", "tenant_id": "t1", "rating": 5, "comment": "nice",
        "source": "direct_invite", "created_at": "2026-06-02T00:00:00",
    }
    c = fr.normalize(fr.SOURCE_GUEST_REVIEW, doc)
    assert c["source"] == fr.SOURCE_GUEST_REVIEW
    assert c["star_rating"] == 5
    assert c["nps_score"] == 10        # bilgi amaçlı dönüşüm
    assert c["category"] is None       # NPS kategorisi YOK
    assert c["nps_eligible"] is False  # NPS matematiğine girmez
    assert c["responded_at"] == "2026-06-02T00:00:00"


def test_normalize_survey_response_not_eligible():
    doc = {
        "id": "s1", "tenant_id": "t1", "overall_rating": 4.2,
        "survey_name": "Lobby", "submitted_at": "2026-06-03T00:00:00",
        "booking_id": "b1",
    }
    c = fr.normalize(fr.SOURCE_SURVEY_RESPONSE, doc)
    assert c["source"] == fr.SOURCE_SURVEY_RESPONSE
    assert c["overall_rating"] == 4.2
    assert c["nps_score"] is None
    assert c["nps_eligible"] is False
    assert c["responded_at"] == "2026-06-03T00:00:00"


def test_only_nps_survey_source_is_nps_eligible():
    assert fr.NPS_ELIGIBLE_SOURCES == (fr.SOURCE_NPS_SURVEY,)


def test_normalize_unknown_source_raises():
    with pytest.raises(ValueError):
        fr.normalize("bogus", {"id": "x"})


# ── compute_nps_score (legacy birebir + çift sayım yok) ─────────

@pytest.mark.asyncio
async def test_compute_nps_score_matches_legacy_formula(monkeypatch):
    surveys = (
        [{"category": "promoter"}] * 6
        + [{"category": "passive"}] * 2
        + [{"category": "detractor"}] * 2
    )
    db = _db(nps_surveys=_FindColl(find_docs=surveys))
    monkeypatch.setattr(fr, "db", db)
    out = await fr.compute_nps_score("t1", days=30)
    # (6 - 2) / 10 * 100 = 40.0
    assert out["nps_score"] == 40.0
    assert out["promoters"] == 6
    assert out["passives"] == 2
    assert out["detractors"] == 2
    assert out["total_responses"] == 10
    assert out["period_days"] == 30


@pytest.mark.asyncio
async def test_compute_nps_score_empty(monkeypatch):
    db = _db(nps_surveys=_FindColl(find_docs=[]))
    monkeypatch.setattr(fr, "db", db)
    out = await fr.compute_nps_score("t1", days=45)
    assert out == {
        "nps_score": 0, "total_responses": 0, "promoters": 0,
        "passives": 0, "detractors": 0, "period_days": 45,
    }


@pytest.mark.asyncio
async def test_compute_nps_score_reads_only_nps_surveys(monkeypatch):
    """Çift sayım kanıtı: skor sadece nps_surveys'ten okunur; guest_reviews /
    survey_responses koleksiyonlarına HİÇ dokunulmaz."""
    nps = _FindColl(find_docs=[{"category": "promoter"}])
    reviews = _FindColl(find_docs=[{"category": "promoter"}] * 99)
    responses = _FindColl(find_docs=[{"category": "promoter"}] * 99)
    db = _db(nps_surveys=nps, guest_reviews=reviews, survey_responses=responses)
    monkeypatch.setattr(fr, "db", db)
    out = await fr.compute_nps_score("t1")
    assert out["total_responses"] == 1     # yalnız nps_surveys sayıldı
    assert reviews.find_queries == []
    assert responses.find_queries == []


@pytest.mark.asyncio
async def test_compute_nps_score_query_is_tenant_scoped(monkeypatch):
    nps = _FindColl(find_docs=[])
    monkeypatch.setattr(fr, "db", _db(nps_surveys=nps))
    await fr.compute_nps_score("tenant-xyz", days=10)
    q = nps.find_queries[0]
    assert q["tenant_id"] == "tenant-xyz"
    assert "$gte" in q["responded_at"]


# ── recent_feedback ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recent_feedback_shape_and_filters(monkeypatch):
    docs = [{"id": "n1", "category": "detractor", "room_number": "101"}]
    nps = _FindColl(find_docs=docs)
    monkeypatch.setattr(fr, "db", _db(nps_surveys=nps))
    out = await fr.recent_feedback("t1", days=30, limit=5,
                                   category="detractor", room_number="101")
    assert out == {"items": docs, "count": 1}
    q = nps.find_queries[0]
    assert q["tenant_id"] == "t1"
    assert q["category"] == "detractor"
    assert q["room_number"] == "101"


@pytest.mark.asyncio
async def test_recent_feedback_ignores_invalid_category(monkeypatch):
    nps = _FindColl(find_docs=[])
    monkeypatch.setattr(fr, "db", _db(nps_surveys=nps))
    await fr.recent_feedback("t1", category="bogus")
    q = nps.find_queries[0]
    assert "category" not in q


# ── by_room ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_by_room_shape_and_pipeline(monkeypatch):
    rows = [{"room_number": "101", "avg_score": 3.0, "response_count": 2}]
    nps = _FindColl(aggregate_rows=rows)
    monkeypatch.setattr(fr, "db", _db(nps_surveys=nps))
    out = await fr.by_room("t1", days=30)
    assert out == {"rooms": rows, "period_days": 30}
    pipeline = nps.aggregate_pipelines[0]
    match = pipeline[0]["$match"]
    assert match["tenant_id"] == "t1"
    # Oda numarası boş/None kayıtlar dışlanır.
    assert match["room_number"] == {"$nin": [None, ""]}


# ── Fiziksel cutover: feature-flag'li okuma yolu ────────────────

def test_unified_read_disabled_by_default(monkeypatch):
    monkeypatch.delenv(fr.UNIFIED_READ_ENV, raising=False)
    assert fr.unified_read_enabled() is False


def test_unified_read_flag_parsing(monkeypatch):
    for val, expected in (("true", True), ("TRUE", True), (" true ", True),
                          ("false", False), ("1", False), ("", False)):
        monkeypatch.setenv(fr.UNIFIED_READ_ENV, val)
        assert fr.unified_read_enabled() is expected


def test_dedup_key_format():
    assert fr.dedup_key("t1", fr.SOURCE_NPS_SURVEY, "n1") == "t1|nps_survey|n1"


@pytest.mark.asyncio
async def test_compute_nps_score_unified_reads_feedback_entries(monkeypatch):
    """Flag AÇIK iken skor feedback_entries'ten (nps_eligible filtresiyle)
    okunur; nps_surveys'e HİÇ dokunulmaz."""
    monkeypatch.setenv(fr.UNIFIED_READ_ENV, "true")
    cats = [{"category": "promoter"}] * 6 + [{"category": "detractor"}] * 4
    unified = _FindColl(find_docs=cats)
    legacy = _FindColl(find_docs=[{"category": "promoter"}] * 99)
    monkeypatch.setattr(fr, "db", _db(feedback_entries=unified, nps_surveys=legacy))
    out = await fr.compute_nps_score("t1", days=30)
    # (6 - 4) / 10 * 100 = 20.0
    assert out["nps_score"] == 20.0
    assert out["total_responses"] == 10
    assert legacy.find_queries == []          # legacy okunmadı
    q = unified.find_queries[0]
    assert q["tenant_id"] == "t1"
    assert q["nps_eligible"] is True
    assert "$gte" in q["responded_at"]


@pytest.mark.asyncio
async def test_compute_nps_score_unified_matches_legacy(monkeypatch):
    """Aynı kategori dağılımı → flag açık/kapalı birebir aynı skor (parity)."""
    cats = [{"category": "promoter"}] * 5 + [{"category": "passive"}] * 3 + [{"category": "detractor"}] * 2
    monkeypatch.delenv(fr.UNIFIED_READ_ENV, raising=False)
    monkeypatch.setattr(fr, "db", _db(nps_surveys=_FindColl(find_docs=list(cats))))
    legacy_out = await fr.compute_nps_score("t1", days=30)
    monkeypatch.setenv(fr.UNIFIED_READ_ENV, "true")
    monkeypatch.setattr(fr, "db", _db(feedback_entries=_FindColl(find_docs=list(cats))))
    unified_out = await fr.compute_nps_score("t1", days=30)
    assert legacy_out == unified_out


@pytest.mark.asyncio
async def test_recent_feedback_unified_maps_to_legacy_shape(monkeypatch):
    """Flag AÇIK iken kanonik kayıt legacy nps_surveys biçimine çevrilir."""
    monkeypatch.setenv(fr.UNIFIED_READ_ENV, "true")
    canonical = [{
        "source": fr.SOURCE_NPS_SURVEY, "source_id": "n1", "tenant_id": "t1",
        "nps_score": 9, "category": "promoter", "room_number": "101",
        "guest_name": "A", "guest_id": "g1", "booking_id": "b1",
        "comment": "great", "channel": "manual", "recorded_by": "Murat",
        "recorded_by_id": "u1", "responded_at": "2026-06-01T00:00:00",
        "nps_eligible": True, "dedup_key": "t1|nps_survey|n1",
    }]
    unified = _FindColl(find_docs=canonical)
    monkeypatch.setattr(fr, "db", _db(feedback_entries=unified))
    out = await fr.recent_feedback("t1", days=30)
    assert out["count"] == 1
    item = out["items"][0]
    # Legacy POST /nps/survey biçimi: feedback=comment, source=channel.
    assert item == {
        "id": "n1", "tenant_id": "t1", "guest_id": "g1", "booking_id": "b1",
        "room_number": "101", "guest_name": "A", "nps_score": 9,
        "category": "promoter", "feedback": "great", "source": "manual",
        "recorded_by": "Murat", "recorded_by_id": "u1",
        "responded_at": "2026-06-01T00:00:00",
    }
    q = unified.find_queries[0]
    assert q["nps_eligible"] is True


@pytest.mark.asyncio
async def test_by_room_unified_adds_eligible_filter(monkeypatch):
    monkeypatch.setenv(fr.UNIFIED_READ_ENV, "true")
    rows = [{"room_number": "101", "avg_score": 3.0, "response_count": 2}]
    unified = _FindColl(aggregate_rows=rows)
    monkeypatch.setattr(fr, "db", _db(feedback_entries=unified))
    out = await fr.by_room("t1", days=30)
    assert out == {"rooms": rows, "period_days": 30}
    match = unified.aggregate_pipelines[0][0]["$match"]
    assert match["nps_eligible"] is True
    assert match["room_number"] == {"$nin": [None, ""]}


# ── Dual-write yardımcıları ─────────────────────────────────────

class _UpsertColl:
    """update_one/delete_one kaydeden sahte kanonik koleksiyon."""

    def __init__(self, raise_on=None):
        self.upserts = []
        self.deletes = []
        self._raise_on = raise_on

    async def update_one(self, flt, update, upsert=False, *a, **k):
        if self._raise_on == "update":
            raise RuntimeError("boom")
        self.upserts.append((flt, update, upsert))
        return SimpleNamespace(upserted_id=flt["dedup_key"])

    async def delete_one(self, flt, *a, **k):
        if self._raise_on == "delete":
            raise RuntimeError("boom")
        self.deletes.append(flt)
        return SimpleNamespace(deleted_count=1)


@pytest.mark.asyncio
async def test_upsert_canonical_writes_with_dedup_key(monkeypatch):
    coll = _UpsertColl()
    monkeypatch.setattr(fr, "db", _db(feedback_entries=coll))
    survey = {"id": "n1", "tenant_id": "t1", "nps_score": 9, "category": "promoter",
              "responded_at": "x"}
    ok = await fr.upsert_canonical(fr.SOURCE_NPS_SURVEY, survey)
    assert ok is True
    flt, update, upsert = coll.upserts[0]
    assert flt["dedup_key"] == "t1|nps_survey|n1"
    assert upsert is True
    doc = update["$setOnInsert"]
    assert doc["source"] == fr.SOURCE_NPS_SURVEY
    assert doc["nps_eligible"] is True
    assert doc["written_by"] == "dualwrite"


@pytest.mark.asyncio
async def test_upsert_canonical_skips_without_stable_key(monkeypatch):
    coll = _UpsertColl()
    monkeypatch.setattr(fr, "db", _db(feedback_entries=coll))
    # id yok → kararlı dedup anahtarı yok → atlanır (çift sayım riski).
    ok = await fr.upsert_canonical(fr.SOURCE_NPS_SURVEY, {"tenant_id": "t1", "nps_score": 5})
    assert ok is False
    assert coll.upserts == []


@pytest.mark.asyncio
async def test_dualwrite_canonical_never_raises(monkeypatch):
    coll = _UpsertColl(raise_on="update")
    monkeypatch.setattr(fr, "db", _db(feedback_entries=coll))
    # Kanonik yazım patlasa bile legacy yolu KIRMAMALI → False döner, exception yok.
    ok = await fr.dualwrite_canonical(fr.SOURCE_NPS_SURVEY,
                                      {"id": "n1", "tenant_id": "t1", "responded_at": "x"})
    assert ok is False


@pytest.mark.asyncio
async def test_dualdelete_canonical_by_key(monkeypatch):
    coll = _UpsertColl()
    monkeypatch.setattr(fr, "db", _db(feedback_entries=coll))
    n = await fr.dualdelete_canonical("t1", fr.SOURCE_NPS_SURVEY, "n1")
    assert n == 1
    assert coll.deletes[0]["dedup_key"] == "t1|nps_survey|n1"


@pytest.mark.asyncio
async def test_dualdelete_canonical_never_raises(monkeypatch):
    coll = _UpsertColl(raise_on="delete")
    monkeypatch.setattr(fr, "db", _db(feedback_entries=coll))
    n = await fr.dualdelete_canonical("t1", fr.SOURCE_NPS_SURVEY, "n1")
    assert n == 0


# ── Parity doğrulaması ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_parity_match(monkeypatch):
    cats = [{"category": "promoter"}] * 3 + [{"category": "detractor"}]
    legacy = _FindColl(find_docs=list(cats))
    unified = _FindColl(find_docs=list(cats))
    monkeypatch.setattr(fr, "db", _db(nps_surveys=legacy, feedback_entries=unified))
    res = await fr.verify_parity("t1", days=30)
    assert res["match"] is True
    assert res["diffs"] == []
    assert res["legacy"] == res["unified"]
    # Kanonik tarafta nps_eligible filtresi uygulanır.
    assert unified.find_queries[0]["nps_eligible"] is True


@pytest.mark.asyncio
async def test_verify_parity_mismatch(monkeypatch):
    legacy = _FindColl(find_docs=[{"category": "promoter"}] * 4)
    unified = _FindColl(find_docs=[{"category": "promoter"}] * 3)  # eksik kayıt
    monkeypatch.setattr(fr, "db", _db(nps_surveys=legacy, feedback_entries=unified))
    res = await fr.verify_parity("t1", days=30)
    assert res["match"] is False
    assert "total_responses" in res["diffs"]
