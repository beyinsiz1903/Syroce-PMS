"""User management endpoints (admin only): list, create, patch, delete, reset, unlock, lockout-status."""
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request

from auth import (
    check_account_lockout, hash_password, require_admin,
    unlock_account, validate_password_strength, verify_password,
)
from db import db, users_col
from helpers import create_auth_audit_log, serialize_doc
from rate_limit import limiter
from schemas import PasswordChange, UserCreate, UserUpdate

router = APIRouter()
logger = logging.getLogger("quickid")


@router.get("/api/users")
async def list_users(user=Depends(require_admin)):
    cursor = users_col.find({}).sort("created_at", -1)
    users = [serialize_doc(doc) async for doc in cursor]
    return {"users": users, "total": len(users)}


@router.post("/api/users")
async def create_user(request: Request, req: UserCreate, user=Depends(require_admin)):
    ip = request.client.host if request.client else None
    actor_id = user.get("sub")
    actor_email = user.get("email")
    existing = await users_col.find_one({"email": req.email})
    if existing:
        await create_auth_audit_log("user_created",
            actor_id=actor_id, actor_email=actor_email,
            target_email=req.email, outcome="blocked",
            reason="duplicate_email", ip_address=ip)
        raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı")
    if req.role not in ("admin", "reception"):
        await create_auth_audit_log("user_created",
            actor_id=actor_id, actor_email=actor_email,
            target_email=req.email, outcome="blocked",
            reason="invalid_role", ip_address=ip,
            metadata={"requested_role": req.role})
        raise HTTPException(status_code=400, detail="Geçersiz rol")
    pwd_check = validate_password_strength(req.password)
    if not pwd_check["valid"]:
        await create_auth_audit_log("user_created",
            actor_id=actor_id, actor_email=actor_email,
            target_email=req.email, outcome="blocked",
            reason="weak_password", ip_address=ip)
        raise HTTPException(status_code=400, detail={
            "message": "Şifre gereksinimleri karşılanmadı",
            "errors": pwd_check["errors"],
            "strength": pwd_check["strength"],
        })
    user_doc = {
        "email": req.email,
        "password_hash": hash_password(req.password),
        "name": req.name,
        "role": req.role,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "password_changed_at": datetime.now(timezone.utc),
    }
    result = await users_col.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    await create_auth_audit_log("user_created",
        actor_id=actor_id, actor_email=actor_email,
        target_id=str(result.inserted_id), target_email=req.email,
        outcome="success", ip_address=ip,
        metadata={"role": req.role, "name": req.name})
    logger.info(f"👤 Yeni kullanıcı oluşturuldu: {req.email} (rol: {req.role}) - oluşturan: {user.get('email')}")
    return {"success": True, "user": serialize_doc(user_doc)}


@router.patch("/api/users/{user_id}")
async def update_user(request: Request, user_id: str, req: UserUpdate, user=Depends(require_admin)):
    ip = request.client.host if request.client else None
    actor_id = user.get("sub")
    actor_email = user.get("email")
    try:
        oid = ObjectId(user_id)
    except Exception:
        await create_auth_audit_log("user_updated", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="invalid_user_id", ip_address=ip)
        raise HTTPException(status_code=400, detail="Invalid user ID")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "role" in updates and updates["role"] not in ("admin", "reception"):
        await create_auth_audit_log("user_updated", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="invalid_role", ip_address=ip,
            metadata={"requested_role": updates.get("role")})
        raise HTTPException(status_code=400, detail="Geçersiz rol")
    old_doc = await users_col.find_one({"_id": oid})
    updates["updated_at"] = datetime.now(timezone.utc)
    result = await users_col.update_one({"_id": oid}, {"$set": updates})
    if result.matched_count == 0:
        await create_auth_audit_log("user_updated", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="not_found", ip_address=ip)
        raise HTTPException(status_code=404)
    doc = await users_col.find_one({"_id": oid})
    diffs = {k: {"old": (old_doc or {}).get(k), "new": v} for k, v in updates.items()
             if k != "updated_at" and (old_doc or {}).get(k) != v}
    await create_auth_audit_log("user_updated", actor_id=actor_id, actor_email=actor_email,
        target_id=user_id, target_email=(doc or {}).get("email"),
        outcome="success", ip_address=ip, metadata={"changes": diffs})
    return {"success": True, "user": serialize_doc(doc)}


@router.delete("/api/users/{user_id}")
async def delete_user(request: Request, user_id: str, user=Depends(require_admin)):
    ip = request.client.host if request.client else None
    actor_id = user.get("sub")
    actor_email = user.get("email")
    try:
        oid = ObjectId(user_id)
    except Exception:
        await create_auth_audit_log("user_deleted", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="invalid_user_id", ip_address=ip)
        raise HTTPException(status_code=400, detail="Invalid user ID")
    # v48 Round-3: ObjectId-normalized self-target compare.
    try:
        if oid == ObjectId(user.get("sub") or ""):
            await create_auth_audit_log("user_delete_self_blocked",
                actor_id=actor_id, actor_email=actor_email,
                target_id=user_id, target_email=actor_email,
                outcome="blocked", reason="self_target", ip_address=ip)
            raise HTTPException(status_code=400, detail="Kendi hesabınızı silemezsiniz")
    except HTTPException:
        raise
    except Exception:
        await create_auth_audit_log("user_deleted", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="invalid_session", ip_address=ip)
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    target_doc = await users_col.find_one({"_id": oid})
    target_email = (target_doc or {}).get("email")
    result = await users_col.delete_one({"_id": oid})
    if result.deleted_count == 0:
        await create_auth_audit_log("user_deleted", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="not_found", ip_address=ip)
        raise HTTPException(status_code=404)
    await create_auth_audit_log("user_deleted", actor_id=actor_id, actor_email=actor_email,
        target_id=user_id, target_email=target_email,
        outcome="success", ip_address=ip)
    return {"success": True}


