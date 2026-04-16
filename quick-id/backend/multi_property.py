"""
Multi-Property & Kiosk Modu
- Zincir otel desteği (merkezi DB, property bazlı erişim)
- Kiosk modu (lobby self-service)
- Offline mod (yerel tarama, senkronizasyon)
"""
from datetime import datetime, timezone
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid


# ============== Property (Otel/Tesis) Yönetimi ==============

async def create_property(db: AsyncIOMotorDatabase, name: str, address: str = "",
                          phone: str = "", tax_no: str = "", city: str = "",
                          created_by: str = None, **kwargs) -> dict:
    """Yeni tesis/otel oluştur"""
    col = db["properties"]
    
    property_doc = {
        "property_id": str(uuid.uuid4()),
        "name": name,
        "address": address,
        "phone": phone,
        "tax_no": tax_no,
        "city": city,
        "is_active": True,
        "settings": {
            "kiosk_enabled": False,
            "pre_checkin_enabled": True,
            "face_matching_enabled": False,
            "auto_emniyet_bildirimi": True,
        },
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "created_by": created_by,
        **{k: v for k, v in kwargs.items() if v is not None}
    }
    
    result = await col.insert_one(property_doc)
    property_doc["_id"] = result.inserted_id
    return property_doc


async def list_properties(db: AsyncIOMotorDatabase, is_active: Optional[bool] = None) -> list:
    """Tüm tesisleri listele"""
    col = db["properties"]
    query = {}
    if is_active is not None:
        query["is_active"] = is_active
    
    cursor = col.find(query).sort("created_at", -1)
    properties = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        properties.append(doc)
    return properties


async def get_property(db: AsyncIOMotorDatabase, property_id: str) -> Optional[dict]:
    """Tesis detayını getir"""
    col = db["properties"]
    doc = await col.find_one({"property_id": property_id})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def update_property(db: AsyncIOMotorDatabase, property_id: str, updates: dict) -> Optional[dict]:
    """Tesis bilgilerini güncelle"""
    col = db["properties"]
    updates["updated_at"] = datetime.now(timezone.utc)
    result = await col.update_one({"property_id": property_id}, {"$set": updates})
    if result.matched_count == 0:
        return None
    doc = await col.find_one({"property_id": property_id})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


# ============== Kiosk Session Yönetimi ==============

async def create_kiosk_session(db: AsyncIOMotorDatabase, property_id: str,
                                kiosk_name: str = "Lobby Kiosk") -> dict:
    """Kiosk oturumu oluştur"""
    col = db["kiosk_sessions"]
    
    session_doc = {
        "session_id": str(uuid.uuid4()),
        "property_id": property_id,
        "kiosk_name": kiosk_name,
        "status": "active",
        "started_at": datetime.now(timezone.utc),
        "last_activity": datetime.now(timezone.utc),
        "scan_count": 0,
        "guest_count": 0,
    }
    
    result = await col.insert_one(session_doc)
    session_doc["_id"] = result.inserted_id
    return session_doc


async def update_kiosk_activity(db: AsyncIOMotorDatabase, session_id: str, 
                                 scan_increment: int = 0, guest_increment: int = 0):
    """Kiosk aktivitesini güncelle"""
    col = db["kiosk_sessions"]
    await col.update_one(
        {"session_id": session_id},
        {
            "$set": {"last_activity": datetime.now(timezone.utc)},
            "$inc": {"scan_count": scan_increment, "guest_count": guest_increment}
        }
    )


async def get_kiosk_sessions(db: AsyncIOMotorDatabase, property_id: Optional[str] = None,
                              status: Optional[str] = None) -> list:
    """Kiosk oturumlarını listele"""
    col = db["kiosk_sessions"]
    query = {}
    if property_id:
        query["property_id"] = property_id
    if status:
        query["status"] = status
    
    cursor = col.find(query).sort("last_activity", -1)
    sessions = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        sessions.append(doc)
    return sessions


# ============== Offline Sync ==============

