"""KVKK (Turkish GDPR) compliance utilities"""
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase


DEFAULT_SETTINGS = {
    "retention_days_scans": 90,        # Auto-delete scans after N days
    "retention_days_audit": 365,       # Auto-delete audit logs after N days  
    "retention_days_deleted_guests": 30, # Permanently purge soft-deleted data after N days
    "store_scan_images": False,         # Whether to store raw scan images
    "kvkk_consent_required": True,      # Require KVKK consent before scanning
    "kvkk_consent_text": "Kimlik verileriniz yalnızca konaklama işlemleri kapsamında, 6698 sayılı KVKK uyarınca işlenecektir. Verileriniz yasal saklama süresi sonunda otomatik olarak silinecektir.",
    "data_processing_purpose": "Konaklama hizmetleri kapsamında misafir kayıt ve takip işlemleri",
    "auto_cleanup_enabled": True,
}


async def get_settings(db: AsyncIOMotorDatabase) -> dict:
    """Get current KVKK/retention settings"""
    settings_col = db["settings"]
    doc = await settings_col.find_one({"type": "kvkk"})
    if not doc:
        # Initialize with defaults
        settings = {"type": "kvkk", **DEFAULT_SETTINGS, "updated_at": datetime.now(timezone.utc)}
        await settings_col.insert_one(settings)
        return DEFAULT_SETTINGS
    # Return merged with defaults for any missing keys
    result = {**DEFAULT_SETTINGS}
    for k, v in doc.items():
        if k not in ("_id", "type", "updated_at"):
            result[k] = v
    return result


async def update_settings(db: AsyncIOMotorDatabase, updates: dict) -> dict:
    """Update KVKK/retention settings"""
    settings_col = db["settings"]
    updates["updated_at"] = datetime.now(timezone.utc)
    await settings_col.update_one(
        {"type": "kvkk"},
        {"$set": updates},
        upsert=True
    )
    return await get_settings(db)


async def run_data_cleanup(db: AsyncIOMotorDatabase) -> dict:
    """Run data cleanup based on retention policies"""
    settings = await get_settings(db)
    if not settings.get("auto_cleanup_enabled"):
        return {"skipped": True, "reason": "Auto cleanup disabled"}
    
    now = datetime.now(timezone.utc)
    results = {"scans_deleted": 0, "audit_deleted": 0}
    
    # Cleanup old scans
    retention_scans = settings.get("retention_days_scans", 90)
    if retention_scans > 0:
        cutoff = now - timedelta(days=retention_scans)
        result = await db["scans"].delete_many({"created_at": {"$lt": cutoff}})
        results["scans_deleted"] = result.deleted_count
    
    # Cleanup old audit logs
    retention_audit = settings.get("retention_days_audit", 365)
    if retention_audit > 0:
        cutoff = now - timedelta(days=retention_audit)
        result = await db["audit_logs"].delete_many({"created_at": {"$lt": cutoff}})
        results["audit_deleted"] = result.deleted_count
    
    results["ran_at"] = now.isoformat()
    return results


async def anonymize_guest(db: AsyncIOMotorDatabase, guest_id: str) -> bool:
    """Anonymize a guest's personal data (KVKK right to be forgotten)"""
    from bson import ObjectId
    try:
        oid = ObjectId(guest_id)
    except Exception:
        return False
    
    anonymized_data = {
        "first_name": "[SİLİNDİ]",
        "last_name": "[SİLİNDİ]",
        "id_number": "[SİLİNDİ]",
        "birth_date": None,
        "gender": None,
        "nationality": None,
        "document_number": None,
        "birth_place": None,
        "mother_name": None,
        "father_name": None,
        "address": None,
        "original_extracted_data": None,
        "notes": "[KVKK kapsamında anonimleştirildi]",
        "anonymized": True,
        "anonymized_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    
    result = await db["guests"].update_one({"_id": oid}, {"$set": anonymized_data})
    
    # Also anonymize related audit logs
    await db["audit_logs"].update_many(
        {"guest_id": guest_id},
        {"$set": {
            "changes": {},
            "old_data": {"note": "[KVKK kapsamında anonimleştirildi]"},
            "new_data": {"note": "[KVKK kapsamında anonimleştirildi]"},
        }}
    )
    
    return result.modified_count > 0
