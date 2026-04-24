"""KVKK (Turkish GDPR) compliance utilities"""
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

# v109 Bug DAJ round-2 (architect P1): minimum retention floors prevent admin
# token compromise from purging forensic audit trail. Even with valid admin
# session, retention_days_audit cannot be lowered below MIN_AUDIT_RETENTION_DAYS.
# To override (regulator order, breakglass), set ALLOW_AUDIT_RETENTION_OVERRIDE=1
# env at deploy time + manual DB update (out-of-band, leaves disk evidence).
MIN_AUDIT_RETENTION_DAYS = 365
MIN_SCANS_RETENTION_DAYS = 30


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


class RetentionFloorViolation(Exception):
    """Raised when admin attempts to lower retention below regulatory floor."""
    pass


async def update_settings(db: AsyncIOMotorDatabase, updates: dict) -> dict:
    """Update KVKK/retention settings.

    v109 Bug DAJ round-2: enforce retention floors so a compromised admin
    token cannot reduce the audit retention to 1 day and then trigger cleanup
    to wipe forensic evidence. Raises RetentionFloorViolation on attempt.
    """
    import os as _os
    allow_override = _os.environ.get("ALLOW_AUDIT_RETENTION_OVERRIDE") == "1"

    if not allow_override:
        if "retention_days_audit" in updates and updates["retention_days_audit"] is not None:
            try:
                v = int(updates["retention_days_audit"])
            except (TypeError, ValueError):
                raise RetentionFloorViolation(
                    f"retention_days_audit gecersiz tip: {type(updates['retention_days_audit']).__name__}"
                )
            if v < MIN_AUDIT_RETENTION_DAYS:
                raise RetentionFloorViolation(
                    f"retention_days_audit en az {MIN_AUDIT_RETENTION_DAYS} gun olmalidir (KVKK forensic floor)"
                )
        if "retention_days_scans" in updates and updates["retention_days_scans"] is not None:
            try:
                v = int(updates["retention_days_scans"])
            except (TypeError, ValueError):
                raise RetentionFloorViolation(
                    f"retention_days_scans gecersiz tip: {type(updates['retention_days_scans']).__name__}"
                )
            if v < MIN_SCANS_RETENTION_DAYS:
                raise RetentionFloorViolation(
                    f"retention_days_scans en az {MIN_SCANS_RETENTION_DAYS} gun olmalidir"
                )

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

    # v109 Bug DAJ round-2 (architect P1 defense-in-depth): even if a stale
    # settings doc somehow contains a sub-floor retention, enforce floors at
    # cleanup time. ALLOW_AUDIT_RETENTION_OVERRIDE=1 env bypass for breakglass.
    import os as _os
    allow_override = _os.environ.get("ALLOW_AUDIT_RETENTION_OVERRIDE") == "1"

    now = datetime.now(timezone.utc)
    results = {"scans_deleted": 0, "audit_deleted": 0}

    # Cleanup old scans
    retention_scans = settings.get("retention_days_scans", 90)
    if not allow_override and retention_scans < MIN_SCANS_RETENTION_DAYS:
        retention_scans = MIN_SCANS_RETENTION_DAYS
    if retention_scans > 0:
        cutoff = now - timedelta(days=retention_scans)
        result = await db["scans"].delete_many({"created_at": {"$lt": cutoff}})
        results["scans_deleted"] = result.deleted_count

    # Cleanup old audit logs — forensic floor enforced
    retention_audit = settings.get("retention_days_audit", 365)
    if not allow_override and retention_audit < MIN_AUDIT_RETENTION_DAYS:
        retention_audit = MIN_AUDIT_RETENTION_DAYS
    if retention_audit > 0:
        cutoff = now - timedelta(days=retention_audit)
        result = await db["audit_logs"].delete_many({"created_at": {"$lt": cutoff}})
        results["audit_deleted"] = result.deleted_count

    # Self-audit: log the cleanup operation itself (immutable trail of who/when
    # purged what). This row sits inside audit_logs but only stale enough rows
    # were deleted, so this entry survives subsequent cleanups for ≥365 days.
    results["effective_retention_audit_days"] = retention_audit
    results["effective_retention_scans_days"] = retention_scans
    results["ran_at"] = now.isoformat()
    try:
        await db["audit_logs"].insert_one({
            "action": "data_cleanup_executed",
            "outcome": "success",
            "results": results,
            "created_at": now,
        })
    except Exception:
        pass
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