async def store_offline_data(db: AsyncIOMotorDatabase, property_id: str,
                              data_type: str, data: list, device_id: str = None) -> dict:
    """Offline cihazdan gelen verileri sakla"""
    col = db["offline_sync"]
    
    sync_doc = {
        "sync_id": str(uuid.uuid4()),
        "property_id": property_id,
        "device_id": device_id or "unknown",
        "data_type": data_type,  # "scans", "guests"
        "data": data,
        "record_count": len(data),
        "status": "pending",  # pending, processed, failed
        "created_at": datetime.now(timezone.utc),
        "processed_at": None,
        "errors": [],
    }
    
    result = await col.insert_one(sync_doc)
    sync_doc["_id"] = result.inserted_id
    return sync_doc


async def get_pending_syncs(db: AsyncIOMotorDatabase, property_id: Optional[str] = None) -> list:
    """Bekleyen senkronizasyonları listele"""
    col = db["offline_sync"]
    query = {"status": "pending"}
    if property_id:
        query["property_id"] = property_id
    
    cursor = col.find(query).sort("created_at", 1)
    syncs = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        syncs.append(doc)
    return syncs


async def process_sync(db: AsyncIOMotorDatabase, sync_id: str, 
                        status: str = "processed", errors: list = None) -> Optional[dict]:
    """Senkronizasyon durumunu güncelle"""
    col = db["offline_sync"]
    update = {
        "status": status,
        "processed_at": datetime.now(timezone.utc),
    }
    if errors:
        update["errors"] = errors
    
    result = await col.update_one({"sync_id": sync_id}, {"$set": update})
    if result.matched_count == 0:
        return None
    doc = await col.find_one({"sync_id": sync_id})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


# ============== Pre-Arrival (QR ile ön check-in) ==============

async def create_precheckin_token(db: AsyncIOMotorDatabase, property_id: str,
                                   reservation_ref: str = None, guest_name: str = None,
                                   created_by: str = None) -> dict:
    """Ön check-in QR token oluştur"""
    col = db["precheckin_tokens"]
    
    token_doc = {
        "token_id": str(uuid.uuid4()),
        "property_id": property_id,
        "reservation_ref": reservation_ref or "",
        "guest_name": guest_name or "",
        "status": "active",  # active, used, expired
        "scan_data": None,
        "guest_id": None,
        "created_at": datetime.now(timezone.utc),
        "used_at": None,
        "created_by": created_by,
    }
    
    result = await col.insert_one(token_doc)
    token_doc["_id"] = result.inserted_id
    return token_doc


async def get_precheckin_token(db: AsyncIOMotorDatabase, token_id: str) -> Optional[dict]:
    """Ön check-in token bilgisini getir"""
    col = db["precheckin_tokens"]
    doc = await col.find_one({"token_id": token_id})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def use_precheckin_token(db: AsyncIOMotorDatabase, token_id: str,
                                scan_data: dict, guest_id: str = None) -> Optional[dict]:
    """Ön check-in tokenını kullan"""
    col = db["precheckin_tokens"]
    update = {
        "status": "used",
        "scan_data": scan_data,
        "guest_id": guest_id,
        "used_at": datetime.now(timezone.utc),
    }
    result = await col.update_one({"token_id": token_id, "status": "active"}, {"$set": update})
    if result.matched_count == 0:
        return None
    doc = await col.find_one({"token_id": token_id})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def list_precheckin_tokens(db: AsyncIOMotorDatabase, property_id: Optional[str] = None,
                                  status: Optional[str] = None, page: int = 1, limit: int = 20) -> dict:
    """Ön check-in tokenlarını listele"""
    col = db["precheckin_tokens"]
    query = {}
    if property_id:
        query["property_id"] = property_id
    if status:
        query["status"] = status
    
    total = await col.count_documents(query)
    skip = (page - 1) * limit
    cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    tokens = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        tokens.append(doc)
    return {"tokens": tokens, "total": total, "page": page, "limit": limit}
