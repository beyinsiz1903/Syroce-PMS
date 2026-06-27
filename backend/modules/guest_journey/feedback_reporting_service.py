"""
Birleşik geri bildirim raporlama modeli (NPS Raporlama Birleştirme).

Misafir geri bildirimi üç koleksiyona dağılmış durumda:
- ``nps_surveys``      : personel-girişli NPS (0-10 skala, promoter/passive/detractor)
- ``survey_responses`` : iç/halka açık anket yanıtları (``overall_rating`` ortalaması)
- ``guest_reviews``    : halka açık davet yorumları (1-5 yıldız)

Bu modül üçünü TEK kanonik şemaya normalize eder ve kaynak (``source``)
ayrımını korur. Kanonik model, raporlamanın tek doğruluk kaynağıdır; legacy
``/nps/*`` uçları artık bu servisin ince adaptörleridir (sözleşme/yanıt biçimi
DEĞİŞMEZ).

KRİTİK geriye uyumluluk kuralı (operatör kararı):
    Paneldeki/mobildeki NPS sayısı DEĞİŞMEZ. NPS skoru, son yorumlar ve oda
    bazlı rapor YALNIZCA NPS-uygun (0-10) kaynaktan (``nps_survey``)
    hesaplanır. 1-5 yıldız yorumlar ve anket yanıtları NPS matematiğine
    KARIŞMAZ — bu hem skala bozulmasını hem de çift sayımı engeller. Diğer
    kaynaklar kanonik modelde (ör. ``feedback_entries`` materyalizasyonu)
    temsil edilir ama NPS toplamına dahil edilmez.

Bu dosya legacy davranışla birebir aynı sayıları üretir; tek değişiklik
hesaplamanın tek serviste toplanması ve kaynak ayrımının açıkça
işaretlenmesidir.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)

# ── Kaynak (source) etiketleri ──────────────────────────────────
SOURCE_NPS_SURVEY = "nps_survey"
SOURCE_SURVEY_RESPONSE = "survey_response"
SOURCE_GUEST_REVIEW = "guest_review"

ALL_SOURCES = (SOURCE_NPS_SURVEY, SOURCE_SURVEY_RESPONSE, SOURCE_GUEST_REVIEW)

# Kaynak → fiziksel koleksiyon adı (migration ve okuma için tek doğruluk kaynağı).
SOURCE_COLLECTIONS: dict[str, str] = {
    SOURCE_NPS_SURVEY: "nps_surveys",
    SOURCE_SURVEY_RESPONSE: "survey_responses",
    SOURCE_GUEST_REVIEW: "guest_reviews",
}

# Yalnız bu kaynak(lar) NPS (0-10) matematiğine girer. Operatör kararı gereği
# 1-5 yıldız yorumlar ve anketler NPS skorunu DEĞİŞTİRMEZ.
NPS_ELIGIBLE_SOURCES = (SOURCE_NPS_SURVEY,)

MAX_DAYS = 730

# Kanonik (birleşik) koleksiyon — tek doğruluk kaynağının fiziksel hedefi.
UNIFIED_COLLECTION = "feedback_entries"

# ── Fiziksel cutover feature-flag'i (fail-closed) ───────────────
# Açıkça ``true`` verilmedikçe canlı ``/nps/*`` uçları AUTHORITATIVE
# ``nps_surveys``'ten okur (sıfır-değişim, maksimum uyumluluk). Flag ``true``
# olduğunda okuma yolu kanonik ``feedback_entries``'e geçer (``nps_eligible``
# filtresiyle) — çıktı legacy ile birebir kalır.
UNIFIED_READ_ENV = "FEEDBACK_UNIFIED_READ_ENABLED"


def unified_read_enabled() -> bool:
    """Okuma yolu kanonik modele geçmiş mi? Fail-closed: default ``false``.

    Cutover yalnız operatör backfill (``migrate_feedback_unified --apply``)
    sonrası ve parity yeşilken açılmalıdır. Açık değilse legacy davranış
    (``nps_surveys``'ten okuma) korunur."""
    return os.environ.get(UNIFIED_READ_ENV, "false").strip().lower() == "true"


def dedup_key(tenant_id: str, source: str, source_id: str | None) -> str:
    """Kanonik idempotency anahtarı (migration ile birebir aynı format).

    ``feedback_entries`` üzerinde unique olan bu anahtar, dual-write ile
    backfill migration'ın aynı kaydı çift yazmasını engeller."""
    return f"{tenant_id}|{source}|{source_id}"


# ── Ortak yardımcılar (legacy ile birebir kural) ────────────────

def nps_category(score: int) -> str:
    """0-10 NPS skorunu kategoriye çevir (legacy ``_nps_category`` ile aynı)."""
    return "detractor" if score <= 6 else "passive" if score <= 8 else "promoter"


def bounded_days(days: int) -> int:
    """Anormal aralıkları engelle (1..730 gün) — legacy ``_bounded_days``."""
    if days < 1:
        return 1
    if days > MAX_DAYS:
        return MAX_DAYS
    return days


def star_to_nps(rating: float | int | None) -> int | None:
    """1-5 yıldızı 0-10 skalaya lineer çevir (1->0 ... 5->10).

    YALNIZCA kanonik materyalizasyon (bilgi amaçlı) içindir; NPS skoruna
    KARIŞMAZ (operatör kararı). NPS toplamı sadece ``nps_survey`` kaynağından
    gelir.
    """
    if rating is None:
        return None
    scaled = round((float(rating) - 1) / 4 * 10)
    return max(0, min(10, scaled))


def _start_iso(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


# ── Normalizerlar: her kaynak → kanonik kayıt ───────────────────
# Kanonik kayıt downstream/analitik için ``feedback_entries`` koleksiyonuna
# yazılır. ``nps_eligible`` bayrağı NPS toplamına girip girmeyeceğini belirler.

def normalize_nps_survey(doc: dict[str, Any]) -> dict[str, Any]:
    raw = doc.get("nps_score")
    score = int(raw) if raw is not None else 0
    return {
        "tenant_id": doc.get("tenant_id"),
        "source": SOURCE_NPS_SURVEY,
        "source_id": doc.get("id"),
        "nps_score": score,
        "star_rating": None,
        "overall_rating": None,
        "category": doc.get("category") or nps_category(score),
        "nps_eligible": True,
        "room_number": doc.get("room_number"),
        "guest_name": doc.get("guest_name"),
        "guest_id": doc.get("guest_id"),
        "booking_id": doc.get("booking_id"),
        "comment": doc.get("feedback"),
        "channel": doc.get("source"),  # manual | email | qr | api
        "recorded_by": doc.get("recorded_by"),
        "recorded_by_id": doc.get("recorded_by_id"),
        "responded_at": doc.get("responded_at"),
    }


def normalize_guest_review(doc: dict[str, Any]) -> dict[str, Any]:
    rating = doc.get("rating")
    if rating is None:
        rating = doc.get("overall_rating")
    star = int(rating) if rating is not None else None
    return {
        "tenant_id": doc.get("tenant_id"),
        "source": SOURCE_GUEST_REVIEW,
        "source_id": doc.get("id"),
        "nps_score": star_to_nps(star),
        "star_rating": star,
        "overall_rating": None,
        "category": None,        # NPS kategorisi YOK → NPS matematiğine girmez
        "nps_eligible": False,
        "room_number": doc.get("room_number"),
        "guest_name": doc.get("guest_name"),
        "guest_id": doc.get("guest_id"),
        "booking_id": doc.get("booking_id"),
        "comment": doc.get("comment"),
        "channel": doc.get("source"),  # direct_invite
        "recorded_by": None,
        "responded_at": doc.get("created_at") or doc.get("submitted_at"),
    }


def normalize_survey_response(doc: dict[str, Any]) -> dict[str, Any]:
    overall = doc.get("overall_rating")
    return {
        "tenant_id": doc.get("tenant_id"),
        "source": SOURCE_SURVEY_RESPONSE,
        "source_id": doc.get("id"),
        "nps_score": None,        # anket ölçeği belirsiz → NPS'e çevrilmez
        "star_rating": None,
        "overall_rating": overall,
        "category": None,
        "nps_eligible": False,
        "room_number": None,
        "guest_name": doc.get("guest_name"),
        "guest_id": None,
        "booking_id": doc.get("booking_id"),
        "comment": None,
        "channel": doc.get("survey_name"),
        "recorded_by": None,
        "responded_at": doc.get("submitted_at"),
    }


NORMALIZERS = {
    SOURCE_NPS_SURVEY: normalize_nps_survey,
    SOURCE_SURVEY_RESPONSE: normalize_survey_response,
    SOURCE_GUEST_REVIEW: normalize_guest_review,
}


def normalize(source: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Bir kaynak dokümanını kanonik kayda çevir."""
    fn = NORMALIZERS.get(source)
    if fn is None:
        raise ValueError(f"Bilinmeyen geri bildirim kaynağı: {source!r}")
    return fn(doc)


# ── Kanonik → legacy biçim eşlemesi ─────────────────────────────
# Birleşik okuma açıkken ``recent_feedback`` kanonik kaydı legacy
# ``nps_surveys`` doküman biçimine geri çevirir (çıktı birebir kalsın).

def _canonical_to_legacy_nps(c: dict[str, Any]) -> dict[str, Any]:
    """Kanonik ``feedback_entries`` kaydını legacy ``nps_surveys`` biçimine çevir.

    POST ``/nps/survey``'in yazdığı alan kümesiyle birebir aynı doküman üretir;
    böylece okuma kaynağı kanonik modele taşınsa da yanıt biçimi DEĞİŞMEZ."""
    return {
        "id": c.get("source_id"),
        "tenant_id": c.get("tenant_id"),
        "guest_id": c.get("guest_id"),
        "booking_id": c.get("booking_id"),
        "room_number": c.get("room_number"),
        "guest_name": c.get("guest_name"),
        "nps_score": c.get("nps_score"),
        "category": c.get("category"),
        "feedback": c.get("comment"),
        "source": c.get("channel"),
        "recorded_by": c.get("recorded_by"),
        "recorded_by_id": c.get("recorded_by_id"),
        "responded_at": c.get("responded_at"),
    }


def _score_from_categories(surveys: list[dict[str, Any]], days: int) -> dict[str, Any]:
    """Kategori listesinden NPS skoru — legacy formülüyle birebir."""
    if not surveys:
        return {
            "nps_score": 0,
            "total_responses": 0,
            "promoters": 0,
            "passives": 0,
            "detractors": 0,
            "period_days": days,
        }

    promoters = len([s for s in surveys if s.get("category") == "promoter"])
    detractors = len([s for s in surveys if s.get("category") == "detractor"])
    passives = len([s for s in surveys if s.get("category") == "passive"])
    total = len(surveys)

    nps = ((promoters - detractors) / total * 100) if total > 0 else 0

    return {
        "nps_score": round(nps, 1),
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "total_responses": total,
        "period_days": days,
    }


# ── Raporlama (legacy /nps/* uçlarının ince adaptör hedefi) ──────
# Bu fonksiyonlar legacy uçlarla BİREBİR aynı yanıt biçimini üretir ve YALNIZ
# NPS-uygun kaynaktan okur → paneldeki/mobildeki sayı değişmez, çift sayım
# olmaz. Okuma kaynağı feature-flag'e bağlıdır: flag KAPALI iken authoritative
# ``nps_surveys``; AÇIK iken kanonik ``feedback_entries`` (nps_eligible).

async def compute_nps_score(tenant_id: str, days: int = 30) -> dict[str, Any]:
    """NPS skoru — legacy ``GET /nps/score`` ile birebir aynı çıktı."""
    days = bounded_days(days)
    start = _start_iso(days)

    if unified_read_enabled():
        query = {
            "tenant_id": tenant_id,
            "nps_eligible": True,
            "responded_at": {"$gte": start},
        }
        surveys = await db.feedback_entries.find(
            query, {"_id": 0, "category": 1}
        ).to_list(5000)
    else:
        query = {"tenant_id": tenant_id, "responded_at": {"$gte": start}}
        surveys = await db.nps_surveys.find(
            query, {"_id": 0, "category": 1}
        ).to_list(5000)

    return _score_from_categories(surveys, days)


async def recent_feedback(
    tenant_id: str,
    days: int = 30,
    limit: int = 50,
    category: str | None = None,
    room_number: str | None = None,
) -> dict[str, Any]:
    """Son misafir yorumları — legacy ``GET /nps/recent`` ile birebir aynı."""
    days = bounded_days(days)
    limit = max(1, min(200, limit))
    start = _start_iso(days)

    query: dict[str, Any] = {
        "tenant_id": tenant_id,
        "responded_at": {"$gte": start},
    }
    if category in ("promoter", "passive", "detractor"):
        query["category"] = category
    if room_number:
        query["room_number"] = room_number

    if unified_read_enabled():
        query["nps_eligible"] = True
        cursor = (
            db.feedback_entries.find(query, {"_id": 0})
            .sort("responded_at", -1)
            .limit(min(limit, 200))
        )
        rows = await cursor.to_list(min(limit, 200))
        # Kanonik kaydı legacy biçime çevir → yanıt birebir kalır.
        items = [_canonical_to_legacy_nps(r) for r in rows]
    else:
        cursor = (
            db.nps_surveys.find(query, {"_id": 0})
            .sort("responded_at", -1)
            .limit(min(limit, 200))
        )
        items = await cursor.to_list(min(limit, 200))

    return {"items": items, "count": len(items)}


def _by_room_pipeline(tenant_id: str, start: str, eligible: bool) -> list[dict[str, Any]]:
    match: dict[str, Any] = {
        "tenant_id": tenant_id,
        "responded_at": {"$gte": start},
        "room_number": {"$nin": [None, ""]},
    }
    if eligible:
        match["nps_eligible"] = True
    return [
        {"$match": match},
        {"$group": {
            "_id": "$room_number",
            "avg_score": {"$avg": "$nps_score"},
            "response_count": {"$sum": 1},
            "promoters": {"$sum": {"$cond": [{"$eq": ["$category", "promoter"]}, 1, 0]}},
            "passives": {"$sum": {"$cond": [{"$eq": ["$category", "passive"]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$eq": ["$category", "detractor"]}, 1, 0]}},
            "last_responded_at": {"$max": "$responded_at"},
        }},
        {"$project": {
            "_id": 0,
            "room_number": "$_id",
            "avg_score": {"$round": ["$avg_score", 2]},
            "response_count": 1,
            "promoters": 1,
            "passives": 1,
            "detractors": 1,
            "last_responded_at": 1,
        }},
        {"$sort": {"avg_score": 1, "response_count": -1}},
        {"$limit": 200},
    ]


async def by_room(tenant_id: str, days: int = 30) -> dict[str, Any]:
    """Oda bazlı ortalama puan — legacy ``GET /nps/by-room`` ile birebir aynı."""
    days = bounded_days(days)
    start = _start_iso(days)

    if unified_read_enabled():
        pipeline = _by_room_pipeline(tenant_id, start, eligible=True)
        rows = await db.feedback_entries.aggregate(pipeline).to_list(200)
    else:
        pipeline = _by_room_pipeline(tenant_id, start, eligible=False)
        rows = await db.nps_surveys.aggregate(pipeline).to_list(200)

    return {"rooms": rows, "period_days": days}


# ── Dual-write: kanonik modele canlı yazım (idempotent, en-iyi-çaba) ──
# Legacy yazım (nps_surveys / survey_responses / guest_reviews) AUTHORITATIVE
# kalır; kanonik kayıt aynı request içinde dedup_key upsert ile materyalize
# edilir. Kanonik yazım başarısız olursa legacy yazım GERİ ALINMAZ (en-iyi-çaba)
# — yalnız error loglanır; backfill migration her an kanonik modeli yeniden
# tutarlı hale getirebilir. dedup_key, backfill migration ile çakışmayı önler
# ($setOnInsert: var olan kaydın üstüne yazmaz).

async def upsert_canonical(source: str, doc: dict[str, Any]) -> bool:
    """Bir kaynak dokümanını kanonik koleksiyona idempotent upsert et.

    True → yazım denendi (kayıt vardı veya yeni eklendi). False → kararlı
    dedup anahtarı (tenant_id/source_id) yok, atlandı."""
    canonical = normalize(source, doc)
    tenant_id = canonical.get("tenant_id")
    source_id = canonical.get("source_id")
    if not tenant_id or not source_id:
        return False
    key = dedup_key(tenant_id, source, source_id)
    canonical["dedup_key"] = key
    canonical["written_by"] = "dualwrite"
    canonical["written_at"] = datetime.now(UTC).isoformat()
    await db.feedback_entries.update_one(
        {"dedup_key": key}, {"$setOnInsert": canonical}, upsert=True
    )
    return True


async def dualwrite_canonical(source: str, doc: dict[str, Any]) -> bool:
    """``upsert_canonical``'ın en-iyi-çaba sarmalayıcısı: hata YÜKSELTMEZ.

    Çağıran legacy yazım yolunu KIRMAMALI; kanonik yazım hatası yalnız
    loglanır (cutover sonrası parity drift'i görünür kılmak için error)."""
    try:
        return await upsert_canonical(source, doc)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "feedback dual-write başarısız (source=%s): %s",
            source, type(exc).__name__,
        )
        return False


async def dualdelete_canonical(
    tenant_id: str, source: str, source_id: str | None
) -> int:
    """Kanonik kaydı dedup_key ile sil (legacy DELETE ile eşlik, en-iyi-çaba)."""
    if not tenant_id or not source_id:
        return 0
    key = dedup_key(tenant_id, source, source_id)
    try:
        res = await db.feedback_entries.delete_one({"dedup_key": key})
        return res.deleted_count
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "feedback dual-delete başarısız (source=%s): %s",
            source, type(exc).__name__,
        )
        return 0


# ── Parity doğrulaması (legacy vs unified) ──────────────────────
# Cutover öncesi/sonrası güvence: aynı tenant+pencere için legacy
# (nps_surveys) ve kanonik (feedback_entries, nps_eligible) okuma yolları
# AYNI NPS skorunu üretmeli. Fark varsa flag AÇILMAMALI (fail-closed).

async def verify_parity(tenant_id: str, days: int = 30) -> dict[str, Any]:
    """Legacy ve kanonik NPS skorlarını karşılaştır (flag'den bağımsız okur).

    Dönüş: ``{tenant_id, period_days, match, legacy, unified, diffs}``.
    ``match=True`` → iki yol birebir aynı skoru üretir (cutover güvenli)."""
    days = bounded_days(days)
    start = _start_iso(days)

    legacy_cats = await db.nps_surveys.find(
        {"tenant_id": tenant_id, "responded_at": {"$gte": start}},
        {"_id": 0, "category": 1},
    ).to_list(5000)
    unified_cats = await db.feedback_entries.find(
        {"tenant_id": tenant_id, "nps_eligible": True, "responded_at": {"$gte": start}},
        {"_id": 0, "category": 1},
    ).to_list(5000)

    legacy = _score_from_categories(legacy_cats, days)
    unified = _score_from_categories(unified_cats, days)

    diffs = [k for k in legacy if legacy.get(k) != unified.get(k)]
    return {
        "tenant_id": tenant_id,
        "period_days": days,
        "match": not diffs,
        "legacy": legacy,
        "unified": unified,
        "diffs": diffs,
    }
