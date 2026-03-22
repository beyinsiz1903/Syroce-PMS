from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone, timedelta
import uuid

from server import get_current_user, User, db


class MediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    SIGNATURE = "signature"


class MediaStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    QA_PENDING = "qa_pending"
    QA_APPROVED = "qa_approved"
    QA_REJECTED = "qa_rejected"


class MediaUploadRequest(BaseModel):
    module: str = Field(..., description="housekeeping, frontdesk, maintenance, guest_profile, etc.")
    entity_id: str = Field(..., description="Related entity (task id, booking id, work order id)")
    filename: str
    content_type: str
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    media_type: MediaType = MediaType.PHOTO
    qa_required: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MediaUploadResponse(BaseModel):
    media_id: str
    upload_url: str
    headers: Dict[str, str]
    expires_at: datetime
    status: MediaStatus


class MediaConfirmRequest(BaseModel):
    media_id: str
    storage_url: Optional[str] = None
    checksum: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


class MediaQARequest(BaseModel):
    media_id: str
    action: str = Field(..., description="'approve' or 'reject'")
    score: Optional[int] = Field(default=None, ge=1, le=10)
    notes: Optional[str] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_media(media: dict) -> dict:
    if not media:
        return media
    media = {k: v for k, v in media.items() if k != "_id"}
    return media


media_router = APIRouter(prefix="/media", tags=["media"])

MAX_MEDIA_SIZE = 25 * 1024 * 1024  # 25MB


def _generate_upload_url(media_id: str, filename: str) -> str:
    sanitized = filename.replace(" ", "_")
    return f"https://storage.roomops.local/{media_id}/{sanitized}"


@media_router.post("/request-upload", response_model=MediaUploadResponse)
async def request_media_upload(
    payload: MediaUploadRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a media placeholder and return a (mock) presigned URL."""
    if payload.size_bytes > MAX_MEDIA_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({payload.size_bytes} bytes). Max allowed is {MAX_MEDIA_SIZE}."
        )

    media_id = str(uuid.uuid4())
    upload_token = str(uuid.uuid4())
    expires_at = _now() + timedelta(minutes=15)

    media_doc = {
        "id": media_id,
        "tenant_id": current_user.tenant_id,
        "module": payload.module,
        "entity_id": payload.entity_id,
        "media_type": payload.media_type.value,
        "status": MediaStatus.PENDING.value,
        "qa_required": payload.qa_required,
        "metadata": payload.metadata,
        "filename": payload.filename,
        "content_type": payload.content_type,
        "size_bytes": payload.size_bytes,
        "upload_token": upload_token,
        "upload_url": _generate_upload_url(media_id, payload.filename),
        "expires_at": expires_at.isoformat(),
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat()
    }

    await db.media_assets.insert_one(media_doc)

    return MediaUploadResponse(
        media_id=media_id,
        upload_url=media_doc["upload_url"],
        headers={
            "x-upload-token": upload_token,
            "Content-Type": payload.content_type
        },
        expires_at=expires_at,
        status=MediaStatus.PENDING
    )


@media_router.post("/confirm")
async def confirm_media_upload(
    payload: MediaConfirmRequest,
    current_user: User = Depends(get_current_user)
):
    """Mark a media record as uploaded and ready for QA."""
    media = await db.media_assets.find_one({
        "tenant_id": current_user.tenant_id,
        "id": payload.media_id
    })

    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    update_doc = {
        "status": MediaStatus.QA_PENDING.value if media.get("qa_required") else MediaStatus.UPLOADED.value,
        "storage_url": payload.storage_url or media.get("storage_url") or media.get("upload_url"),
        "checksum": payload.checksum or media.get("checksum"),
        "content_type": payload.content_type or media.get("content_type"),
        "size_bytes": payload.size_bytes or media.get("size_bytes"),
        "uploaded_at": _now().isoformat(),
        "updated_at": _now().isoformat()
    }

    await db.media_assets.update_one(
        {"id": payload.media_id, "tenant_id": current_user.tenant_id},
        {"$set": update_doc}
    )

    media.update(update_doc)
    return {"success": True, "media": _serialize_media(media)}


@media_router.post("/qa/review")
async def review_media(
    payload: MediaQARequest,
    current_user: User = Depends(get_current_user)
):
    """Approve or reject uploaded media as part of QA workflow."""
    media = await db.media_assets.find_one({
        "tenant_id": current_user.tenant_id,
        "id": payload.media_id
    })

    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    if payload.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    new_status = MediaStatus.QA_APPROVED.value if payload.action == "approve" else MediaStatus.QA_REJECTED.value

    update_doc = {
        "status": new_status,
        "qa_status": new_status,
        "qa_score": payload.score,
        "qa_notes": payload.notes,
        "qa_reviewer_id": current_user.id,
        "qa_reviewer_name": current_user.name,
        "qa_reviewed_at": _now().isoformat(),
        "updated_at": _now().isoformat()
    }

    await db.media_assets.update_one(
        {"id": payload.media_id, "tenant_id": current_user.tenant_id},
        {"$set": update_doc}
    )

    media.update(update_doc)
    return {"success": True, "media": _serialize_media(media)}


@media_router.get("/list")
async def list_media(
    module: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Return media assets filtered by module/entity/status."""
    query = {"tenant_id": current_user.tenant_id}
    if module:
        query["module"] = module
    if entity_id:
        query["entity_id"] = entity_id
    if status:
        query["status"] = status

    items = await db.media_assets.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": items, "count": len(items)}


@media_router.get("/{media_id}")
async def get_media(
    media_id: str,
    current_user: User = Depends(get_current_user)
):
    media = await db.media_assets.find_one(
        {"tenant_id": current_user.tenant_id, "id": media_id},
        {"_id": 0}
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return media
