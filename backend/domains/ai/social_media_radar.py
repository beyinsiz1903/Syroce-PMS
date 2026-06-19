"""
Social Media Command Center
Instagram, Twitter, Facebook mention takibi ve sentiment analizi.

NOT: Gerçek sosyal medya entegrasyonu (Instagram/Twitter/Facebook Graph API)
yapılandırılmadığı sürece bu modül FABRİKASYON yapmaz. Tüm okuma yüzeyleri
fail-closed döner (boş veri + data_available:false). Önceki sürümdeki rastgele
(simulated) mention/sentiment üretimi kaldırılmıştır.
"""


class SocialMediaRadar:
    """Social media monitoring ve analiz (gerçek kaynak yoksa fail-closed)."""

    def __init__(self, db):
        self.db = db

    async def scan_mentions(self, tenant_id: str, hours: int = 24) -> list[dict]:
        """Son N saatteki mention'lar.

        Gerçek sosyal medya API entegrasyonu yapılandırılmadığı için boş liste
        döner. Sahte/rastgele mention üretilmez.
        """
        return []

    async def get_sentiment_summary(self, tenant_id: str, days: int = 7) -> dict:
        """Sentiment özeti — gerçek mention akışı yoksa fail-closed."""
        return {
            'period_days': days,
            'data_available': False,
            'total_mentions': 0,
            'positive': 0,
            'neutral': 0,
            'negative': 0,
            'sentiment_score': 0,
            'trend': 'unknown',
            'message': 'Sosyal medya entegrasyonu yapılandırılmamış. Veri yok.',
        }

    async def detect_crisis(self, tenant_id: str) -> list[dict]:
        """Kriz tespiti — gerçek mention akışı yoksa fail-closed (boş)."""
        return []

    async def suggest_response(self, mention_text: str, sentiment: str) -> str:
        """Yanıt önerisi şablonu (sabit metin; veri değildir)."""
        if sentiment == 'positive':
            return "Thank you for your kind words! We're delighted you enjoyed your stay. We look forward to welcoming you back!"
        elif sentiment == 'negative':
            return "We sincerely apologize for your experience. We take all feedback seriously and would love the opportunity to make it right. Please DM us so we can address your concerns."
        else:
            return "Thank you for sharing your experience! We appreciate your feedback and hope to see you again soon."


# Global instance
social_radar = None


def get_social_radar(db):
    global social_radar
    if social_radar is None:
        social_radar = SocialMediaRadar(db)
    return social_radar
