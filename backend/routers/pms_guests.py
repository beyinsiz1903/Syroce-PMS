"""
PMS Guests Router — Extracted from routers/pms.py (Stage 1 decomposition)
Guest CRUD and search with field-level PII encryption.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from core.database import db
from core.helpers import require_module
from core.pagination import PaginationParams, paginate
from core.security import get_current_user
from models.schemas import Guest, GuestCreate, User
from modules.pms_core.role_permission_service import require_op
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
)

try:
    from security.field_encryption import get_field_encryption_service
    _fenc = get_field_encryption_service()
except Exception:
    _fenc = None

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["pms"])

_GUEST_COLLECTION = "guests"


def _encrypt_guest(doc: dict) -> dict:
    """Encrypt PII fields before DB write."""
    if _fenc:
        return _fenc.encrypt_document(doc, collection=_GUEST_COLLECTION)
    return doc


def _decrypt_guest(doc: dict) -> dict:
    """Decrypt PII fields after DB read."""
    if _fenc and doc:
        return _fenc.decrypt_document(doc, collection=_GUEST_COLLECTION)
    return doc


@router.post("/pms/guests", response_model=Guest)
async def create_guest(
    guest_data: GuestCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    # Optional Idempotency-Key replay protection: same key returns the original
    # guest object instead of creating a duplicate (e.g. on UI double-submit).
    idem_key = get_idempotency_key(request)
    lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope="guest_create",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            # Cache only stored {id, tenant_id} (no PII); re-fetch the encrypted
            # guest doc, decrypt, and return the same shape the original POST did.
            replay = claim["response"] or {}
            replay_id = replay.get("id")
            if replay_id:
                doc = await db.guests.find_one(
                    {"id": replay_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
                )
                if doc:
                    return _decrypt_guest(doc)
            # Cache pointer is stale (guest was hard-deleted out of band) —
            # fall through to a fresh insert under the same key.
        elif claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        lock_id = claim.get("lock_id")

    try:
        guest = Guest(tenant_id=current_user.tenant_id, **guest_data.model_dump())
        guest_dict = guest.model_dump()
        guest_dict['created_at'] = guest_dict['created_at'].isoformat()
        guest_dict_to_store = _encrypt_guest(guest_dict.copy())
        await db.guests.insert_one(guest_dict_to_store)
        if lock_id:
            # Persist ONLY the guest id + tenant in the idempotency cache to
            # avoid leaking PII outside the encrypted `guests` collection.
            # Replay handler re-fetches & decrypts from `guests` instead.
            await complete_idempotency(
                db,
                lock_id=lock_id,
                response_body={"id": guest.id, "tenant_id": current_user.tenant_id},
            )
        return guest
    except Exception as exc:
        if lock_id:
            await release_idempotency(db, lock_id=lock_id, error=str(exc))
        raise


@router.get("/pms/guests", response_model=list[Guest])
@cached(ttl=300, key_prefix="pms_guests")  # Cache for 5 minutes
async def get_guests(
    p: PaginationParams = Depends(paginate(default_limit=1000, max_limit=5000)),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_guest_list")),  # v71 Bug DH (PII)
):
    limit, offset = p.limit, p.offset
    guests_raw = await db.guests.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).skip(offset).limit(limit).to_list(limit)

    # Map database fields to model fields
    guests = []
    for guest in guests_raw:
        guest = _decrypt_guest(guest)

        # Combine first_name and last_name into name if they exist
        if 'first_name' in guest and 'last_name' in guest:
            guest['name'] = f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
        elif 'name' not in guest:
            guest['name'] = guest.get('email', 'Unknown')

        # Use passport_number as id_number if id_number doesn't exist
        if 'id_number' not in guest and 'passport_number' in guest:
            guest['id_number'] = guest.get('passport_number', '')
        elif 'id_number' not in guest:
            guest['id_number'] = ''

        guests.append(guest)

    return guests


@router.get("/pms/guests/search")
async def search_guests(
    q: str = "",
    p: PaginationParams = Depends(paginate(default_limit=10, max_limit=100)),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    limit = p.limit
    """Misafir arama: ad, e-posta, telefon veya kimlik numarasina gore arar."""
    # Null byte ve diger kontrol karakterlerini temizle (MongoDB regex null byte kabul etmez)
    q = q.replace("\x00", "").strip()
    if not q or len(q) < 2:
        return []
    # DoS guard: cok uzun query string mongo regex compile'i patlatabilir
    if len(q) > 200:
        q = q[:200]

    tenant_id = current_user.tenant_id
    import re as _re
    safe_q = _re.escape(q)
    regex = {"$regex": safe_q, "$options": "i"}

    # Build search conditions supporting both encrypted and plaintext fields
    if _fenc:
        encrypted_conditions = _fenc.build_search_query(
            collection=_GUEST_COLLECTION,
            search_fields=["email", "phone", "id_number", "passport_number"],
            search_value=safe_q,
        )
        name_conditions = [
            {"name": regex},
            {"first_name": regex},
            {"last_name": regex},
        ]
        query = {
            "tenant_id": tenant_id,
            "$or": name_conditions + encrypted_conditions,
        }
    else:
        query = {
            "tenant_id": tenant_id,
            "$or": [
                {"name": regex},
                {"first_name": regex},
                {"last_name": regex},
                {"email": regex},
                {"phone": regex},
                {"id_number": regex},
                {"passport_number": regex},
            ],
        }

    guests_raw = await db.guests.find(query, {"_id": 0}).sort("name", 1).limit(limit).to_list(limit)

    results = []
    for g in guests_raw:
        g = _decrypt_guest(g)
        if "first_name" in g and "last_name" in g:
            g["name"] = f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
        elif "name" not in g:
            g["name"] = g.get("email", "Unknown")
        if "id_number" not in g:
            g["id_number"] = g.get("passport_number", "")
        results.append({
            "id": g.get("id", ""),
            "name": g.get("name", ""),
            "email": g.get("email", ""),
            "phone": g.get("phone", ""),
            "id_number": g.get("id_number", ""),
            "vip_status": g.get("vip_status", False),
            "total_stays": g.get("total_stays", 0),
        })
    return results


@router.get("/pms/guests/{guest_id}")
async def get_guest_by_id(
    guest_id: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    guest = _decrypt_guest(guest)
    if "first_name" in guest and "last_name" in guest:
        guest["name"] = f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
    elif "name" not in guest:
        guest["name"] = guest.get("email", "Unknown")
    if "id_number" not in guest:
        guest["id_number"] = guest.get("passport_number", "")
    return guest


@router.put("/pms/guests/{guest_id}")
async def update_guest(
    guest_id: str,
    data: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    allowed = {
        "name", "email", "phone", "id_type", "id_number",
        "nationality", "date_of_birth", "address", "city",
        "postal_code", "country", "gender", "notes",
        "id_issue_date", "id_expiry_date", "id_issuing_authority",
    }
    update_fields = {k: v for k, v in data.items() if k in allowed}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Guncellenecek alan bulunamadi")

    # Encrypt PII fields in the update
    update_fields = _encrypt_guest(update_fields)

    await db.guests.update_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields},
    )
    updated = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    return _decrypt_guest(updated)


@router.delete("/pms/guests/{guest_id}")
async def delete_guest(
    guest_id: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("manage_sales")),
):
    """Soft-delete a guest record.

    We never hard-delete because guests are referenced by historical bookings,
    folios, and KBS submissions. The record is marked deleted and excluded from
    list/search responses by downstream filters when they choose to honor it.
    Active bookings (confirmed / checked_in / guaranteed) block deletion to
    prevent breaking referential integrity for in-flight stays.
    """
    from datetime import UTC, datetime

    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    active = await db.bookings.count_documents({
        "tenant_id": current_user.tenant_id,
        "guest_id": guest_id,
        "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
    })
    if active > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Aktif {active} rezervasyonu olan misafir silinemez",
        )

    await db.guests.update_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "deleted",
            "deleted_at": datetime.now(UTC).isoformat(),
            "deleted_by": getattr(current_user, "id", None),
        }},
    )
    return {"success": True, "guest_id": guest_id, "soft_deleted": True}
