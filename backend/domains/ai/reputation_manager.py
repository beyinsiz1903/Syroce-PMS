"""
Reputation Management System
Review aggregation, sentiment analysis, auto-response
"""

from datetime import UTC, datetime, timedelta


class ReputationManager:
    """Online reputation yönetimi"""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _rating_5(review: dict) -> float | None:
        value = review.get("rating_5", review.get("rating"))
        if not isinstance(value, (int, float)):
            return None
        scale = review.get("rating_scale") or (10 if value > 5 else 5)
        return round(max(0.0, min(5.0, float(value) * 5 / float(scale))), 2)

    async def aggregate_reviews(self, tenant_id: str) -> dict:
        """Platform review ozeti — YALNIZCA gercek db.external_reviews kayitlari.
        Sabit TripAdvisor/Google/Booking/Expedia uydurma verisi kaldirildi; kayit yoksa fail-closed."""
        reviews = await self.db.external_reviews.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "platform": 1, "rating": 1, "rating_5": 1, "rating_scale": 1, "review_date": 1, "received_at": 1, "response_status": 1},
        ).to_list(10000)

        if not reviews:
            return {
                "data_available": False,
                "message": "Dis platform (TripAdvisor/Google/Booking vb.) review verisi yok; entegrasyon yapilandirilmamis veya kayit bulunmuyor.",
                "platforms": {},
                "overall_rating": None,
                "total_reviews": 0,
                "last_updated": datetime.now(UTC).isoformat(),
            }

        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        acc: dict = {}
        for r in reviews:
            rt = self._rating_5(r)
            if rt is None:
                continue
            p = r.get("platform") or "unknown"
            st = acc.setdefault(p, {"rating_sum": 0.0, "total_reviews": 0, "recent_reviews": 0})
            st["rating_sum"] += rt
            st["total_reviews"] += 1
            rd = r.get("review_date") or r.get("received_at") or ""
            if isinstance(rd, str) and rd >= cutoff:
                st["recent_reviews"] += 1

        platforms = {}
        total_reviews = 0
        norm_weighted = 0.0
        norm_weight = 0
        for p, st in acc.items():
            n = st["total_reviews"]
            if n == 0:
                continue
            avg = st["rating_sum"] / n
            platforms[p] = {"rating": round(avg, 2), "total_reviews": n, "recent_reviews": st["recent_reviews"]}
            norm_weighted += avg * n
            norm_weight += n
            total_reviews += n

        out = {
            "data_available": total_reviews > 0,
            "platforms": platforms,
            "overall_rating": round(norm_weighted / norm_weight, 2) if norm_weight else None,
            "total_reviews": total_reviews,
            "last_updated": datetime.now(UTC).isoformat(),
            "responded_reviews": sum(1 for review in reviews if review.get("response_status") == "responded"),
        }
        if total_reviews == 0:
            out["message"] = "Dis platform review kaydi var ancak gecerli sayisal puan bulunmuyor."
        return out

    async def analyze_sentiment(self, review_text: str) -> dict:
        """Review sentiment analizi"""
        # Basit keyword-based (gerçekte NLP/ML kullanılır)
        positive_words = ["harika", "mükemmel", "temiz", "güzel", "excellent", "amazing", "great"]
        negative_words = ["kötü", "berbat", "kirli", "bad", "terrible", "poor", "awful"]

        text_lower = review_text.lower()

        positive_count = sum([1 for word in positive_words if word in text_lower])
        negative_count = sum([1 for word in negative_words if word in text_lower])

        # Skor/güven gerçek keyword sinyalinden türetilir (sabit 0.7/-0.6/0.75 kaldırıldı)
        total_signal = positive_count + negative_count
        if positive_count > negative_count:
            sentiment = "positive"
            score = round(positive_count / total_signal, 2) if total_signal else 0.0
        elif negative_count > positive_count:
            sentiment = "negative"
            score = round(-negative_count / total_signal, 2) if total_signal else 0.0
        else:
            sentiment = "neutral"
            score = 0.0

        # güven: eşleşen toplam sinyal güçlendikçe artar, sinyal yoksa düşük
        confidence = round(min(0.5 + 0.1 * total_signal, 0.95), 2) if total_signal else 0.0

        return {"sentiment": sentiment, "score": score, "confidence": confidence}

    async def suggest_response(self, review_text: str, rating: float) -> str:
        """AI-powered yanıt önerisi"""
        sentiment = await self.analyze_sentiment(review_text)

        if sentiment["sentiment"] == "positive":
            return """Değerli misafirimiz,

Güzel sözleriniz için çok teşekkür ederiz! Sizi ağırlamaktan büyük mutluluk duyduk.

Tekrar görüşmek üzere,
Syroce Ekibi"""
        else:
            return """Değerli misafirimiz,

Geri bildiriminiz için teşekkür ederiz. Yaşadığınız olumsuz deneyim için özür dileriz.

Durumu detaylı inceleyip, gerekli aksiyonları alacağız. Sizi memnun etmek için tekrar şans vermemizi isteriz.

Saygılarımızla,
Syroce Yönetim Ekibi"""

    async def detect_negative_reviews(self, tenant_id: str) -> list[dict]:
        """Son 24 saatteki negatif review'ları bul"""
        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()

        reviews = await self.db.external_reviews.find(
            {
                "tenant_id": tenant_id,
                "$or": [{"review_date": {"$gte": yesterday}}, {"received_at": {"$gte": yesterday}}],
            },
            {"_id": 0},
        ).to_list(500)
        return [review for review in reviews if (self._rating_5(review) or 0) <= 3]

    async def get_reputation_trends(self, tenant_id: str, days: int = 30) -> dict:
        """Reputation trend analizi"""
        start_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

        reviews = await self.db.external_reviews.find(
            {"tenant_id": tenant_id, "$or": [{"review_date": {"$gte": start_date}}, {"received_at": {"$gte": start_date}}]},
            {"_id": 0, "rating": 1, "rating_5": 1, "rating_scale": 1, "review_date": 1, "received_at": 1},
        ).to_list(1000)

        # Calculate trend
        if not reviews:
            return {"trend": "stable", "avg_rating": 0, "total_reviews": 0}

        reviews = sorted(reviews, key=lambda row: row.get("review_date") or row.get("received_at") or "")
        ratings = [value for value in (self._rating_5(review) for review in reviews) if value is not None]
        if not ratings:
            return {"trend": "stable", "avg_rating": 0, "total_reviews": 0}
        avg_rating = sum(ratings) / len(ratings)

        # Split into first half and second half
        mid = len(ratings) // 2
        first_half_avg = sum(ratings[:mid]) / mid if mid > 0 else ratings[0]
        second_half_avg = sum(ratings[mid:]) / (len(ratings) - mid) if len(ratings) > mid else ratings[-1]

        trend = "improving" if second_half_avg > first_half_avg else "declining" if second_half_avg < first_half_avg else "stable"

        return {"trend": trend, "avg_rating": round(avg_rating, 2), "total_reviews": len(ratings), "first_period_avg": round(first_half_avg, 2), "second_period_avg": round(second_half_avg, 2)}


# Global instance
reputation_manager = None


def get_reputation_manager(db):
    global reputation_manager
    if reputation_manager is None:
        reputation_manager = ReputationManager(db)
    return reputation_manager
