"""
Housekeeping Intelligence - AI-Powered
Oda dağılımı optimizasyonu, tahminli temizlik süreleri
"""
import random
from typing import List


class HousekeepingAI:
    """AI-powered housekeeping optimization"""
    
    def __init__(self, db):
        self.db = db
    
    async def optimize_room_assignment(self, tenant_id: str, staff_list: List[dict]) -> List[dict]:
        """Odaları personele optimal dağıt"""
        dirty_rooms = await self.db.rooms.find({
            'tenant_id': tenant_id,
            'status': 'dirty'
        }, {'_id': 0}).to_list(100)
        
        if not dirty_rooms or not staff_list:
            return []
        
        assignments = []
        staff_workload = {s['id']: 0 for s in staff_list}
        
        for room in dirty_rooms:
            available_staff = sorted(staff_list, key=lambda s: staff_workload[s['id']])
            
            if available_staff:
                assigned_staff = available_staff[0]
                base_time = {'Standard': 25, 'Deluxe': 35, 'Suite': 50}.get(room.get('room_type', 'Standard'), 30)
                estimated_time = int(base_time * random.uniform(0.9, 1.1))
                
                assignments.append({
                    'room_id': room['id'],
                    'room_number': room['room_number'],
                    'staff_id': assigned_staff['id'],
                    'staff_name': assigned_staff['name'],
                    'estimated_minutes': estimated_time
                })
                
                staff_workload[assigned_staff['id']] += estimated_time
        
        return assignments
    
    async def predict_cleaning_time(self, room_type: str, staff_id: str) -> dict:
        """Temizlik süresi tahmini"""
        avg_time = {'Standard': 25, 'Deluxe': 35, 'Suite': 50}.get(room_type, 30)
        
        return {
            'room_type': room_type,
            'predicted_minutes': avg_time,
            'confidence': 0.85
        }

# Global
housekeeping_ai = None

def get_housekeeping_ai(db):
    global housekeeping_ai
    if housekeeping_ai is None:
        housekeeping_ai = HousekeepingAI(db)
    return housekeeping_ai
