"""
ML Data Generators for Hotel PMS
Generates synthetic training data for all ML models
"""

import random
from datetime import datetime, timedelta

import pandas as pd


class RMSDataGenerator:
    """
    Revenue Management System Data Generator
    Generates 2 years of pricing and occupancy data
    """
    
    @staticmethod
    def generate(days=730):
        """
        Generate RMS training data
        
        Features:
        - day_of_week (0-6)
        - month (1-12)
        - season (0=low, 1=mid, 2=high, 3=peak)
        - is_weekend (0/1)
        - is_holiday (0/1)
        - days_until_event (0-365)
        - competitor_avg_rate (50-300)
        - competitor_occupancy (0.3-1.0)
        - historical_occupancy_7d (0.3-1.0)
        - historical_occupancy_30d (0.3-1.0)
        - lead_time_bookings (0-100)
        - current_price (50-300)
        
        Targets:
        - occupancy_rate (0.3-1.0)
        - optimal_price (50-300)
        """
        
        start_date = datetime.now() - timedelta(days=days)
        data = []
        
        # Define seasons
        high_season_months = [6, 7, 8, 12]  # Summer + December
        mid_season_months = [4, 5, 9, 10]   # Spring + Fall
        
        # Define holidays
        holidays = [
            (1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29), (12, 25)
        ]
        
        # Define major events (randomly throughout year)
        events = [start_date + timedelta(days=random.randint(0, days)) for _ in range(20)]
        
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            
            day_of_week = current_date.weekday()
            month = current_date.month
            is_weekend = 1 if day_of_week >= 5 else 0
            is_holiday = 1 if (month, current_date.day) in holidays else 0
            
            # Determine season
            if month in high_season_months:
                season = 3  # Peak
                base_occupancy = 0.80
                base_price = 200
            elif month in mid_season_months:
                season = 2  # High
                base_occupancy = 0.65
                base_price = 150
            else:
                season = 1  # Low
                base_occupancy = 0.45
                base_price = 100
            
            # Days until next event
            days_until_event = min([abs((event - current_date).days) for event in events])
            
            # Competitor data (with some noise)
            competitor_avg_rate = base_price * random.uniform(0.9, 1.1)
            competitor_occupancy = base_occupancy * random.uniform(0.85, 1.15)
            competitor_occupancy = max(0.3, min(1.0, competitor_occupancy))
            
            # Historical occupancy simulation
            historical_occupancy_7d = base_occupancy * random.uniform(0.85, 1.1)
            historical_occupancy_30d = base_occupancy * random.uniform(0.9, 1.05)
            historical_occupancy_7d = max(0.3, min(1.0, historical_occupancy_7d))
            historical_occupancy_30d = max(0.3, min(1.0, historical_occupancy_30d))
            
            # Lead time bookings (advance reservations)
            lead_time_bookings = int(base_occupancy * 100 * random.uniform(0.8, 1.2))
            
            # Current price (what hotel is charging)
            current_price = base_price * random.uniform(0.95, 1.05)
            
            # Calculate target occupancy (with various factors)
            occupancy = base_occupancy
            
            # Weekend boost
            if is_weekend:
                occupancy *= 1.15
            
            # Holiday boost
            if is_holiday:
                occupancy *= 1.25
            
            # Event proximity boost
            if days_until_event < 7:
                occupancy *= 1.3
            elif days_until_event < 14:
                occupancy *= 1.15
            
            # Price sensitivity
            if current_price < competitor_avg_rate * 0.95:
                occupancy *= 1.10  # Lower price increases occupancy
            elif current_price > competitor_avg_rate * 1.05:
                occupancy *= 0.90  # Higher price decreases occupancy
            
            # Add noise
            occupancy *= random.uniform(0.92, 1.08)
            occupancy = max(0.3, min(1.0, occupancy))
            
            # Calculate optimal price (based on occupancy and demand)
            if occupancy > 0.85:
                optimal_price = base_price * 1.30  # High demand - increase price
            elif occupancy > 0.70:
                optimal_price = base_price * 1.15
            elif occupancy > 0.50:
                optimal_price = base_price * 1.0
            else:
                optimal_price = base_price * 0.85  # Low demand - discount
            
            # Add some noise to optimal price
            optimal_price *= random.uniform(0.95, 1.05)
            
            data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'day_of_week': day_of_week,
                'month': month,
                'season': season,
                'is_weekend': is_weekend,
                'is_holiday': is_holiday,
                'days_until_event': days_until_event,
                'competitor_avg_rate': round(competitor_avg_rate, 2),
                'competitor_occupancy': round(competitor_occupancy, 3),
                'historical_occupancy_7d': round(historical_occupancy_7d, 3),
                'historical_occupancy_30d': round(historical_occupancy_30d, 3),
                'lead_time_bookings': lead_time_bookings,
                'current_price': round(current_price, 2),
                'occupancy_rate': round(occupancy, 3),
                'optimal_price': round(optimal_price, 2)
            })
        
        return pd.DataFrame(data)


