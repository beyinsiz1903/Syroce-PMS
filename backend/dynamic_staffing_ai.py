"""
Dynamic Staffing AI - Optimal Personel Yönetimi
Talep bazlı otomatik personel planlama
"""
from datetime import datetime
from typing import Dict, List

class DynamicStaffingAI:
    """AI-powered personel optimizasyonu"""
    
    def __init__(self, db):
        self.db = db
        # Staffing ratios
        self.ratios = {
            'front_desk': 10,  # 1 staff per 10 arrivals
            'housekeeping': 12,  # 1 staff per 12 checkouts
            'fnb': 15,  # 1 staff per 15 covers
            'maintenance': 50  # 1 staff per 50 rooms
        }
    
    async def calculate_optimal_staffing(self, tenant_id: str, target_date: str) -> Dict:
        """Optimal personel ihtiyacı hesapla"""
        datetime.fromisoformat(target_date).date()
        
        # Get demand data
        arrivals = await self.db.bookings.count_documents({
            'tenant_id': tenant_id,
            'check_in': {'$regex': f'^{target_date}'},
            'status': {'$in': ['confirmed', 'guaranteed']}
        })
        
        departures = await self.db.bookings.count_documents({
            'tenant_id': tenant_id,
            'check_out': {'$regex': f'^{target_date}'}
        })
        
        # Calculate needs
        front_desk_needed = max(2, arrivals // self.ratios['front_desk'])
        housekeeping_needed = max(3, departures // self.ratios['housekeeping'])
        
        # Get available staff
        all_staff = await self.db.staff_members.find({
            'tenant_id': tenant_id,
            'active': True
        }, {'_id': 0}).to_list(200)
        
        front_desk_staff = [s for s in all_staff if s['department'] == 'front_desk']
        housekeeping_staff = [s for s in all_staff if s['department'] == 'housekeeping']
        
        return {
            'target_date': target_date,
            'demand': {
                'arrivals': arrivals,
                'departures': departures
            },
            'staffing_needs': {
                'front_desk': front_desk_needed,
                'housekeeping': housekeeping_needed,
                'fnb': 3,
                'maintenance': 1
            },
            'available_staff': {
                'front_desk': len(front_desk_staff),
                'housekeeping': len(housekeeping_staff)
            },
            'status': 'adequate' if len(front_desk_staff) >= front_desk_needed else 'understaffed'
        }
    
    async def generate_shift_schedule(self, tenant_id: str, target_date: str) -> List[Dict]:
        """Otomatik vardiya planı oluştur"""
        optimal = await self.calculate_optimal_staffing(tenant_id, target_date)
        
        # Generate schedule (simplified)
        schedule = [
            {
                'department': 'front_desk',
                'shift': 'morning',
                'start': '07:00',
                'end': '15:00',
                'staff_needed': optimal['staffing_needs']['front_desk']
            },
            {
                'department': 'housekeeping',
                'shift': 'morning',
                'start': '08:00',
                'end': '16:00',
                'staff_needed': optimal['staffing_needs']['housekeeping']
            }
        ]
        
        return schedule

# Global
staffing_ai = None

def get_staffing_ai(db):
    global staffing_ai
    if staffing_ai is None:
        staffing_ai = DynamicStaffingAI(db)
    return staffing_ai
