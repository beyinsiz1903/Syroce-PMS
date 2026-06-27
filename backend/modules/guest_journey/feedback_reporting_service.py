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

from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

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


# ── Raporlama (legacy /nps/* uçlarının ince adaptör hedefi) ──────
# Bu fonksiyonlar legacy uçlarla BİREBİR aynı yanıt biçimini üretir ve YALNIZ
# NPS-uygun kaynaktan (nps_surveys) okur → paneldeki/mobildeki sayı değişmez,
# çift sayım olmaz.

async def compute_nps_score(tenant_id: str, days: int = 30) -> dict[str, Any]:
    """NPS skoru — legacy ``GET /nps/score`` ile birebir aynı çıktı."""
    days = bounded_days(days)
    start = _start_iso(days)

    surveys = await db.nps_surveys.find(
        {"tenant_id": tenant_id, "responded_at": {"$gte": start}},
        {"_id": 0, "category": 1},
    ).to_list(5000)

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

    cursor = (
        db.nps_surveys.find(query, {"_id": 0})
        .sort("responded_at", -1)
        .limit(min(limit, 200))
    )
    items = await cursor.to_list(min(limit, 200))
    return {"items": items, "count": len(items)}


async def by_room(tenant_id: str, days: int = 30) -> dict[str, Any]:
    """Oda bazlı ortalama puan — legacy ``GET /nps/by-room`` ile birebir aynı."""
    days = bounded_days(days)
    start = _start_iso(days)

    pipeline = [
        {"$match": {
            "tenant_id": tenant_id,
            "responded_at": {"$gte": start},
            "room_number": {"$nin": [None, ""]},
        }},
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
    rows = await db.nps_surveys.aggregate(pipeline).to_list(200)
    return {"rooms": rows, "period_days": days}