class PersonaDataGenerator:
    """
    Guest Persona Data Generator
    Generates 300-500 guest profile data
    """
    
    @staticmethod
    def generate(num_guests=400):
        """
        Generate guest persona training data
        
        Features:
        - total_stays (1-20)
        - avg_spend (50-500)
        - total_spent (100-10000)
        - avg_lead_time (0-90 days)
        - ota_bookings (0-20)
        - direct_bookings (0-20)
        - upsells_accepted (0-10)
        - negative_reviews (0-5)
        - positive_reviews (0-20)
        - days_since_last_visit (0-730)
        - booking_frequency (bookings per year)
        
        Target:
        - persona_type: 0=price_sensitive, 1=experience_seeker, 2=complainer, 
                       3=upsell_candidate, 4=high_ltv, 5=ota_to_direct
        """
        
        data = []
        
        persona_types = [
            'price_sensitive',
            'experience_seeker', 
            'complainer',
            'upsell_candidate',
            'high_ltv',
            'ota_to_direct'
        ]
        
        for i in range(num_guests):
            # Randomly assign a primary persona
            primary_persona = random.choice(persona_types)
            
            if primary_persona == 'price_sensitive':
                total_stays = random.randint(1, 3)
                avg_spend = random.uniform(50, 100)
                avg_lead_time = random.uniform(30, 90)
                ota_bookings = total_stays
                direct_bookings = 0
                upsells_accepted = 0
                negative_reviews = random.randint(0, 1)
                positive_reviews = random.randint(0, 2)
                days_since_last_visit = random.randint(60, 365)
                
            elif primary_persona == 'experience_seeker':
                total_stays = random.randint(2, 8)
                avg_spend = random.uniform(200, 400)
                avg_lead_time = random.uniform(14, 60)
                ota_bookings = random.randint(1, 3)
                direct_bookings = total_stays - ota_bookings
                upsells_accepted = random.randint(4, 10)
                negative_reviews = random.randint(0, 1)
                positive_reviews = random.randint(3, 10)
                days_since_last_visit = random.randint(30, 180)
                
            elif primary_persona == 'complainer':
                total_stays = random.randint(1, 5)
                avg_spend = random.uniform(100, 250)
                avg_lead_time = random.uniform(7, 45)
                ota_bookings = random.randint(0, total_stays)
                direct_bookings = total_stays - ota_bookings
                upsells_accepted = random.randint(0, 2)
                negative_reviews = random.randint(2, 5)
                positive_reviews = random.randint(0, 2)
                days_since_last_visit = random.randint(90, 365)
                
            elif primary_persona == 'upsell_candidate':
                total_stays = random.randint(3, 10)
                avg_spend = random.uniform(250, 450)
                avg_lead_time = random.uniform(10, 45)
                ota_bookings = random.randint(1, 4)
                direct_bookings = random.randint(1, 6)
                upsells_accepted = random.randint(2, 8)
                negative_reviews = random.randint(0, 1)
                positive_reviews = random.randint(2, 8)
                days_since_last_visit = random.randint(20, 150)
                
            elif primary_persona == 'high_ltv':
                total_stays = random.randint(6, 20)
                avg_spend = random.uniform(300, 500)
                avg_lead_time = random.uniform(7, 60)
                ota_bookings = random.randint(0, 3)
                direct_bookings = total_stays - ota_bookings
                upsells_accepted = random.randint(5, 15)
                negative_reviews = random.randint(0, 2)
                positive_reviews = random.randint(5, 20)
                days_since_last_visit = random.randint(10, 90)
                
            else:  # ota_to_direct
                total_stays = random.randint(2, 6)
                avg_spend = random.uniform(120, 250)
                avg_lead_time = random.uniform(14, 60)
                ota_bookings = total_stays
                direct_bookings = 0
                upsells_accepted = random.randint(0, 3)
                negative_reviews = random.randint(0, 1)
                positive_reviews = random.randint(1, 5)
                days_since_last_visit = random.randint(45, 180)
            
            total_spent = avg_spend * total_stays
            booking_frequency = total_stays / max(1, days_since_last_visit / 365)
            
            data.append({
                'guest_id': f'G{i+1:04d}',
                'total_stays': total_stays,
                'avg_spend': round(avg_spend, 2),
                'total_spent': round(total_spent, 2),
                'avg_lead_time': round(avg_lead_time, 1),
                'ota_bookings': ota_bookings,
                'direct_bookings': direct_bookings,
                'upsells_accepted': upsells_accepted,
                'negative_reviews': negative_reviews,
                'positive_reviews': positive_reviews,
                'days_since_last_visit': days_since_last_visit,
                'booking_frequency': round(booking_frequency, 2),
                'persona_type': primary_persona
            })
        
        return pd.DataFrame(data)


