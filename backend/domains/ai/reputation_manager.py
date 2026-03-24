"""
Reputation Management System
Review aggregation, sentiment analysis, auto-response
"""
from datetime import datetime, timezone, timedelta
from typing import List

class ReputationManager:
    """Online reputation yönetimi"""
    
    def __init__(self, db):
        self.db = db
    
    async def aggregate_reviews(self, tenant_id: str) -> dict:
        """Tüm platformlardan review'ları topla"""
        # Gerçekte: TripAdvisor, Google, Booking.com API'leri
        
        # Simulated data
        platforms = {
            'tripadvisor': {'rating': 4.5, 'total_reviews': 1250, 'recent_reviews': 45},
            'google': {'rating': 4.3, 'total_reviews': 890, 'recent_reviews': 32},
            'booking_com': {'rating': 8.9, 'total_reviews': 2100, 'recent_reviews': 78},
            'expedia': {'rating': 4.4, 'total_reviews': 650, 'recent_reviews': 28}
        }
        
        # Calculate overall
        total_reviews = sum([p['total_reviews'] for p in platforms.values()])
        weighted_rating = sum([
            (p['rating'] if p['rating'] <= 5 else p['rating']/2) * p['total_reviews'] 
            for p in platforms.values()
        ]) / total_reviews
        
        return {
            'platforms': platforms,
            'overall_rating': round(weighted_rating, 2),
            'total_reviews': total_reviews,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
    
    async def analyze_sentiment(self, review_text: str) -> dict:
        """Review sentiment analizi"""
        # Basit keyword-based (gerçekte NLP/ML kullanılır)
        positive_words = ['harika', 'mükemmel', 'temiz', 'güzel', 'excellent', 'amazing', 'great']
        negative_words = ['kötü', 'berbat', 'kirli', 'bad', 'terrible', 'poor', 'awful']
        
        text_lower = review_text.lower()
        
        positive_count = sum([1 for word in positive_words if word in text_lower])
        negative_count = sum([1 for word in negative_words if word in text_lower])
        
        if positive_count > negative_count:
            sentiment = 'positive'
            score = 0.7
        elif negative_count > positive_count:
            sentiment = 'negative'
            score = -0.6
        else:
            sentiment = 'neutral'
            score = 0.0
        
        return {
            'sentiment': sentiment,
            'score': score,
            'confidence': 0.75
        }
    
    async def suggest_response(self, review_text: str, rating: float) -> str:
        """AI-powered yanıt önerisi"""
        sentiment = await self.analyze_sentiment(review_text)
        
        if sentiment['sentiment'] == 'positive':
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
    
    async def detect_negative_reviews(self, tenant_id: str) -> List[dict]:
        """Son 24 saatteki negatif review'ları bul"""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        reviews = await self.db.reviews.find({
            'tenant_id': tenant_id,
            'rating': {'$lte': 3},
            'created_at': {'$gte': yesterday}
        }, {'_id': 0}).to_list(100)
        
        return reviews
    
    async def get_reputation_trends(self, tenant_id: str, days: int = 30) -> dict:
        """Reputation trend analizi"""
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        reviews = await self.db.reviews.find({
            'tenant_id': tenant_id,
            'created_at': {'$gte': start_date}
        }, {'_id': 0, 'rating': 1, 'created_at': 1}).to_list(1000)
        
        # Calculate trend
        if not reviews:
            return {'trend': 'stable', 'avg_rating': 0, 'total_reviews': 0}
        
        avg_rating = sum([r.get('rating', 3) for r in reviews]) / len(reviews)
        
        # Split into first half and second half
        mid = len(reviews) // 2
        first_half_avg = sum([r.get('rating', 3) for r in reviews[:mid]]) / mid if mid > 0 else 3
        second_half_avg = sum([r.get('rating', 3) for r in reviews[mid:]]) / (len(reviews) - mid) if len(reviews) > mid else 3
        
        trend = 'improving' if second_half_avg > first_half_avg else 'declining' if second_half_avg < first_half_avg else 'stable'
        
        return {
            'trend': trend,
            'avg_rating': round(avg_rating, 2),
            'total_reviews': len(reviews),
            'first_period_avg': round(first_half_avg, 2),
            'second_period_avg': round(second_half_avg, 2)
        }

# Global instance
reputation_manager = None

def get_reputation_manager(db):
    global reputation_manager
    if reputation_manager is None:
        reputation_manager = ReputationManager(db)
    return reputation_manager
