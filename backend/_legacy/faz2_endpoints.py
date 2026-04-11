"""
FAZ 2 Endpoints - Advanced Features
Sales CRM, Marketing Automation, Service Recovery
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
import uuid
from typing import Optional

# This file contains FAZ 2 endpoints that will be included in main server
# Import this in server.py: from faz2_endpoints import faz2_router

faz2_router = APIRouter(prefix="/api")

# ============= SALES CRM & LEAD MANAGEMENT =============

@faz2_router.post("/sales/leads")
async def create_lead(lead_data: dict, db, current_user):
    """Yeni satış lead'i oluştur"""
    lead = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'company_name': lead_data.get('company_name'),
        'contact_name': lead_data['contact_name'],
        'contact_email': lead_data['contact_email'],
        'contact_phone': lead_data.get('contact_phone'),
        'source': lead_data['source'],
        'status': 'new',
        'priority': lead_data.get('priority', 'medium'),
        'estimated_value': lead_data.get('estimated_value'),
        'estimated_rooms': lead_data.get('estimated_rooms'),
        'target_checkin': lead_data.get('target_checkin'),
        'target_checkout': lead_data.get('target_checkout'),
        'assigned_to': lead_data.get('assigned_to', current_user.id),
        'lead_score': 50,  # Initial score
        'notes': lead_data.get('notes'),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.sales_leads.insert_one(lead)
    
    return {
        'success': True,
        'message': 'Lead başarıyla oluşturuldu',
        'lead_id': lead['id'],
        'lead_score': lead['lead_score']
    }

@faz2_router.get("/sales/leads")
async def get_leads(status: Optional[str], db, current_user):
    """Lead'leri listele"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    
    leads = await db.sales_leads.find(query, {'_id': 0}).sort('created_at', -1).to_list(100)
    
    return {
        'leads': leads,
        'total': len(leads)
    }

@faz2_router.get("/sales/funnel")
async def get_sales_funnel(db, current_user):
    """Satış hunisi metrikleri"""
    # Count by status
    statuses = ['new', 'contacted', 'qualified', 'proposal_sent', 'negotiating', 'won', 'lost']
    funnel = {}
    
    for status in statuses:
        count = await db.sales_leads.count_documents({
            'tenant_id': current_user.tenant_id,
            'status': status
        })
        funnel[status] = count
    
    # Calculate conversion rates
    total_leads = sum(funnel.values())
    won_count = funnel['won']
    
    return {
        'funnel': funnel,
        'total_leads': total_leads,
        'win_rate': round((won_count / total_leads * 100) if total_leads > 0 else 0, 2),
        'active_leads': total_leads - funnel['won'] - funnel['lost']
    }

@faz2_router.post("/sales/activity")
async def log_sales_activity(activity_data: dict, db, current_user):
    """Satış aktivitesi kaydet"""
    activity = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'lead_id': activity_data['lead_id'],
        'activity_type': activity_data['activity_type'],
        'subject': activity_data['subject'],
        'description': activity_data.get('description'),
        'outcome': activity_data.get('outcome'),
        'next_action': activity_data.get('next_action'),
        'next_action_date': activity_data.get('next_action_date'),
        'created_by': current_user.id,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.sales_activities.insert_one(activity)
    
    # Update lead last_contacted
    await db.sales_leads.update_one(
        {'id': activity_data['lead_id']},
        {'$set': {'last_contacted_at': datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        'success': True,
        'message': 'Aktivite kaydedildi',
        'activity_id': activity['id']
    }

# ============= MARKETING AUTOMATION =============

@faz2_router.post("/marketing/campaigns")
async def create_campaign(campaign_data: dict, db, current_user):
    """Pazarlama kampanyası oluştur"""
    campaign = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': campaign_data['name'],
        'campaign_type': campaign_data.get('campaign_type', 'promotional'),
        'subject': campaign_data['subject'],
        'message': campaign_data['message'],
        'segment': campaign_data.get('segment', 'all'),  # all, vip, inactive, frequent
        'scheduled_date': campaign_data.get('scheduled_date'),
        'status': 'draft',  # draft, scheduled, sent, completed
        'sent_count': 0,
        'opened_count': 0,
        'clicked_count': 0,
        'created_by': current_user.id,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.marketing_campaigns.insert_one(campaign)
    
    return {
        'success': True,
        'message': 'Kampanya oluşturuldu',
        'campaign_id': campaign['id']
    }

@faz2_router.get("/marketing/segments")
async def get_customer_segments(db, current_user):
    """Müşteri segmentleri"""
    # VIP guests
    vip_count = await db.guests.count_documents({
        'tenant_id': current_user.tenant_id,
        'tags': 'vip'
    })
    
    # Frequent guests (3+ stays)
    frequent_count = await db.guests.count_documents({
        'tenant_id': current_user.tenant_id,
        'total_stays': {'$gte': 3}
    })
    
    # High spenders
    high_spender_count = await db.guests.count_documents({
        'tenant_id': current_user.tenant_id,
        'tags': 'high_spender'
    })
    
    # Inactive (no booking in last 6 months)
    (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    
    total_guests = await db.guests.count_documents({'tenant_id': current_user.tenant_id})
    
    return {
        'segments': [
            {'name': 'VIP Guests', 'count': vip_count, 'segment_id': 'vip'},
            {'name': 'Frequent Guests', 'count': frequent_count, 'segment_id': 'frequent'},
            {'name': 'High Spenders', 'count': high_spender_count, 'segment_id': 'high_spender'},
            {'name': 'All Guests', 'count': total_guests, 'segment_id': 'all'}
        ],
        'total_guests': total_guests
    }

# ============= SERVICE RECOVERY & COMPLAINT MANAGEMENT =============

@faz2_router.post("/service/complaints")
async def create_complaint(complaint_data: dict, db, current_user):
    """Şikayet kaydı oluştur"""
    complaint = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': complaint_data.get('guest_id'),
        'booking_id': complaint_data.get('booking_id'),
        'complaint_category': complaint_data['complaint_category'],  # room, service, fnb, noise, cleanliness
        'severity': complaint_data.get('severity', 'medium'),  # low, medium, high, critical
        'description': complaint_data['description'],
        'reported_by': complaint_data.get('reported_by', 'guest'),
        'status': 'open',  # open, investigating, resolved, closed
        'priority': complaint_data.get('priority', 'medium'),
        'assigned_to': complaint_data.get('assigned_to'),
        'compensation_offered': None,
        'compensation_amount': 0.0,
        'resolution_notes': None,
        'created_by': current_user.id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'resolved_at': None
    }
    
    await db.service_complaints.insert_one(complaint)
    
    # Alert MOD if severity is high or critical
    if complaint['severity'] in ['high', 'critical']:
        # Send alert (implement notification system)
        pass
    
    return {
        'success': True,
        'message': 'Şikayet kaydedildi',
        'complaint_id': complaint['id'],
        'severity': complaint['severity']
    }

@faz2_router.get("/service/complaints")
async def get_complaints(status: Optional[str], db, current_user):
    """Şikayetleri listele"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    
    complaints = await db.service_complaints.find(query, {'_id': 0}).sort('created_at', -1).to_list(100)
    
    return {
        'complaints': complaints,
        'total': len(complaints)
    }

