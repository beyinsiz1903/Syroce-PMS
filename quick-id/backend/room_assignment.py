"""
Oda Atama Modülü (Düzeltilmiş)
- Oda yönetimi (CRUD)
- Manuel oda atama (ID uyumlu)
- Scan sonrası otomatik oda atama
- Müsait oda kontrolü
- Serialization güvenli
"""
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import uuid


# Oda tipleri
ROOM_TYPES = [
    {"code": "standard", "name": "Standart Oda"},
    {"code": "deluxe", "name": "Deluxe Oda"},
    {"code": "suite", "name": "Süit"},
    {"code": "family", "name": "Aile Odası"},
    {"code": "single", "name": "Tek Kişilik"},
    {"code": "double", "name": "Çift Kişilik"},
    {"code": "twin", "name": "İki Yataklı"},
]

ROOM_STATUSES = ["available", "occupied", "cleaning", "maintenance", "reserved"]


def serialize_room(doc):
    """Oda dokümanını JSON-safe dict'e çevir"""
    if doc is None:
        return None
    result = {}
    for key, value in doc.items():
        if key == "_id":
            result["id"] = str(value)
        elif isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = [str(v) if isinstance(v, (ObjectId, datetime)) else v for v in value]
        elif isinstance(value, dict):
            result[key] = serialize_room(value)
        else:
            result[key] = value
    return result