class PredictiveMaintenanceDataGenerator:
    """
    Predictive Maintenance Data Generator
    Generates IoT sensor simulation data
    """
    
    @staticmethod
    def generate(num_samples=1000):
        """
        Generate predictive maintenance training data
        
        Features:
        - equipment_type: 0=hvac, 1=plumbing, 2=electrical, 3=elevator
        - temperature (15-35°C for HVAC)
        - vibration_level (0-100)
        - error_count_24h (0-20)
        - usage_hours (0-10000)
        - days_since_maintenance (0-365)
        - humidity (20-80%)
        - pressure (for plumbing, 20-100 PSI)
        - age_years (0-20)
        
        Targets:
        - failure_risk: 0=low, 1=medium, 2=high
        - days_until_failure (1-365)
        """
        
        data = []
        equipment_types = ['hvac', 'plumbing', 'electrical', 'elevator']
        
        for i in range(num_samples):
            equipment = random.choice(equipment_types)
            equipment_idx = equipment_types.index(equipment)
            
            # Base values
            age_years = random.uniform(0, 20)
            days_since_maintenance = random.randint(0, 365)
            usage_hours = random.randint(100, 10000)
            
            # Determine failure risk based on multiple factors
            risk_score = 0
            
            # Age factor
            if age_years > 15:
                risk_score += 3
            elif age_years > 10:
                risk_score += 2
            elif age_years > 5:
                risk_score += 1
            
            # Maintenance factor
            if days_since_maintenance > 180:
                risk_score += 3
            elif days_since_maintenance > 90:
                risk_score += 2
            elif days_since_maintenance > 60:
                risk_score += 1
            
            # Usage factor
            if usage_hours > 8000:
                risk_score += 2
            elif usage_hours > 5000:
                risk_score += 1
            
            # Equipment-specific features
            if equipment == 'hvac':
                # Normal: 18-24°C, problematic: outside this range
                if risk_score >= 5:
                    temperature = random.uniform(28, 35)  # Overheating
                    vibration_level = random.uniform(60, 100)
                    error_count_24h = random.randint(10, 20)
                elif risk_score >= 3:
                    temperature = random.uniform(25, 28)
                    vibration_level = random.uniform(40, 60)
                    error_count_24h = random.randint(5, 10)
                else:
                    temperature = random.uniform(18, 24)
                    vibration_level = random.uniform(0, 40)
                    error_count_24h = random.randint(0, 5)
                
                humidity = random.uniform(30, 70)
                pressure = 0  # Not applicable
                
            elif equipment == 'plumbing':
                temperature = random.uniform(15, 30)
                vibration_level = random.uniform(0, 30)
                
                if risk_score >= 5:
                    pressure = random.uniform(80, 100)  # High pressure
                    error_count_24h = random.randint(5, 15)
                    humidity = random.uniform(70, 90)  # High humidity = leak risk
                elif risk_score >= 3:
                    pressure = random.uniform(60, 80)
                    error_count_24h = random.randint(2, 5)
                    humidity = random.uniform(55, 70)
                else:
                    pressure = random.uniform(40, 60)
                    error_count_24h = random.randint(0, 2)
                    humidity = random.uniform(40, 55)
                    
            elif equipment == 'electrical':
                temperature = random.uniform(20, 40) if risk_score >= 5 else random.uniform(20, 30)
                vibration_level = random.uniform(0, 20)
                
                if risk_score >= 5:
                    error_count_24h = random.randint(10, 20)
                elif risk_score >= 3:
                    error_count_24h = random.randint(3, 10)
                else:
                    error_count_24h = random.randint(0, 3)
                
                humidity = random.uniform(30, 60)
                pressure = 0
                
            else:  # elevator
                temperature = random.uniform(20, 30)
                
                if risk_score >= 5:
                    vibration_level = random.uniform(70, 100)
                    error_count_24h = random.randint(8, 20)
                elif risk_score >= 3:
                    vibration_level = random.uniform(40, 70)
                    error_count_24h = random.randint(3, 8)
                else:
                    vibration_level = random.uniform(0, 40)
                    error_count_24h = random.randint(0, 3)
                
                humidity = random.uniform(30, 60)
                pressure = 0
            
            # Determine failure risk category
            if risk_score >= 6:
                failure_risk = 'high'
                days_until_failure = random.randint(1, 30)
            elif risk_score >= 3:
                failure_risk = 'medium'
                days_until_failure = random.randint(31, 90)
            else:
                failure_risk = 'low'
                days_until_failure = random.randint(91, 365)
            
            data.append({
                'equipment_id': f'EQ{i+1:04d}',
                'equipment_type': equipment,
                'equipment_type_idx': equipment_idx,
                'temperature': round(temperature, 1),
                'vibration_level': round(vibration_level, 1),
                'error_count_24h': error_count_24h,
                'usage_hours': usage_hours,
                'days_since_maintenance': days_since_maintenance,
                'humidity': round(humidity, 1),
                'pressure': round(pressure, 1),
                'age_years': round(age_years, 1),
                'failure_risk': failure_risk,
                'days_until_failure': days_until_failure
            })
        
        return pd.DataFrame(data)