@faz2_router.post("/service/complaints/{complaint_id}/resolve")
async def resolve_complaint(complaint_id: str, resolution_data: dict, db, current_user):
    """Şikayeti çöz"""
    complaint = await db.service_complaints.find_one({
        'id': complaint_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not complaint:
        raise HTTPException(status_code=404, detail="Şikayet bulunamadı")
    
    # Update complaint
    await db.service_complaints.update_one(
        {'id': complaint_id},
        {
            '$set': {
                'status': 'resolved',
                'resolution_notes': resolution_data.get('resolution_notes'),
                'compensation_offered': resolution_data.get('compensation_offered'),
                'compensation_amount': resolution_data.get('compensation_amount', 0),
                'resolved_at': datetime.now(timezone.utc).isoformat(),
                'resolved_by': current_user.id
            }
        }
    )
    
    # If compensation offered, add to folio
    if resolution_data.get('compensation_offered') and complaint.get('booking_id'):
        folio = await db.folios.find_one({
            'booking_id': complaint['booking_id'],
            'folio_type': 'guest'
        }, {'_id': 0})
        
        if folio:
            charge = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'folio_id': folio['id'],
                'charge_category': 'adjustment',
                'description': f'Service recovery - {resolution_data.get("compensation_offered")}',
                'amount': -abs(resolution_data.get('compensation_amount', 0)),
                'posted_at': datetime.now(timezone.utc).isoformat(),
                'voided': False
            }
            await db.folio_charges.insert_one(charge)
    
    return {
        'success': True,
        'message': 'Şikayet çözüldü ve kaydedildi',
        'compensation_applied': resolution_data.get('compensation_offered') is not None
    }

# Note: These endpoints will be included in server.py
# Example usage in server.py:
# try:
#     from faz2_endpoints import faz2_router
#     app.include_router(faz2_router)
# except ImportError:
#     pass
