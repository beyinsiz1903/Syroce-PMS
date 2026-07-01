"""Guest CRUD, duplicate-check, check-in/out, restore, group check-in, photo upload/get."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo import ReturnDocument

from auth import require_admin, require_auth
from db import db, guests_col, users_col
from email_service import notify_checkin, notify_checkout
from helpers import (
    _validate_image_payload, compute_field_diffs, create_audit_log,
    find_duplicates, serialize_doc,
)
from image_quality import assess_image_quality
from rate_limit import limiter
from room_assignment import assign_room, get_room
from schemas import (
    MAX_IMAGE_BASE64_LENGTH, GroupCheckinRequest, GuestCreate,
    GuestPhotoRequest, GuestUpdate,
)

router = APIRouter()
logger = logging.getLogger("quickid")


@router.get("/api/guests/check-duplicate")
@limiter.limit("60/minute")
async def check_duplicate(
    request: Request,
    id_number: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    birth_date: Optional[str] = None,
    user=Depends(require_auth),
):
    duplicates = await find_duplicates(id_number, first_name, last_name, birth_date)
    return {"has_duplicates": len(duplicates) > 0, "duplicates": duplicates, "count": len(duplicates)}


@router.post("/api/guests")
@limiter.limit("30/minute")
async def create_guest(request: Request, guest: GuestCreate, user=Depends(require_auth)):
    if not guest.force_create:
        duplicates = await find_duplicates(guest.id_number, guest.first_name, guest.last_name, guest.birth_date)
        if duplicates:
            return {"success": False, "duplicate_detected": True, "duplicates": duplicates, "message": "Mükerrer misafir tespit edildi."}

    guest_data = guest.model_dump(exclude_none=True)
    original_extracted = guest_data.pop("original_extracted_data", None)
    guest_data.pop("force_create", None)
    scan_id = guest_data.pop("scan_id", None)
    kvkk_consent = guest_data.pop("kvkk_consent", False)

    guest_doc = {
        **guest_data,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "check_in_at": None,
        "check_out_at": None,
        "scan_ids": [scan_id] if scan_id else [],
        "original_extracted_data": original_extracted,
        "kvkk_consent": kvkk_consent,
        "kvkk_consent_at": datetime.now(timezone.utc) if kvkk_consent else None,
        "created_by": user.get("email"),
    }

    result = await guests_col.insert_one(guest_doc)
    guest_doc["_id"] = result.inserted_id
    guest_id = str(result.inserted_id)

    audit_changes = compute_field_diffs(original_extracted or {}, guest_data) if original_extracted else {}
    await create_audit_log(guest_id, "created", audit_changes, original_extracted or {}, guest_data,
                           {"scan_id": scan_id, "had_manual_edits": bool(audit_changes), "kvkk_consent": kvkk_consent},
                           user.get("email"))
    return {"success": True, "guest": serialize_doc(guest_doc)}


@router.get("/api/guests")
async def get_guests(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None, status: Optional[str] = None,
    nationality: Optional[str] = None, document_type: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    include_deleted: bool = Query(False, description="Silinen misafirleri de göster"),
    user=Depends(require_auth),
):
    query = {}
    if not include_deleted:
        query["status"] = {"$ne": "deleted"}
    if search:
        query["$or"] = [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"id_number": {"$regex": search, "$options": "i"}},
            {"document_number": {"$regex": search, "$options": "i"}},
        ]
    if status:
        query["status"] = status
    if nationality: query["nationality"] = {"$regex": nationality, "$options": "i"}
    if document_type: query["document_type"] = document_type
    if date_from:
        try: query.setdefault("created_at", {})["$gte"] = datetime.fromisoformat(date_from)
        except ValueError: pass
    if date_to:
        try: query.setdefault("created_at", {})["$lte"] = datetime.fromisoformat(date_to)
        except ValueError: pass

    skip = (page - 1) * limit
    total = await guests_col.count_documents(query)
    cursor = guests_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    guests = [serialize_doc(doc) async for doc in cursor]
    return {"guests": guests, "total": total, "page": page, "limit": limit}


@router.get("/api/guests/{guest_id}")
async def get_guest(guest_id: str, user=Depends(require_auth)):
    try: doc = await guests_col.find_one({"_id": ObjectId(guest_id)})
    except Exception: raise HTTPException(status_code=400, detail="Invalid guest ID")
    if not doc: raise HTTPException(status_code=404, detail="Guest not found")
    return {"guest": serialize_doc(doc)}


@router.patch("/api/guests/{guest_id}")
@limiter.limit("60/minute")
async def update_guest(request: Request, guest_id: str, update: GuestUpdate, user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400)
    old_doc = await guests_col.find_one({"_id": oid})
    if not old_doc: raise HTTPException(status_code=404)
    old_data = serialize_doc(old_doc)
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {"$set": update_data})
    doc = await guests_col.find_one({"_id": oid})
    diffs = compute_field_diffs(old_data, update_data)
    if diffs:
        await create_audit_log(guest_id, "updated", diffs,
                               {k: old_data.get(k) for k in diffs},
                               {k: update_data.get(k) for k in diffs},
                               user_email=user.get("email"))
    return {"success": True, "guest": serialize_doc(doc)}


@router.delete("/api/guests/{guest_id}")
@limiter.limit("30/minute")
async def delete_guest(request: Request, guest_id: str,
                       permanent: bool = Query(False, description="Kalıcı silme (true = geri alınamaz)"),
                       user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    doc = await guests_col.find_one({"_id": oid})
    if not doc: raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    if permanent:
        # v48 (architect Round-4): JWT 'role' STALE olabilir — DB'den canlı role + is_active bak.
        sub = user.get("sub")
        db_user = None
        if sub:
            try:
                db_user = await users_col.find_one({"_id": ObjectId(sub)})
            except Exception:
                db_user = None
        if not db_user or not db_user.get("is_active", True) or db_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Kalıcı silme için admin yetkisi gerekiyor")
        await create_audit_log(guest_id, "permanently_deleted", old_data=serialize_doc(doc), user_email=user.get("email"))
        await guests_col.delete_one({"_id": oid})
        logger.info(f"Guest {guest_id} permanently deleted by {user.get('email')}")
        return {"success": True, "action": "permanently_deleted"}
    else:
        now = datetime.now(timezone.utc)
        await guests_col.update_one({"_id": oid}, {"$set": {
            "status": "deleted", "deleted_at": now,
            "deleted_by": user.get("email"), "updated_at": now,
        }})
        await create_audit_log(guest_id, "soft_deleted", old_data=serialize_doc(doc), user_email=user.get("email"))
        logger.info(f"Guest {guest_id} soft-deleted by {user.get('email')}")
        return {"success": True, "action": "soft_deleted",
                "message": "Misafir silindi. Geri almak için admin ile iletişime geçin."}


@router.post("/api/guests/{guest_id}/restore", tags=["Misafirler"], summary="Silinen misafiri geri getir")
async def restore_guest(guest_id: str, user=Depends(require_admin)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    doc = await guests_col.find_one({"_id": oid})
    if not doc: raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    if doc.get("status") != "deleted":
        raise HTTPException(status_code=400, detail="Bu misafir silinmiş durumda değil")

    now = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {
        "$set": {"status": "pending", "updated_at": now},
        "$unset": {"deleted_at": "", "deleted_by": ""},
    })
    await create_audit_log(guest_id, "restored",
                           metadata={"restored_by": user.get("email")},
                           user_email=user.get("email"))
    doc = await guests_col.find_one({"_id": oid})
    logger.info(f"Guest {guest_id} restored by {user.get('email')}")
    return {"success": True, "guest": serialize_doc(doc)}


@router.post("/api/guests/{guest_id}/checkin")
async def checkin_guest(guest_id: str, user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400)
    old_doc = await guests_col.find_one({"_id": oid})
    if not old_doc: raise HTTPException(status_code=404)
    now = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {"$set": {"status": "checked_in", "check_in_at": now, "updated_at": now}})
    await create_audit_log(guest_id, "checked_in",
                           {"status": {"old": old_doc.get("status"), "new": "checked_in"}},
                           metadata={"check_in_at": now.isoformat()},
                           user_email=user.get("email"))
    logger.info(f"📥 Check-in: Guest {guest_id} by {user.get('email')}")
    doc = await guests_col.find_one({"_id": oid})
    try:
        guest_name = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
        await notify_checkin(guest_name, doc.get('room_number', ''), user.get('email'))
    except Exception:
        pass
    return {"success": True, "guest": serialize_doc(doc)}


@router.post("/api/guests/{guest_id}/checkout")
async def checkout_guest(guest_id: str, user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400)
    old_doc = await guests_col.find_one({"_id": oid})
    if not old_doc: raise HTTPException(status_code=404)
    now = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {"$set": {"status": "checked_out", "check_out_at": now, "updated_at": now}})
    await create_audit_log(guest_id, "checked_out",
                           {"status": {"old": old_doc.get("status"), "new": "checked_out"}},
                           metadata={"check_out_at": now.isoformat()},
                           user_email=user.get("email"))
    logger.info(f"📤 Check-out: Guest {guest_id} by {user.get('email')}")
    doc = await guests_col.find_one({"_id": oid})
    try:
        guest_name = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
        await notify_checkout(guest_name, doc.get('room_number', ''), user.get('email'))
    except Exception:
        pass
    return {"success": True, "guest": serialize_doc(doc)}


@router.post("/api/guests/group-checkin", tags=["Grup Check-in"], summary="Grup check-in",
             description="Birden fazla misafiri tek işlemde kayıt eder ve opsiyonel oda atar")
async def group_checkin(req: GroupCheckinRequest, user=Depends(require_auth)):
    results = {"successful": [], "failed": [], "room_assignment": None}

    for guest_id in req.guest_ids:
        try:
            oid = ObjectId(guest_id)
            old_doc = await guests_col.find_one({"_id": oid})
            if not old_doc:
                results["failed"].append({"guest_id": guest_id, "error": "Misafir bulunamadı"})
                continue

            now = datetime.now(timezone.utc)
            await guests_col.update_one(
                {"_id": oid},
                {"$set": {"status": "checked_in", "check_in_at": now, "updated_at": now}},
            )
            await create_audit_log(guest_id, "group_checked_in",
                                   {"status": {"old": old_doc.get("status"), "new": "checked_in"}},
                                   metadata={"group_checkin": True, "group_size": len(req.guest_ids)},
                                   user_email=user.get("email"))
            doc = await guests_col.find_one({"_id": oid})
            results["successful"].append(serialize_doc(doc))
        except Exception as e:
            results["failed"].append({"guest_id": guest_id, "error": str(e)})

    if req.room_id and results["successful"]:
        try:
            for guest in results["successful"]:
                await assign_room(db, room_id=req.room_id, guest_id=guest["id"])
            room = await get_room(db, req.room_id)
            results["room_assignment"] = {"success": True, "room": room}
        except Exception as e:
            results["room_assignment"] = {"success": False, "error": str(e)}

    return {
        "success": len(results["successful"]) > 0,
        "total_requested": len(req.guest_ids),
        "successful_count": len(results["successful"]),
        "failed_count": len(results["failed"]),
        "results": results,
    }


@router.post("/api/guests/{guest_id}/photo", tags=["Misafirler"], summary="Misafir fotoğrafı yükle",
             description="Check-in sırasında misafir fotoğrafı çeker ve kaydeder")
@limiter.limit("20/minute")
async def upload_guest_photo(request: Request, guest_id: str, req: GuestPhotoRequest, user=Depends(require_auth)):
    if len(req.image_base64) > MAX_IMAGE_BASE64_LENGTH:
        raise HTTPException(status_code=413, detail=f"Fotoğraf boyutu çok büyük. Maksimum {MAX_IMAGE_BASE64_LENGTH // (1024*1024)}MB izin verilir.")

    # v50 (Bug CK): magic-byte validation — JPEG/PNG/WEBP/GIF allowlist.
    raw_bytes, mime = _validate_image_payload(req.image_base64)

    try:
        oid = ObjectId(guest_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")

    guest = await guests_col.find_one({"_id": oid})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    quality = assess_image_quality(req.image_base64)

    # v51 R2 (architect concurrency fix): atomically read pre-image via
    # find_one_and_update(return_document=BEFORE) to avoid concurrent override
    # observing identical pre-images and breaking forensic chain.
    new_hash = hashlib.sha256(raw_bytes).hexdigest()
    new_size = len(raw_bytes)
    new_captured_at = datetime.now(timezone.utc)
    user_email = user.get("email")

    pre_doc = await guests_col.find_one_and_update(
        {"_id": oid},
        {"$set": {
            "has_photo": True,
            "photo_captured_at": new_captured_at,
            "photo_captured_by": user_email,
            "photo_sha256": new_hash,
            "photo_size_bytes": new_size,
            "photo_base64": req.image_base64,
            "updated_at": new_captured_at,
        }},
        return_document=ReturnDocument.BEFORE,
    )
    if not pre_doc:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    is_overwrite = bool(pre_doc.get("has_photo")) and bool(pre_doc.get("photo_base64"))
    old_data = {}
    if is_overwrite:
        old_data = {
            "captured_by": pre_doc.get("photo_captured_by"),
            "captured_at": (pre_doc.get("photo_captured_at").isoformat()
                            if isinstance(pre_doc.get("photo_captured_at"), datetime) else None),
            "sha256": pre_doc.get("photo_sha256"),
            "size_bytes": pre_doc.get("photo_size_bytes"),
        }

    photo_doc = {
        "photo_id": str(uuid.uuid4()),
        "guest_id": guest_id,
        "image_base64": req.image_base64[:100] + "...",
        "quality": quality,
        "captured_at": new_captured_at,
        "captured_by": user_email,
    }

    new_data = {
        "captured_by": user_email,
        "captured_at": new_captured_at.isoformat(),
        "sha256": new_hash,
        "size_bytes": new_size,
    }

    action = "photo_overwritten" if is_overwrite else "photo_captured"
    await create_audit_log(guest_id, action,
                           old_data=old_data, new_data=new_data,
                           metadata={"quality": quality.get("overall_quality", "unknown"),
                                     "mime": mime, "is_overwrite": is_overwrite},
                           user_email=user_email)

    return {
        "success": True,
        "photo_id": photo_doc["photo_id"],
        "quality": quality,
        "message": "Misafir fotoğrafı başarıyla kaydedildi",
    }


@router.get("/api/guests/{guest_id}/photo", tags=["Misafirler"], summary="Misafir fotoğrafı getir")
async def get_guest_photo(guest_id: str, user=Depends(require_auth)):
    try:
        oid = ObjectId(guest_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")

    guest = await guests_col.find_one({"_id": oid})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    if not guest.get("photo_base64"):
        raise HTTPException(status_code=404, detail="Misafir fotoğrafı bulunamadı")

    return {
        "success": True,
        "guest_id": guest_id,
        "has_photo": True,
        "photo_base64": guest["photo_base64"],
        "photo_captured_at": guest.get("photo_captured_at", "").isoformat() if isinstance(guest.get("photo_captured_at"), datetime) else str(guest.get("photo_captured_at", "")),
    }