@router.post("/api/users/{user_id}/reset-password")
@limiter.limit("10/minute")
async def reset_user_password(request: Request, user_id: str, req: PasswordChange, user=Depends(require_admin)):
    ip = request.client.host if request.client else None
    actor_id = user.get("sub")
    actor_email = user.get("email")
    try:
        oid = ObjectId(user_id)
    except Exception:
        await create_auth_audit_log("admin_reset_password",
            actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked",
            reason="invalid_user_id", ip_address=ip)
        raise HTTPException(status_code=400)
    # v48 (Bug CG, Round-3): self-target ObjectId compare blocks UPPERCASE bypass.
    try:
        if oid == ObjectId(user.get("sub") or ""):
            await create_auth_audit_log("admin_reset_self_blocked",
                actor_id=actor_id, actor_email=actor_email,
                target_id=user_id, target_email=actor_email,
                outcome="blocked", reason="self_target", ip_address=ip)
            raise HTTPException(
                status_code=400,
                detail="Kendi şifrenizi bu uçtan değiştiremezsiniz; lütfen 'Şifremi Değiştir' bölümünü kullanın",
            )
    except HTTPException:
        raise
    except Exception:
        await create_auth_audit_log("admin_reset_password",
            actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked",
            reason="invalid_session", ip_address=ip)
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    pwd_check = validate_password_strength(req.new_password)
    if not pwd_check["valid"]:
        await create_auth_audit_log("admin_reset_password",
            actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked",
            reason="weak_password", ip_address=ip)
        raise HTTPException(status_code=400, detail={
            "message": "Şifre gereksinimleri karşılanmadı",
            "errors": pwd_check["errors"],
            "strength": pwd_check["strength"],
        })
    target_doc = await users_col.find_one({"_id": oid})
    if not target_doc:
        await create_auth_audit_log("admin_reset_password",
            actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked",
            reason="not_found", ip_address=ip)
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    target_email = target_doc.get("email")
    # v108 (Bug DAI): same-password reuse engelle.
    if verify_password(req.new_password, target_doc.get("password_hash", "")):
        await create_auth_audit_log("admin_reset_password",
            actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, target_email=target_email,
            outcome="blocked", reason="same_as_current", ip_address=ip)
        raise HTTPException(status_code=400, detail={
            "message": "Yeni şifre kullanıcının mevcut şifresinden farklı olmalı",
            "error_code": "SAME_AS_CURRENT_PASSWORD",
        })
    # v107 EK-2: admin reset = recovery semantics (re-enable + force_password_change).
    await users_col.update_one({"_id": oid}, {"$set": {
        "password_hash": hash_password(req.new_password),
        "password_changed_at": datetime.now(timezone.utc),
        "is_active": True,
        "force_password_change": True,
    }})
    await create_auth_audit_log("admin_reset_password",
        actor_id=actor_id, actor_email=actor_email,
        target_id=user_id, target_email=target_email,
        outcome="success", ip_address=ip)
    logger.info(f"🔑 Şifre sıfırlandı: user_id={user_id} - admin: {user.get('email')}")
    return {"success": True, "message": "Şifre sıfırlandı"}


@router.post("/api/users/{user_id}/unlock", tags=["Kullanıcı Yönetimi"], summary="Hesap kilidini aç")
@limiter.limit("10/minute")
async def unlock_user_account(request: Request, user_id: str, user=Depends(require_admin)):
    actor_id = str(user.get("sub") or user.get("id") or user.get("_id") or "")
    actor_email = user.get("email")
    ip = request.client.host if request and request.client else None
    try:
        oid = ObjectId(user_id)
    except Exception:
        await create_auth_audit_log("user_unlock", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="invalid_user_id", ip_address=ip)
        raise HTTPException(status_code=400, detail="Geçersiz kullanıcı ID")
    target_user = await users_col.find_one({"_id": oid})
    if not target_user:
        await create_auth_audit_log("user_unlock", actor_id=actor_id, actor_email=actor_email,
            target_id=user_id, outcome="blocked", reason="not_found", ip_address=ip)
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    result = await unlock_account(db, target_user["email"])
    await create_auth_audit_log("user_unlock", actor_id=actor_id, actor_email=actor_email,
        target_id=user_id, target_email=target_user.get("email"), outcome="success",
        ip_address=ip, metadata={"cleared_attempts": result.get("cleared_attempts", 0)})
    logger.info(f"🔓 Hesap kilidi açıldı: {target_user['email']} - admin: {user.get('email')}")
    return {"success": True, "message": "Hesap kilidi açıldı", "cleared_attempts": result["cleared_attempts"]}


@router.get("/api/users/{user_id}/lockout-status", tags=["Kullanıcı Yönetimi"], summary="Hesap kilit durumu")
async def get_lockout_status(user_id: str, user=Depends(require_admin)):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz kullanıcı ID")
    target_user = await users_col.find_one({"_id": oid})
    if not target_user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    status = await check_account_lockout(db, target_user["email"])
    return {"email": target_user["email"], "lockout": status}
