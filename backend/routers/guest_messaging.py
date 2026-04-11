"""
Guest Messaging Router - Misafir Mesajlaşma Sistemi
Misafirlerin otel ile mesajlaşmasını sağlar.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel

router = APIRouter(prefix="/api/guest/messages", tags=["guest-messaging"])

_db = None
_get_current_user = None


def init_guest_messaging(db, get_current_user_dep):
    global _db, _get_current_user
    _db = db
    _get_current_user = get_current_user_dep


class SendMessageRequest(BaseModel):
    booking_id: str | None = None
    message: str
    message_type: str | None = "general"  # general, request, complaint, feedback


class ReplyMessageRequest(BaseModel):
    message: str


@router.get("")
async def get_guest_messages(
    booking_id: str | None = None,
    credentials=Depends(HTTPBearer())
):
    """Misafirin mesajlarını listele."""
    current_user = await _get_current_user(credentials)


    if current_user.role == "guest":
        query_filter = {
            "tenant_id": current_user.tenant_id,
            "guest_user_id": current_user.id
        }
    else:
        query_filter = {"tenant_id": current_user.tenant_id}
        if booking_id:
            query_filter["booking_id"] = booking_id

    messages = await _db.guest_messages.find(
        query_filter,
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    # Group by conversation (booking_id or guest_user_id)
    conversations = {}
    for msg in messages:
        conv_key = msg.get("booking_id") or msg.get("guest_user_id", "unknown")
        if conv_key not in conversations:
            conversations[conv_key] = {
                "booking_id": msg.get("booking_id"),
                "guest_name": msg.get("guest_name", "Misafir"),
                "guest_user_id": msg.get("guest_user_id"),
                "room_number": msg.get("room_number"),
                "messages": [],
                "unread_count": 0,
                "last_message_at": msg.get("created_at"),
            }
        conversations[conv_key]["messages"].append(msg)
        if not msg.get("read") and msg.get("sender") == "guest":
            conversations[conv_key]["unread_count"] += 1

    return {
        "conversations": list(conversations.values()),
        "total_messages": len(messages),
        "unread_total": sum(c["unread_count"] for c in conversations.values()),
    }


@router.post("")
async def send_guest_message(
    req: SendMessageRequest,
    credentials=Depends(HTTPBearer())
):
    """Misafir mesajı gönder."""
    current_user = await _get_current_user(credentials)

    # Determine sender type
    is_guest = current_user.role == "guest"

    # Get guest info if staff is sending
    guest_name = getattr(current_user, 'name', 'Misafir')
    room_number = None

    if req.booking_id:
        booking = await _db.bookings.find_one(
            {"id": req.booking_id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        if booking:
            guest_name = booking.get("guest_name", guest_name)
            room_number = booking.get("room_number")

    msg_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "booking_id": req.booking_id,
        "guest_user_id": current_user.id if is_guest else None,
        "guest_name": guest_name,
        "room_number": room_number,
        "sender": "guest" if is_guest else "staff",
        "sender_name": getattr(current_user, 'name', 'Bilinmeyen'),
        "sender_id": current_user.id,
        "message": req.message,
        "message_type": req.message_type,
        "read": False,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await _db.guest_messages.insert_one(msg_doc)
    msg_doc.pop("_id", None)

    return msg_doc


@router.post("/{message_id}/reply")
async def reply_to_message(
    message_id: str,
    req: ReplyMessageRequest,
    credentials=Depends(HTTPBearer())
):
    """Mesaja yanıt ver."""
    current_user = await _get_current_user(credentials)

    original = await _db.guest_messages.find_one(
        {"id": message_id, "tenant_id": current_user.tenant_id},
        {"_id": 0}
    )
    if not original:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")

    is_guest = current_user.role == "guest"

    reply_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "booking_id": original.get("booking_id"),
        "guest_user_id": original.get("guest_user_id"),
        "guest_name": original.get("guest_name"),
        "room_number": original.get("room_number"),
        "sender": "guest" if is_guest else "staff",
        "sender_name": getattr(current_user, 'name', 'Bilinmeyen'),
        "sender_id": current_user.id,
        "message": req.message,
        "message_type": original.get("message_type", "general"),
        "reply_to": message_id,
        "read": False,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await _db.guest_messages.insert_one(reply_doc)
    reply_doc.pop("_id", None)

    return reply_doc


@router.put("/{message_id}/read")
async def mark_message_read(
    message_id: str,
    credentials=Depends(HTTPBearer())
):
    """Mesajı okundu olarak işaretle."""
    current_user = await _get_current_user(credentials)

    await _db.guest_messages.update_one(
        {"id": message_id, "tenant_id": current_user.tenant_id},
        {"$set": {"read": True, "read_at": datetime.now(UTC).isoformat()}}
    )
    return {"message": "Okundu olarak işaretlendi"}


@router.put("/mark-all-read")
async def mark_all_read(
    booking_id: str | None = None,
    credentials=Depends(HTTPBearer())
):
    """Tüm mesajları okundu işaretle."""
    current_user = await _get_current_user(credentials)

    query = {"tenant_id": current_user.tenant_id, "read": False}
    if booking_id:
        query["booking_id"] = booking_id
    if current_user.role == "guest":
        query["sender"] = "staff"
    else:
        query["sender"] = "guest"

    result = await _db.guest_messages.update_many(query, {
        "$set": {"read": True, "read_at": datetime.now(UTC).isoformat()}
    })

    return {"marked_read": result.modified_count}


@router.get("/unread-count")
async def get_unread_count(credentials=Depends(HTTPBearer())):
    """Okunmamış mesaj sayısı."""
    current_user = await _get_current_user(credentials)

    query = {"tenant_id": current_user.tenant_id, "read": False}
    if current_user.role == "guest":
        query["sender"] = "staff"
    else:
        query["sender"] = "guest"

    count = await _db.guest_messages.count_documents(query)
    return {"unread_count": count}
