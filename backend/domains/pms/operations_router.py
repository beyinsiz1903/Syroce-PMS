from fastapi import APIRouter, Depends
from datetime import datetime, timedelta
import uuid

from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api", tags=["PMS / Operations"])

@router.get("/concierge/requests")
async def get_concierge_requests(current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    return {
        "requests": [
            {"id": "1", "type": "restaurant", "room_number": "301", "guest_name": "Ahmet Bey", "details": "Nusr-Et Etiler, 20:00, 4 kisi", "date": now.strftime("%Y-%m-%d"), "time": "20:00", "pax": 4, "status": "confirmed", "priority": "vip", "created_at": now.isoformat()},
            {"id": "2", "type": "transfer", "room_number": "505", "guest_name": "Mr. Smith", "details": "IST Havalimani, Mercedes VIP", "date": now.strftime("%Y-%m-%d"), "time": "14:00", "pax": 2, "status": "pending", "priority": "high", "created_at": now.isoformat()},
            {"id": "3", "type": "wakeup", "room_number": "202", "guest_name": "Fatma Hanim", "details": "07:00 uyandirma", "date": (now + timedelta(days=1)).strftime("%Y-%m-%d"), "time": "07:00", "pax": 1, "status": "pending", "priority": "normal", "created_at": now.isoformat()},
        ]
    }

@router.post("/concierge/requests")
async def create_concierge_request(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"id": str(uuid.uuid4()), "status": "pending", "created_at": datetime.utcnow().isoformat()}

@router.patch("/concierge/requests/{request_id}")
async def update_concierge_request(request_id: str, body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"id": request_id, "status": body.get("status", "updated")}

@router.get("/banquet/events")
async def get_banquet_events(current_user: User = Depends(get_current_user)):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    return {
        "events": [
            {"id": "1", "event_name": "ABC Holding Yillik Toplanti", "company": "ABC Holding A.S.", "contact_name": "Murat Ozturk", "contact_phone": "0532 111 2233", "room_name": "Toplanti Salonu A", "date": today, "start_time": "09:00", "end_time": "17:00", "setup_type": "u_shape", "attendees": 40, "guaranteed_pax": 35, "menu_type": "lunch", "menu_details": "Ogle yemegi + 2 kahve molasi", "av_equipment": ["Projektor", "Ses Sistemi"], "price_per_person": 350, "total_price": 14000, "deposit_amount": 7000, "status": "confirmed"},
            {"id": "2", "event_name": "Yilmaz - Kaya Dugun", "company": "Ozel", "contact_name": "Ayse Yilmaz", "contact_phone": "0544 555 6677", "room_name": "Balo Salonu", "date": tomorrow, "start_time": "19:00", "end_time": "02:00", "setup_type": "banquet", "attendees": 300, "guaranteed_pax": 280, "menu_type": "gala", "av_equipment": ["Ses Sistemi", "Isik Sistemi", "DJ Masasi", "Sahne"], "price_per_person": 800, "total_price": 240000, "deposit_amount": 120000, "status": "confirmed"},
        ]
    }

@router.post("/banquet/events")
async def create_banquet_event(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"id": str(uuid.uuid4()), "status": "tentative", "created_at": datetime.utcnow().isoformat()}

@router.post("/kbs/send")
async def send_kbs_notification(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"status": "sent", "kbs_reference": str(uuid.uuid4())[:8], "sent_at": datetime.utcnow().isoformat()}

@router.post("/kbs/send-batch")
async def send_kbs_batch(body: dict = {}, current_user: User = Depends(get_current_user)):
    booking_ids = body.get("booking_ids", [])
    return {"status": "sent", "count": len(booking_ids), "sent_at": datetime.utcnow().isoformat()}

@router.get("/kvkk/requests")
async def get_kvkk_requests(current_user: User = Depends(get_current_user)):
    return {"requests": []}

@router.post("/kvkk/requests")
async def create_kvkk_request(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"id": str(uuid.uuid4()), "status": "pending", "created_at": datetime.utcnow().isoformat()}

@router.patch("/pms/guests/{guest_id}/preferences")
async def update_guest_preferences(guest_id: str, body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"id": guest_id, "status": "updated", "preferences": body.get("preferences", {})}

@router.post("/frontdesk/booking/{booking_id}/routing-rules")
async def save_routing_rules(booking_id: str, body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"booking_id": booking_id, "rules_count": len(body.get("rules", [])), "status": "saved"}

@router.patch("/pms/rooms/{room_id}/features")
async def update_room_features(room_id: str, body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"id": room_id, "status": "updated"}
