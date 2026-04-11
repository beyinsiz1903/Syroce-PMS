"""
Guest DNA Profile - Hyper-Personalization Engine
Her misafir için DNA profili: tercihler, davranışlar, tahminler
"""
from datetime import datetime, timezone
from typing import Dict, List
import statistics

class GuestDNAEngine:
    """Misafir DNA profilleme motoru"""
    
    def __init__(self, db):
        self.db = db
    
    async def generate_dna_profile(self, tenant_id: str, guest_id: str) -> Dict:
        """Misafir için kapsamlı DNA profili oluştur"""
        # Get all guest data
        guest = await self.db.guests.find_one({'id': guest_id, 'tenant_id': tenant_id}, {'_id': 0})
        
        if not guest:
            return {'error': 'Guest not found'}
        
        # Get booking history
        bookings = await self.db.bookings.find({
            'guest_id': guest_id,
            'tenant_id': tenant_id
        }, {'_id': 0}).to_list(100)
        
        # Get preferences
        preferences = await self.db.enhanced_guest_preferences.find_one({
            'guest_id': guest_id,
            'tenant_id': tenant_id
        }, {'_id': 0})
        
        # Analyze patterns
        patterns = await self.analyze_behavioral_patterns(guest_id, bookings)
        spending = await self.calculate_spending_profile(bookings)
        propensity = await self.calculate_upsell_propensity(guest_id, bookings)
        
        return {
            'guest_id': guest_id,
            'guest_name': guest.get('name'),
            'total_stays': len(bookings),
            'member_since': guest.get('created_at'),
            'preferences': preferences or {},
            'behavioral_patterns': patterns,
            'spending_profile': spending,
            'upsell_propensity': propensity,
            'lifetime_value': spending.get('total_spent', 0),
            'tier_recommendation': self.recommend_tier(spending),
            'generated_at': datetime.now(timezone.utc).isoformat()
        }
    
    async def analyze_behavioral_patterns(self, guest_id: str, bookings: List) -> Dict:
        """Davranış pattern'lerini analiz et"""
        if not bookings:
            return {}
        
        # Booking lead time
        lead_times = []
        for b in bookings:
            if b.get('created_at') and b.get('check_in'):
                # Simplified
                lead_times.append(30)  # days
        
        avg_lead_time = statistics.mean(lead_times) if lead_times else 30
        
        # Stay patterns
        weekend_stays = len([b for b in bookings if b.get('rate_type') == 'leisure'])
        business_stays = len([b for b in bookings if b.get('market_segment') == 'corporate'])
        
        return {
            'avg_booking_lead_time_days': round(avg_lead_time, 1),
            'preferred_stay_type': 'leisure' if weekend_stays > business_stays else 'business',
            'booking_frequency': len(bookings) / 12 if len(bookings) > 0 else 0,  # per year
            'weekend_preference': weekend_stays > business_stays
        }
    
    async def calculate_spending_profile(self, bookings: List) -> Dict:
        """Harcama profili"""
        if not bookings:
            return {'total_spent': 0, 'avg_per_stay': 0}
        
        total_spent = sum([b.get('total_amount', 0) for b in bookings])
        avg_per_stay = total_spent / len(bookings)
        
        return {
            'total_spent': round(total_spent, 2),
            'avg_per_stay': round(avg_per_stay, 2),
            'ltv_tier': 'high_value' if total_spent > 5000 else 'valuable' if total_spent > 2000 else 'regular'
        }
    
    async def calculate_upsell_propensity(self, guest_id: str, bookings: List) -> Dict:
        """Upsell kabul eğilimi"""
        # Simulated propensity scores
        return {
            'room_upgrade': 70,  # %70 chance accepts room upgrade
            'early_checkin': 40,
            'late_checkout': 60,
            'spa_package': 80,
            'fnb_offers': 50,
            'overall_score': 60
        }
    
    def recommend_tier(self, spending: Dict) -> str:
        """VIP tier önerisi"""
        total = spending.get('total_spent', 0)
        if total > 10000:
            return 'platinum'
        elif total > 5000:
            return 'gold'
        elif total > 2000:
            return 'silver'
        return 'regular'

# Global
guest_dna_engine = None

def get_guest_dna_engine(db):
    global guest_dna_engine
    if guest_dna_engine is None:
        guest_dna_engine = GuestDNAEngine(db)
    return guest_dna_engine