class HKSchedulerDataGenerator:
    """
    Housekeeping Scheduler Data Generator
    Generates occupancy-based staffing data
    """
    
    @staticmethod
    def generate(num_days=365):
        """
        Generate HK scheduler training data
        
        Features:
        - total_rooms (50-200)
        - occupied_rooms (20-200)
        - checkout_rooms (0-50)
        - stayover_rooms (0-150)
        - vip_rooms (0-10)
        - day_of_week (0-6)
        - is_weekend (0/1)
        - season (0-3)
        - occupancy_rate (0.3-1.0)
        - avg_room_type_points (1-3: standard=1, deluxe=2, suite=3)
        
        Targets:
        - staff_needed (3-20)
        - estimated_hours (10-80)
        """
        
        data = []
        
        for i in range(num_days):
            current_date = datetime.now() - timedelta(days=num_days - i)
            
            day_of_week = current_date.weekday()
            month = current_date.month
            is_weekend = 1 if day_of_week >= 5 else 0
            
            # Season determination
            if month in [6, 7, 8, 12]:
                season = 3  # Peak
                base_occupancy = 0.85
            elif month in [4, 5, 9, 10]:
                season = 2  # High
                base_occupancy = 0.70
            else:
                season = 1  # Low
                base_occupancy = 0.50
            
            # Add weekend boost
            if is_weekend:
                base_occupancy *= 1.10
            
            # Add noise
            occupancy_rate = base_occupancy * random.uniform(0.9, 1.1)
            occupancy_rate = max(0.3, min(1.0, occupancy_rate))
            
            # Hotel capacity
            total_rooms = 100  # Fixed hotel size
            occupied_rooms = int(total_rooms * occupancy_rate)
            
            # Checkout patterns (higher on weekends and Mondays)
            if day_of_week == 0:  # Monday
                checkout_rate = 0.30
            elif is_weekend:
                checkout_rate = 0.25
            else:
                checkout_rate = 0.15
            
            checkout_rooms = int(occupied_rooms * checkout_rate)
            checkout_rooms = max(0, min(checkout_rooms, occupied_rooms))
            
            stayover_rooms = occupied_rooms - checkout_rooms
            
            # VIP rooms (2-8% of occupied)
            vip_rooms = int(occupied_rooms * random.uniform(0.02, 0.08))
            
            # Room type complexity (higher = more cleaning time)
            # Standard room: 1 point (25 min)
            # Deluxe room: 2 points (35 min) 
            # Suite: 3 points (50 min)
            avg_room_type_points = random.uniform(1.3, 1.8)  # Mix of room types
            
            # Calculate staff needed
            # Base formula: 
            # - Checkout rooms (full cleaning): 30 min each
            # - Stayover rooms (refresh): 15 min each
            # - VIP rooms: +10 min extra
            # - Room type multiplier
            
            checkout_minutes = checkout_rooms * 30 * avg_room_type_points
            stayover_minutes = stayover_rooms * 15 * avg_room_type_points
            vip_extra_minutes = vip_rooms * 10
            
            total_minutes = checkout_minutes + stayover_minutes + vip_extra_minutes
            estimated_hours = total_minutes / 60
            
            # Each staff works 6 hours effectively (8 hours - breaks)
            # Add 20% buffer for unexpected issues
            staff_needed = int((estimated_hours / 6) * 1.2) + 1
            staff_needed = max(3, min(20, staff_needed))  # Min 3, max 20
            
            data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'day_of_week': day_of_week,
                'is_weekend': is_weekend,
                'season': season,
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms,
                'checkout_rooms': checkout_rooms,
                'stayover_rooms': stayover_rooms,
                'vip_rooms': vip_rooms,
                'occupancy_rate': round(occupancy_rate, 3),
                'avg_room_type_points': round(avg_room_type_points, 2),
                'staff_needed': staff_needed,
                'estimated_hours': round(estimated_hours, 1)
            })
        
        return pd.DataFrame(data)
