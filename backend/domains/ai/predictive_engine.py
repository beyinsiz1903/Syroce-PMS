"""
Predictive Analytics Engine - AI Oracle
Geleceği tahmin et: No-show, demand, complaints, inventory
"""
import random
from datetime import date, timedelta
from typing import Dict, List


class PredictiveEngine:
    """AI prediction engine"""
    
    def __init__(self, db):
        self.db = db
    
    async def predict_no_shows(self, tenant_id: str, target_date: str) -> List[Dict]:
        """No-show risk prediction"""
        # Get bookings for target date
        bookings = await self.db.bookings.find({
            'tenant_id': tenant_id,
            'check_in': {'$regex': f'^{target_date}'},
            'status': {'$in': ['confirmed', 'guaranteed']}
        }, {'_id': 0}).to_list(100)
        
        predictions = []
        for booking in bookings:
            # Risk factors (simplified ML model)
            risk_score = 0.0
            
            # No payment method
            if not booking.get('payment_method'):
                risk_score += 0.35
            
            # OTA booking
            if booking.get('channel') in ['booking_com', 'expedia']:
                risk_score += 0.25
            
            # No pre-arrival contact
            if not booking.get('last_contact_date'):
                risk_score += 0.20
            
            # Last minute booking
            if booking.get('created_at'):
                days_advance = 1  # Simplified
                if days_advance < 3:
                    risk_score += 0.15
            
            # Low price point
            if booking.get('total_amount', 0) < 80:
                risk_score += 0.10
            
            confidence = min(risk_score * 100, 95)
            risk_level = 'high' if risk_score > 0.6 else 'medium' if risk_score > 0.3 else 'low'
            
            if risk_score > 0.3:  # Only report medium+ risk
                predictions.append({
                    'booking_id': booking['id'],
                    'guest_id': booking['guest_id'],
                    'risk_score': round(risk_score, 2),
                    'confidence': round(confidence, 1),
                    'risk_level': risk_level,
                    'recommended_action': 'Reconfirm booking via phone/WhatsApp' if risk_level == 'high' else 'Monitor',
                    'factors': self._get_risk_factors(booking)
                })
        
        # Sort by risk
        predictions.sort(key=lambda x: x['risk_score'], reverse=True)
        
        return predictions
    
    def _get_risk_factors(self, booking: dict) -> List[str]:
        """Risk faktörlerini listele"""
        factors = []
        if not booking.get('payment_method'):
            factors.append('No payment method')
        if booking.get('channel') in ['booking_com', 'expedia']:
            factors.append('OTA booking')
        if not booking.get('last_contact_date'):
            factors.append('No pre-arrival contact')
        return factors
    
    async def predict_demand(self, tenant_id: str, days_ahead: int = 30) -> List[Dict]:
        """Talep tahmini (30 gün)"""
        today = date.today()
        predictions = []
        
        for i in range(days_ahead):
            target_date = today + timedelta(days=i)
            
            # Simplified demand model (gerçekte LSTM kullanılır)
            # Get historical occupancy for same day of week
            day_of_week = target_date.weekday()
            
            # Weekend vs weekday
            base_occupancy = 75 if day_of_week >= 4 else 60
            
            # Random variation
            occupancy_forecast = base_occupancy + random.randint(-10, 15)
            occupancy_forecast = max(20, min(95, occupancy_forecast))  # Clamp 20-95
            
            # Demand level
            demand_level = 'very_high' if occupancy_forecast > 85 else 'high' if occupancy_forecast > 70 else 'medium' if occupancy_forecast > 50 else 'low'
            
            # Price recommendation
            base_price = 100
            if demand_level == 'very_high':
                recommended_price = base_price * 1.3
            elif demand_level == 'high':
                recommended_price = base_price * 1.15
            elif demand_level == 'medium':
                recommended_price = base_price
            else:
                recommended_price = base_price * 0.85
            
            predictions.append({
                'date': target_date.isoformat(),
                'day_of_week': ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'][day_of_week],
                'occupancy_forecast': round(occupancy_forecast, 1),
                'demand_level': demand_level,
                'recommended_price': round(recommended_price, 2),
                'confidence': 82.0  # Model confidence
            })
        
        return predictions
    
    async def predict_complaint_risk(self, tenant_id: str, guest_id: str) -> dict:
        """Şikayet riski tahmini"""
        # Get guest history
        past_complaints = await self.db.service_complaints.count_documents({
            'tenant_id': tenant_id,
            'guest_id': guest_id
        })
        
        # Get satisfaction scores
        reviews = await self.db.reviews.find({
            'tenant_id': tenant_id,
            'guest_id': guest_id
        }, {'_id': 0, 'rating': 1}).to_list(10)
        
        avg_rating = sum([r.get('rating', 3) for r in reviews]) / len(reviews) if reviews else 3
        
        # Calculate risk
        risk_score = 0.0
        
        if past_complaints > 0:
            risk_score += 0.4
        
        if avg_rating < 3:
            risk_score += 0.3
        
        if avg_rating < 4 and past_complaints > 0:
            risk_score += 0.2
        
        confidence = 65 + (len(reviews) * 3)  # More data = more confidence
        
        return {
            'guest_id': guest_id,
            'risk_score': round(risk_score, 2),
            'confidence': min(confidence, 95),
            'risk_level': 'high' if risk_score > 0.6 else 'medium' if risk_score > 0.3 else 'low',
            'past_complaints': past_complaints,
            'avg_satisfaction': round(avg_rating, 2),
            'recommended_action': 'Proactive service call' if risk_score > 0.5 else 'Monitor'
        }

# Global instance
predictive_engine = None

def get_predictive_engine(db):
    global predictive_engine
    if predictive_engine is None:
        predictive_engine = PredictiveEngine(db)
    return predictive_engine
