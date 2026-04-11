"""
Desktop Feature Enhancement Endpoints
- Revenue breakdown
- AI Upsell
- Cost management  
- POS menu/tables
- Housekeeping staff assignment
- Messaging (WhatsApp/SMS)
- Folio split/segment
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import uuid
import os
from motor.motor_asyncio import AsyncIOMotorClient

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db_name = os.environ.get('DB_NAME', 'hotel_pms')
db = client[db_name]

# Router
desktop_router = APIRouter()

# Dependency to get db (will be overridden by main app)
async def get_db():
    return db

# Mock current user for now - will use actual auth from server.py
class MockUser:
    def __init__(self):
        self.tenant_id = 'demo_hotel'
        self.id = 'demo_user'

async def get_current_user_mock():
    return MockUser()

# ============= MODELS =============

class RevenueBreakdownItem(BaseModel):
    category: str
    amount: float
    percentage: float
    
class UpsellProduct(BaseModel):
    id: str
    name: str
    description: str
    price: float
    category: str
    image_url: Optional[str] = None
    popular: bool = False
    ai_score: float
    
class CostEntry(BaseModel):
    id: str
    date: datetime
    category: str
    amount: float
    description: str
    
class MenuItem(BaseModel):
    id: str
    name: str
    category: str
    price: float
    cost: float
    available: bool
    outlet_id: str
    
class RestaurantTable(BaseModel):
    id: str
    table_number: int
    capacity: int
    status: str  # available, occupied, reserved
    outlet_id: str
    
class HousekeepingStaff(BaseModel):
    id: str
    name: str
    email: str
    role: str
    shift: str
    efficiency: int
    assigned_rooms: int
    active: bool
    
class MessagingTemplate(BaseModel):
    id: str
    name: str
    type: str  # whatsapp, sms, email
    content: str
    variables: List[str]
    
class FolioSplitRequest(BaseModel):
    folio_id: str
    split_type: str  # even, custom, by_item
    split_data: dict

# ============= ENDPOINTS =============

@desktop_router.get("/revenue/breakdown")
async def get_revenue_breakdown(
    month: Optional[str] = None,
    current_user = Depends(get_current_user_mock)
):
    """Get revenue breakdown by category"""
    query = {'tenant_id': current_user.tenant_id}
    if month:
        query['month'] = month
    else:
        query['month'] = datetime.now().strftime('%Y-%m')
    
    categories = await db.revenue_breakdown.find(query, {'_id': 0}).to_list(100)
    
    total = sum(cat['amount'] for cat in categories)
    
    return {
        'total_revenue': total,
        'breakdown': categories,
        'month': query['month']
    }

@desktop_router.get("/upsell/products")
async def get_upsell_products(
    category: Optional[str] = None,
    popular_only: bool = False,
    
    current_user = Depends(get_current_user_mock)
):
    """Get AI-recommended upsell products"""
    query = {'tenant_id': current_user.tenant_id}
    if category:
        query['category'] = category
    if popular_only:
        query['popular'] = True
    
    products = await db.upsell_products.find(query, {'_id': 0}).sort('ai_score', -1).to_list(100)
    
    return {
        'products': products,
        'total': len(products)
    }

@desktop_router.get("/costs/summary")
async def get_cost_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    
    current_user = Depends(get_current_user_mock)
):
    """Get cost management summary"""
    query = {'tenant_id': current_user.tenant_id}
    
    if start_date:
        query['date'] = {'$gte': datetime.fromisoformat(start_date)}
    if end_date:
        if 'date' not in query:
            query['date'] = {}
        query['date']['$lte'] = datetime.fromisoformat(end_date)
    
    # Default to last 30 days
    if 'date' not in query:
        query['date'] = {'$gte': datetime.now() - timedelta(days=30)}
    
    entries = await db.cost_entries.find(query, {'_id': 0}).to_list(1000)
    
    # Group by category
    by_category = {}
    for entry in entries:
        cat = entry['category']
        if cat not in by_category:
            by_category[cat] = {'total': 0, 'count': 0}
        by_category[cat]['total'] += entry['amount']
        by_category[cat]['count'] += 1
    
    total_costs = sum(entry['amount'] for entry in entries)
    
    return {
        'total_costs': round(total_costs, 2),
        'by_category': by_category,
        'entries_count': len(entries),
        'period': {
            'start': start_date or (datetime.now() - timedelta(days=30)).isoformat(),
            'end': end_date or datetime.now().isoformat()
        }
    }

@desktop_router.get("/pos/menu")
async def get_pos_menu(
    outlet_id: Optional[str] = None,
    category: Optional[str] = None,
    available_only: bool = True,
    
    current_user = Depends(get_current_user_mock)
):
    """Get POS menu items"""
    query = {'tenant_id': current_user.tenant_id}
    if outlet_id:
        query['outlet_id'] = outlet_id
    if category:
        query['category'] = category
    if available_only:
        query['available'] = True
    
    items = await db.menu_items.find(query, {'_id': 0}).to_list(200)
    
    # Group by category
    by_category = {}
    for item in items:
        cat = item['category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(item)
    
    return {
        'items': items,
        'by_category': by_category,
        'total': len(items)
    }

@desktop_router.get("/pos/tables")
async def get_restaurant_tables(
    outlet_id: str = 'main_restaurant',
    status: Optional[str] = None,
    
    current_user = Depends(get_current_user_mock)
):
    """Get restaurant tables"""
    query = {
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id
    }
    if status:
        query['status'] = status
    
    tables = await db.restaurant_tables.find(query, {'_id': 0}).sort('table_number', 1).to_list(100)
    
    # Status summary
    status_counts = {}
    for table in tables:
        st = table['status']
        status_counts[st] = status_counts.get(st, 0) + 1
    
    return {
        'tables': tables,
        'status_counts': status_counts,
        'total': len(tables)
    }

@desktop_router.put("/pos/tables/{table_id}/status")
async def update_table_status(
    table_id: str,
    new_status: str,
    
    current_user = Depends(get_current_user_mock)
):
    """Update table status"""
    result = await db.restaurant_tables.update_one(
        {'id': table_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'status': new_status}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Table not found")
    
    return {'success': True, 'table_id': table_id, 'new_status': new_status}

@desktop_router.get("/housekeeping/staff")
async def get_housekeeping_staff(
    shift: Optional[str] = None,
    active_only: bool = True,
    
    current_user = Depends(get_current_user_mock)
):
    """Get housekeeping staff list"""
    query = {'tenant_id': current_user.tenant_id}
    if shift:
        query['shift'] = shift
    if active_only:
        query['active'] = True
    
    staff = await db.housekeeping_staff.find(query, {'_id': 0}).sort('name', 1).to_list(100)
    
    # Calculate stats
    total_rooms_assigned = sum(s['assigned_rooms'] for s in staff)
    avg_efficiency = sum(s['efficiency'] for s in staff) / len(staff) if staff else 0
    
    return {
        'staff': staff,
        'total': len(staff),
        'total_rooms_assigned': total_rooms_assigned,
        'avg_efficiency': round(avg_efficiency, 1)
    }

@desktop_router.post("/housekeeping/staff/{staff_id}/assign")
async def assign_rooms_to_staff(
    staff_id: str,
    room_ids: List[str],
    
    current_user = Depends(get_current_user_mock)
):
    """Assign rooms to housekeeping staff"""
    # Update staff assigned rooms count
    result = await db.housekeeping_staff.update_one(
        {'id': staff_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'assigned_rooms': len(room_ids)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Staff not found")
    
    # Create assignments
    assignments = []
    for room_id in room_ids:
        assignments.append({
            'id': str(uuid.uuid4()),
            'staff_id': staff_id,
            'room_id': room_id,
            'assigned_at': datetime.now(),
            'status': 'pending',
            'tenant_id': current_user.tenant_id
        })
    
    if assignments:
        await db.room_assignments.insert_many(assignments)
    
    return {
        'success': True,
        'staff_id': staff_id,
        'rooms_assigned': len(room_ids)
    }

@desktop_router.get("/messaging/templates")
async def get_messaging_templates(
    template_type: Optional[str] = None,
    
    current_user = Depends(get_current_user_mock)
):
    """Get messaging templates"""
    query = {'tenant_id': current_user.tenant_id}
    if template_type:
        query['type'] = template_type
    
    templates = await db.messaging_templates.find(query, {'_id': 0}).to_list(100)
    
    return {
        'templates': templates,
        'total': len(templates)
    }

@desktop_router.post("/messaging/send")
async def send_message(
    recipient: str,
    template_id: str,
    variables: dict,
    channel: str,  # whatsapp, sms, email
    
    current_user = Depends(get_current_user_mock)
):
    """Send message via WhatsApp/SMS/Email (mock)"""
    # Get template
    template = await db.messaging_templates.find_one({'id': template_id, 'tenant_id': current_user.tenant_id})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Replace variables
    content = template['content']
    for key, value in variables.items():
        content = content.replace(f'{{{key}}}', str(value))
    
    # Log message (mock send)
    message_log = {
        'id': str(uuid.uuid4()),
        'recipient': recipient,
        'channel': channel,
        'content': content,
        'status': 'sent',  # Mock - always success
        'sent_at': datetime.now(),
        'tenant_id': current_user.tenant_id
    }
    
    await db.message_logs.insert_one(message_log)
    
    return {
        'success': True,
        'message_id': message_log['id'],
        'channel': channel,
        'status': 'sent',
        'note': 'Mock send - WhatsApp/SMS integration required for production'
    }

@desktop_router.post("/folio/{folio_id}/split")
async def split_folio(
    folio_id: str,
    split_request: FolioSplitRequest,
    
    current_user = Depends(get_current_user_mock)
):
    """Split folio into multiple folios"""
    # Get original folio
    folio = await db.folios.find_one({'id': folio_id, 'tenant_id': current_user.tenant_id})
    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")
    
    if folio['status'] != 'open':
        raise HTTPException(status_code=400, detail="Can only split open folios")
    
    # Get charges
    charges = await db.folio_charges.find({'folio_id': folio_id, 'voided': False}, {'_id': 0}).to_list(1000)
    
    if split_request.split_type == 'even':
        # Split evenly
        num_splits = split_request.split_data.get('num_folios', 2)
        charges_per_folio = len(charges) // num_splits
        
        new_folios = []
        for i in range(num_splits):
            new_folio_id = str(uuid.uuid4())
            new_folio = {
                **folio,
                'id': new_folio_id,
                'folio_number': f"{folio['folio_number']}-{i+1}",
                'split_from': folio_id,
                'created_at': datetime.now()
            }
            new_folio.pop('_id', None)
            new_folios.append(new_folio)
            
            # Assign charges
            start_idx = i * charges_per_folio
            end_idx = start_idx + charges_per_folio if i < num_splits - 1 else len(charges)
            
            for charge in charges[start_idx:end_idx]:
                charge['folio_id'] = new_folio_id
                charge['id'] = str(uuid.uuid4())
                await db.folio_charges.insert_one(charge)
        
        # Insert new folios
        await db.folios.insert_many(new_folios)
        
        # Close original folio
        await db.folios.update_one(
            {'id': folio_id},
            {'$set': {'status': 'split', 'split_into': [f['id'] for f in new_folios]}}
        )
        
        return {
            'success': True,
            'original_folio': folio_id,
            'new_folios': [f['id'] for f in new_folios],
            'split_type': 'even'
        }
    
    else:
        raise HTTPException(status_code=400, detail="Split type not implemented yet")

# Export router
__all__ = ['desktop_router']
