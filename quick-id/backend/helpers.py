"""Shared helpers for Quick-ID: serialization, image validation, audit, throttle."""
import asyncio
import base64
import logging
import re
from collections import deque
from datetime import datetime, timezone, timedelta

from bson import ObjectId
from fastapi import HTTPException, Request
from slowapi.util import get_remote_address

from auth import decode_token
from db import audit_col, guests_col
from schemas import MAX_IMAGE_BASE64_LENGTH, ID_EXTRACTION_PROMPT  # noqa: F401  (kept for callers)

logger = logging.getLogger("quickid")


# --- Rate-limit key ---
def get_user_or_ip(request: Request) -> str:
    """Rate limit key: use authenticated user email if available, else IP."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_token(token)
        if payload and payload.get("email"):
            return payload["email"]
    return get_remote_address(request)


# --- Mongo doc serializer (recursive, strips password_hash) ---
def serialize_doc(doc):
    if doc is None:
        return None
    result = {}
    for key, value in doc.items():
        if key == "_id":
            result["id"] = str(value)
        elif key == "password_hash":
            continue
        elif isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = [
                serialize_doc(v) if isinstance(v, dict)
                else str(v) if isinstance(v, (ObjectId, datetime))
                else v
                for v in value
            ]
        elif isinstance(value, dict):
            result[key] = serialize_doc(value)
        else:
            result[key] = value
    return result


# --- Image payload validation (magic bytes + decompression-bomb cap) ---
_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_DATA_URI_PREFIX = re.compile(r"^data:image/(jpeg|png|webp|gif);base64,", re.IGNORECASE)


def _validate_image_payload(image_base64: str) -> tuple[bytes, str]:
    """Return (raw_bytes, mime). Raises HTTPException(400) on any anomaly."""
    s = image_base64.strip()
    if _DATA_URI_PREFIX.match(s):
        s = s.split(",", 1)[1]
    if not _BASE64_RE.match(s):
        raise HTTPException(status_code=400,
            detail="Geçersiz fotoğraf: yalnızca base64-kodlu görüntü kabul edilir.")
    try:
        raw = base64.b64decode(s, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz fotoğraf: base64 çözümlenemedi.")
    if len(raw) < 64:
        raise HTTPException(status_code=400, detail="Geçersiz fotoğraf: dosya çok küçük.")
    detected_mime = None
    for sig, mime in _IMAGE_MAGIC:
        if raw.startswith(sig):
            detected_mime = mime
            break
    if not detected_mime and len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        detected_mime = "image/webp"
    if not detected_mime:
        raise HTTPException(status_code=400,
            detail="Geçersiz fotoğraf: yalnızca JPEG, PNG, WEBP veya GIF kabul edilir.")
    try:
        from PIL import Image
        from io import BytesIO
        import warnings
        Image.MAX_IMAGE_PIXELS = 25_000_000
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as im:
                im.verify()
                w, h = im.size
        if w * h > Image.MAX_IMAGE_PIXELS or w > 8192 or h > 8192:
            raise HTTPException(status_code=400,
                detail="Geçersiz fotoğraf: çözünürlük limitin üzerinde.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400,
            detail="Geçersiz fotoğraf: dosya bozuk veya tanınamadı.")
    return raw, detected_mime


# --- AI ID extraction ---
async def extract_id_data(image_base64: str) -> dict:
    """Extract data from one or more ID documents in an image using OpenAI Vision."""
    from llm_client import chat_with_vision_json

    result = await chat_with_vision_json(
        system_message=ID_EXTRACTION_PROMPT,
        user_text="Analyze ALL identity documents visible in this image. There may be 1 or more documents. Extract data from EACH document separately and return them in the documents array. Return ONLY the JSON structure, no markdown.",
        images_base64=[image_base64],
        model="gpt-4o",
    )
    if "documents" in result and isinstance(result["documents"], list):
        return result
    return {"document_count": 1, "documents": [result]}


# --- Duplicate guest detection ---
async def find_duplicates(id_number=None, first_name=None, last_name=None, birth_date=None, exclude_id=None):
    duplicates = []
    if id_number and id_number.strip():
        query = {"id_number": id_number.strip(), "anonymized": {"$ne": True}}
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        async for doc in guests_col.find(query):
            duplicates.append({**serialize_doc(doc), "match_type": "id_number", "match_confidence": "high"})
    if first_name and last_name and birth_date:
        query = {
            "first_name": {"$regex": f"^{first_name.strip()}$", "$options": "i"},
            "last_name": {"$regex": f"^{last_name.strip()}$", "$options": "i"},
            "birth_date": birth_date.strip(),
            "anonymized": {"$ne": True},
        }
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        existing_ids = {d["id"] for d in duplicates}
        async for doc in guests_col.find(query):
            s = serialize_doc(doc)
            if s["id"] not in existing_ids:
                duplicates.append({**s, "match_type": "name_birthdate", "match_confidence": "medium"})
    return duplicates


# --- Audit logging ---
TRACKED_FIELDS = ["first_name", "last_name", "id_number", "birth_date", "gender", "nationality",
                   "document_type", "document_number", "birth_place", "expiry_date", "issue_date",
                   "mother_name", "father_name", "address", "notes", "status"]


async def create_audit_log(guest_id, action, changes=None, old_data=None, new_data=None, metadata=None, user_email=None):
    audit_entry = {
        "guest_id": guest_id,
        "action": action,
        "changes": changes or {},
        "old_data": old_data or {},
        "new_data": new_data or {},
        "metadata": metadata or {},
        "user_email": user_email,
        "created_at": datetime.now(timezone.utc),
    }
    await audit_col.insert_one(audit_entry)


# v49 (Bug CJ): authentication & user-management audit trail.
async def create_auth_audit_log(action, *, actor_id=None, actor_email=None,
                                 target_id=None, target_email=None,
                                 outcome="success", reason=None,
                                 metadata=None, ip_address=None):
    try:
        await audit_col.insert_one({
            "category": "auth",
            "action": action,
            "actor_id": actor_id,
            "actor_email": actor_email,
            "target_id": target_id,
            "target_email": target_email,
            "outcome": outcome,
            "reason": reason,
            "ip_address": ip_address,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error(f"AUDIT WRITE FAIL action={action} outcome={outcome}: {e}")


def compute_field_diffs(old_data, new_data):
    diffs = {}
    for field in TRACKED_FIELDS:
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        if old_val != new_val and new_val is not None:
            diffs[field] = {"old": old_val, "new": new_val}
    return diffs


# --- Per-user-id sliding-window throttle for self-change-password ---
# v48 (Bug CF): inline (not slowapi) because we key by user_id, not IP, so a
# stolen access_token cannot brute-force the password while rotating IPs.
_chgpw_hits: dict[str, deque] = {}
_chgpw_lock = asyncio.Lock()
_CHGPW_MAX = 5
_CHGPW_WINDOW = 900  # 15 min


async def _chgpw_throttle_check(uid: str) -> None:
    async with _chgpw_lock:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=_CHGPW_WINDOW)
        dq = _chgpw_hits.setdefault(uid, deque())
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _CHGPW_MAX:
            retry = int((dq[0] + timedelta(seconds=_CHGPW_WINDOW) - now).total_seconds()) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Çok fazla şifre değiştirme denemesi. Lütfen {max(1, retry)} saniye sonra tekrar deneyin.",
                headers={"Retry-After": str(max(1, retry))},
            )
        dq.append(now)
        if len(_chgpw_hits) > 10_000:
            _chgpw_hits.clear()


def _chgpw_throttle_reset(uid: str) -> None:
    _chgpw_hits.pop(uid, None)
