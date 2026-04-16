"""
Yedekleme/Restore Prosedürü
- Veritabanı yedekleme planı
- Manuel yedekleme
- Yedekten geri yükleme
- Yedek listesi
"""
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
import json
import os


BACKUP_DIR = "/app/backups"

# Yedeklenecek koleksiyonlar
BACKUP_COLLECTIONS = [
    "guests", "scans", "audit_logs", "users",
    "properties", "rooms", "room_assignments",
    "kiosk_sessions", "offline_sync", "precheckin_tokens",
    "emniyet_bildirimleri", "kvkk_rights_requests",
    "biometric_matches", "liveness_checks",
    "ai_cost_tracking",
]


def ensure_backup_dir():
    """Yedekleme dizinini oluştur"""
    os.makedirs(BACKUP_DIR, exist_ok=True)


async def create_backup(db: AsyncIOMotorDatabase, created_by: str = None,
                        description: str = "") -> dict:
    """Veritabanı yedeği oluştur"""
    ensure_backup_dir()
    
    backup_id = str(uuid.uuid4())
    backup_time = datetime.now(timezone.utc)
    backup_filename = f"backup_{backup_time.strftime('%Y%m%d_%H%M%S')}_{backup_id[:8]}.json"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    backup_data = {
        "backup_id": backup_id,
        "created_at": backup_time.isoformat(),
        "created_by": created_by,
        "description": description,
        "collections": {},
        "stats": {},
    }
    
    total_records = 0
    
    for collection_name in BACKUP_COLLECTIONS:
        col = db[collection_name]
        records = []
        async for doc in col.find({}):
            # Convert ObjectId and datetime for JSON serialization
            record = {}
            for key, value in doc.items():
                if key == "_id":
                    record["_id"] = str(value)
                elif isinstance(value, datetime):
                    record[key] = value.isoformat()
                else:
                    record[key] = value
            records.append(record)
        
        backup_data["collections"][collection_name] = records
        backup_data["stats"][collection_name] = len(records)
        total_records += len(records)
    
    backup_data["total_records"] = total_records
    
    # Write backup file
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)
    
    file_size = os.path.getsize(backup_path)
    
    # Record backup metadata in DB
    meta_col = db["backup_metadata"]
    metadata = {
        "backup_id": backup_id,
        "filename": backup_filename,
        "filepath": backup_path,
        "created_at": backup_time,
        "created_by": created_by,
        "description": description,
        "total_records": total_records,
        "file_size_bytes": file_size,
        "collections_backed_up": list(backup_data["stats"].keys()),
        "stats": backup_data["stats"],
    }
    await meta_col.insert_one(metadata)
    
    return {
        "backup_id": backup_id,
        "filename": backup_filename,
        "created_at": backup_time.isoformat(),
        "total_records": total_records,
        "file_size_bytes": file_size,
        "stats": backup_data["stats"],
        "message": f"Yedekleme başarılı: {total_records} kayıt yedeklendi.",
    }


async def list_backups(db: AsyncIOMotorDatabase) -> list:
    """Yedek listesini getir"""
    col = db["backup_metadata"]
    cursor = col.find({}).sort("created_at", -1)
    backups = []
    async for doc in cursor:
        backups.append({
            "backup_id": doc.get("backup_id"),
            "filename": doc.get("filename"),
            "created_at": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else str(doc.get("created_at", "")),
            "created_by": doc.get("created_by"),
            "description": doc.get("description", ""),
            "total_records": doc.get("total_records", 0),
            "file_size_bytes": doc.get("file_size_bytes", 0),
            "stats": doc.get("stats", {}),
        })
    return backups


async def restore_backup(db: AsyncIOMotorDatabase, backup_id: str,
                         restore_by: str = None) -> dict:
    """Yedekten geri yükleme"""
    meta_col = db["backup_metadata"]
    metadata = await meta_col.find_one({"backup_id": backup_id})
    if not metadata:
        raise ValueError("Yedek bulunamadı")
    
    filepath = metadata.get("filepath", "")
    if not os.path.exists(filepath):
        raise ValueError(f"Yedek dosyası bulunamadı: {filepath}")
    
    with open(filepath, "r", encoding="utf-8") as f:
        backup_data = json.load(f)
    
    restored_stats = {}
    
    for collection_name, records in backup_data.get("collections", {}).items():
        col = db[collection_name]
        if records:
            # Drop existing and restore
            await col.drop()
            # Remove _id to let MongoDB generate new ones, or keep if needed
            for record in records:
                record.pop("_id", None)
            if records:
                await col.insert_many(records)
        restored_stats[collection_name] = len(records)
    
    return {
        "success": True,
        "backup_id": backup_id,
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "restored_by": restore_by,
        "stats": restored_stats,
        "message": "Geri yükleme başarılı. Lütfen verileri kontrol edin.",
    }


def get_backup_schedule() -> dict:
    """Yedekleme planını göster"""
    return {
        "schedule": {
            "daily": {
                "enabled": True,
                "time": "03:00 UTC",
                "retention_days": 7,
                "description": "Her gece 03:00'te otomatik yedekleme",
            },
            "weekly": {
                "enabled": True,
                "day": "Pazar",
                "time": "02:00 UTC",
                "retention_days": 30,
                "description": "Her Pazar 02:00'de haftalık yedekleme",
            },
            "monthly": {
                "enabled": True,
                "day": 1,
                "time": "01:00 UTC",
                "retention_days": 365,
                "description": "Her ayın 1'inde aylık yedekleme",
            },
        },
        "collections": BACKUP_COLLECTIONS,
        "backup_location": BACKUP_DIR,
        "note": "Otomatik yedekleme planı. Manuel yedekleme de desteklenir.",
    }
