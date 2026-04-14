import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api", tags=["PMS / Cashier"])

@router.get("/cashier/current-shift")
async def get_current_shift(current_user: User = Depends(get_current_user)):
    return {
        "shift": None,
        "transactions": []
    }

@router.post("/cashier/open-shift")
async def open_shift(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {
        "shift": {
            "id": str(uuid.uuid4()),
            "cashier_name": current_user.name if hasattr(current_user, 'name') else "Kasiyer",
            "opening_amount": body.get("opening_amount", 0),
            "cash_in": 0,
            "cash_out": 0,
            "status": "open",
            "opened_at": datetime.utcnow().isoformat()
        }
    }

@router.post("/cashier/close-shift")
async def close_shift(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {
        "status": "closed",
        "counted_amount": body.get("counted_amount", 0),
        "expected_amount": 0,
        "difference": 0,
        "closed_at": datetime.utcnow().isoformat()
    }

@router.get("/cashier/shift-history")
async def shift_history(limit: int = 20, current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    return {
        "shifts": [
            {
                "id": str(uuid.uuid4()),
                "cashier_name": "Ali Yilmaz",
                "opening_amount": 500,
                "closing_amount": 2350,
                "difference": 0,
                "status": "closed",
                "opened_at": (now - timedelta(hours=16)).isoformat(),
                "closed_at": (now - timedelta(hours=8)).isoformat()
            },
            {
                "id": str(uuid.uuid4()),
                "cashier_name": "Ayse Kaya",
                "opening_amount": 500,
                "closing_amount": 1820,
                "difference": -5,
                "status": "closed",
                "opened_at": (now - timedelta(hours=40)).isoformat(),
                "closed_at": (now - timedelta(hours=32)).isoformat()
            }
        ]
    }

@router.get("/laundry/orders")
async def get_laundry_orders(current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    return {
        "orders": [
            {
                "id": str(uuid.uuid4()),
                "room_number": "101",
                "guest_name": "Ahmet Yilmaz",
                "service_type": "wash_iron",
                "items": [{"name": "Gomlek", "quantity": 3, "price": 30}],
                "total": 90,
                "status": "in_progress",
                "created_at": now.isoformat(),
                "estimated_ready": (now + timedelta(hours=3)).isoformat()
            },
            {
                "id": str(uuid.uuid4()),
                "room_number": "205",
                "guest_name": "Fatma Demir",
                "service_type": "dry_clean",
                "items": [{"name": "Takim Elbise", "quantity": 1, "price": 80}],
                "total": 120,
                "status": "ready",
                "created_at": (now - timedelta(hours=2)).isoformat()
            },
            {
                "id": str(uuid.uuid4()),
                "room_number": "312",
                "guest_name": "John Smith",
                "service_type": "express",
                "items": [{"name": "Gomlek", "quantity": 2, "price": 30}, {"name": "Pantolon", "quantity": 1, "price": 40}],
                "total": 200,
                "status": "delivered",
                "created_at": (now - timedelta(days=1)).isoformat()
            }
        ]
    }

@router.post("/laundry/orders")
async def create_laundry_order(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {
        "id": str(uuid.uuid4()),
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    }

@router.patch("/laundry/orders/{order_id}")
async def update_laundry_order(order_id: str, body: dict = {}, current_user: User = Depends(get_current_user)):
    return {"id": order_id, "status": body.get("status", "updated")}

@router.get("/meeting-rooms")
async def get_meeting_rooms(current_user: User = Depends(get_current_user)):
    return {
        "rooms": [
            {"id": "1", "name": "Balo Salonu", "capacity": 500, "area": 800, "floor": "Zemin", "setup_types": ["theater", "banquet", "cocktail"], "equipment": ["Projektor", "Ses Sistemi", "Sahne"], "status": "available"},
            {"id": "2", "name": "Toplanti Salonu A", "capacity": 50, "area": 80, "floor": "1. Kat", "setup_types": ["classroom", "u_shape", "boardroom"], "equipment": ["Projektor", "Beyaz Perde", "Video Konferans"], "status": "available"},
            {"id": "3", "name": "Toplanti Salonu B", "capacity": 30, "area": 50, "floor": "1. Kat", "setup_types": ["classroom", "boardroom"], "equipment": ["LED Ekran", "Ses Sistemi"], "status": "reserved"},
            {"id": "4", "name": "VIP Toplanti Odasi", "capacity": 12, "area": 30, "floor": "2. Kat", "setup_types": ["boardroom"], "equipment": ["Video Konferans", "LED Ekran", "Ses Sistemi"], "status": "available"},
        ]
    }

@router.get("/meeting-rooms/reservations")
async def get_meeting_reservations(current_user: User = Depends(get_current_user)):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    return {
        "reservations": [
            {"id": "1", "room_name": "Toplanti Salonu A", "company_name": "ABC Holding", "event_name": "Yillik Toplanti", "date": today, "start_time": "09:00", "end_time": "12:00", "setup_type": "u_shape", "attendees": 25, "status": "confirmed"},
            {"id": "2", "room_name": "Balo Salonu", "company_name": "XYZ Corp", "event_name": "Gala Yemegi", "date": tomorrow, "start_time": "19:00", "end_time": "23:00", "setup_type": "banquet", "attendees": 200, "status": "tentative"},
        ]
    }

@router.post("/meeting-rooms/reservations")
async def create_meeting_reservation(body: dict = {}, current_user: User = Depends(get_current_user)):
    return {
        "id": str(uuid.uuid4()),
        "status": "confirmed",
        "created_at": datetime.utcnow().isoformat()
    }