async def create_room(db: AsyncIOMotorDatabase, room_number: str, room_type: str = "standard",
                      floor: int = 1, capacity: int = 2, property_id: str = None,
                      features: list = None) -> dict:
    """Yeni oda oluştur"""
    col = db["rooms"]

    # Check if room already exists
    existing = await col.find_one({"room_number": room_number, "property_id": property_id or "default"})
    if existing:
        raise ValueError(f"Oda {room_number} zaten mevcut")

    room_doc = {
        "room_id": str(uuid.uuid4()),
        "room_number": room_number,
        "room_type": room_type,
        "floor": floor,
        "capacity": capacity,
        "property_id": property_id or "default",
        "status": "available",
        "current_guest_ids": [],
        "features": features or [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    result = await col.insert_one(room_doc)
    room_doc["_id"] = result.inserted_id
    return serialize_room(room_doc)


async def list_rooms(db: AsyncIOMotorDatabase, property_id: str = None,
                     status: str = None, room_type: str = None,
                     floor: int = None) -> list:
    """Odaları listele"""
    col = db["rooms"]
    query = {}
    if property_id:
        query["property_id"] = property_id
    if status:
        query["status"] = status
    if room_type:
        query["room_type"] = room_type
    if floor is not None:
        query["floor"] = floor

    cursor = col.find(query).sort("room_number", 1)
    rooms = []
    async for doc in cursor:
        rooms.append(serialize_room(doc))
    return rooms


async def find_room_by_any_id(col, room_id: str):
    """room_id (UUID), _id (ObjectId string), veya room_number ile oda bul"""
    if not room_id:
        return None

    # 1. Try room_id (UUID field)
    room = await col.find_one({"room_id": room_id})
    if room:
        return room

    # 2. Try as MongoDB ObjectId
    try:
        oid = ObjectId(room_id)
        room = await col.find_one({"_id": oid})
        if room:
            return room
    except Exception:
        pass

    # 3. Try as room_number (fallback)
    room = await col.find_one({"room_number": room_id})
    if room:
        return room

    return None


async def get_room(db: AsyncIOMotorDatabase, room_id: str) -> Optional[dict]:
    """Oda detayını getir"""
    col = db["rooms"]
    doc = await find_room_by_any_id(col, room_id)
    return serialize_room(doc)


async def update_room(db: AsyncIOMotorDatabase, room_id: str, updates: dict) -> Optional[dict]:
    """Oda bilgilerini güncelle"""
    col = db["rooms"]
    room = await find_room_by_any_id(col, room_id)
    if not room:
        return None
    updates["updated_at"] = datetime.now(timezone.utc)
    await col.update_one({"_id": room["_id"]}, {"$set": updates})
    doc = await col.find_one({"_id": room["_id"]})
    return serialize_room(doc)


async def assign_room(db: AsyncIOMotorDatabase, room_id: str, guest_id: str) -> dict:
    """Misafire oda ata"""
    col = db["rooms"]
    room = await find_room_by_any_id(col, room_id)
    if not room:
        raise ValueError(f"Oda bulunamadı (ID: {room_id})")

    actual_room_id = room.get("room_id", str(room.get("_id", room_id)))

    if room["status"] not in ("available", "reserved"):
        raise ValueError(f"Oda müsait değil (durum: {room['status']})")

    current_guests = room.get("current_guest_ids", [])
    if len(current_guests) >= room.get("capacity", 2):
        raise ValueError("Oda kapasitesi dolu")

    if guest_id not in current_guests:
        current_guests.append(guest_id)

    status = "occupied" if len(current_guests) > 0 else "available"

    await col.update_one(
        {"_id": room["_id"]},
        {"$set": {
            "current_guest_ids": current_guests,
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }}
    )

    # Update guest with room info
    guests_col = db["guests"]
    try:
        guest_oid = ObjectId(guest_id)
        await guests_col.update_one(
            {"_id": guest_oid},
            {"$set": {
                "room_number": room["room_number"],
                "room_id": actual_room_id,
                "updated_at": datetime.now(timezone.utc),
            }}
        )
    except Exception:
        pass

    # Create assignment record
    assignments_col = db["room_assignments"]
    assignment = {
        "assignment_id": str(uuid.uuid4()),
        "room_id": actual_room_id,
        "room_number": room["room_number"],
        "guest_id": guest_id,
        "assigned_at": datetime.now(timezone.utc),
        "released_at": None,
        "status": "active",
    }
    await assignments_col.insert_one(assignment)

    updated_room = await col.find_one({"_id": room["_id"]})

    return {
        "room": serialize_room(updated_room),
        "assignment": {
            "assignment_id": assignment["assignment_id"],
            "room_id": assignment["room_id"],
            "room_number": assignment["room_number"],
            "guest_id": assignment["guest_id"],
            "assigned_at": assignment["assigned_at"].isoformat(),
            "status": assignment["status"],
        },
    }


async def release_room(db: AsyncIOMotorDatabase, room_id: str, guest_id: str = None) -> dict:
    """Odayı serbest bırak"""
    col = db["rooms"]
    room = await find_room_by_any_id(col, room_id)
    if not room:
        raise ValueError(f"Oda bulunamadı (ID: {room_id})")

    actual_room_id = room.get("room_id", str(room.get("_id", room_id)))

    current_guests = room.get("current_guest_ids", [])
    if guest_id:
        current_guests = [g for g in current_guests if g != guest_id]
    else:
        current_guests = []

    status = "cleaning" if len(current_guests) == 0 else "occupied"

    await col.update_one(
        {"_id": room["_id"]},
        {"$set": {
            "current_guest_ids": current_guests,
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }}
    )

    # Update assignment record
    assignments_col = db["room_assignments"]
    query = {"room_id": actual_room_id, "status": "active"}
    if guest_id:
        query["guest_id"] = guest_id
    await assignments_col.update_many(
        query,
        {"$set": {"status": "released", "released_at": datetime.now(timezone.utc)}}
    )

    updated_room = await col.find_one({"_id": room["_id"]})
    return serialize_room(updated_room)


async def auto_assign_room(db: AsyncIOMotorDatabase, guest_id: str,
                           property_id: str = None, preferred_type: str = None) -> Optional[dict]:
    """Scan sonrası otomatik oda atama"""
    col = db["rooms"]

    query = {"status": "available"}
    if property_id:
        query["property_id"] = property_id
    if preferred_type:
        query["room_type"] = preferred_type

    # Find first available room sorted by floor then room number
    room = await col.find_one(query, sort=[("floor", 1), ("room_number", 1)])
    if not room:
        return None

    # Use the room_id UUID or fallback to ObjectId string
    room_identifier = room.get("room_id") or str(room["_id"])
    result = await assign_room(db, room_identifier, guest_id)
    return result


async def get_room_stats(db: AsyncIOMotorDatabase, property_id: str = None) -> dict:
    """Oda istatistikleri"""
    col = db["rooms"]
    query = {}
    if property_id:
        query["property_id"] = property_id

    total = await col.count_documents(query)
    available = await col.count_documents({**query, "status": "available"})
    occupied = await col.count_documents({**query, "status": "occupied"})
    cleaning = await col.count_documents({**query, "status": "cleaning"})
    maintenance = await col.count_documents({**query, "status": "maintenance"})
    reserved = await col.count_documents({**query, "status": "reserved"})

    return {
        "total": total,
        "available": available,
        "occupied": occupied,
        "cleaning": cleaning,
        "maintenance": maintenance,
        "reserved": reserved,
        "occupancy_rate": round((occupied / total * 100), 1) if total > 0 else 0,
    }
