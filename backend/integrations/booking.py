import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from celery_app import celery_app
from models.schemas import Booking, BookingCreate, Guest, GuestCreate, OTAReservation, User
from models.enums import ChannelType
from core.database import db
from core.security import get_current_user


class BookingCredentialManager:
    @staticmethod
    async def upsert_credentials(
        tenant_id: str,
        property_id: str,
        username: str,
        password: str,
        settings: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "provider": "booking",
            "property_id": property_id,
            "username": username,
            "password": password,
            "settings": settings or {},
            "updated_at": datetime.now(UTC).isoformat()
        }

        await db.ota_credentials.update_one(
            {"tenant_id": tenant_id, "provider": "booking"},
            {"$set": record},
            upsert=True
        )
        record.pop("_id", None)
        return record

    @staticmethod
    async def get_credentials(tenant_id: str) -> dict[str, Any] | None:
        doc = await db.ota_credentials.find_one(
            {"tenant_id": tenant_id, "provider": "booking"},
            {"_id": 0}
        )
        return doc


class BookingPayloadBuilder:
    def __init__(self, tenant_id: str, credentials: dict[str, Any]):
        self.tenant_id = tenant_id
        self.credentials = credentials

    def build_rate_payload(self, rooms: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "property_id": self.credentials.get("property_id"),
            "rooms": [
                {
                    "room_code": r["room_code"],
                    "rate_plan": r["rate_plan"],
                    "date": r["date"],
                    "price": r["price"],
                    "currency": r.get("currency", "EUR"),
                    "min_stay": r.get("min_stay", 1),
                    "closed": r.get("closed", False),
                }
                for r in rooms
            ],
        }


class BookingIntegrationLogger:
    @staticmethod
    async def log_event(tenant_id: str, event_type: str, payload: dict[str, Any], status: str, message: str | None = None):
        record = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "provider": "booking",
            "event_type": event_type,
            "payload": payload,
            "status": status,
            "message": message,
            "created_at": datetime.now(UTC).isoformat()
        }
        await db.booking_integration_logs.insert_one(record)


class BookingAPIClient:
    def __init__(self, credentials: dict[str, Any]):
        self.credentials = credentials
        settings = credentials.get("settings", {}) or {}
        self.base_url = settings.get("base_url", "https://distribution.booking.com")
        self.timeout = settings.get("timeout_seconds", 10)
        self.username = credentials.get("username")
        self.password = credentials.get("password")

    async def push_ari(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = f"{self.base_url}/json/bookings"
        async with httpx.AsyncClient(timeout=self.timeout, auth=(self.username, self.password)) as client:
            response = await client.post(endpoint, json={"roomRates": payload.get("rooms", [])})
            response.raise_for_status()
            result = response.json()
            return {
                "success": True,
                "endpoint": endpoint,
                "raw": result
            }

    async def fetch_reservations(self, modified_since: str | None = None) -> dict[str, Any]:
        endpoint = f"{self.base_url}/json/reservations"
        params = {}
        if modified_since:
            params["modified_since"] = modified_since

        async with httpx.AsyncClient(timeout=self.timeout, auth=(self.username, self.password)) as client:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()

        reservations = []
        for item in data.get("reservations", []):
            stay = item.get("dates", {})
            guest = item.get("guest", {})
            counts = item.get("guest_counts", {})
            reservations.append({
                "id": item.get("id"),
                "guest_name": guest.get("name"),
                "guest_email": guest.get("email"),
                "guest_phone": guest.get("phone"),
                "room_code": item.get("room", {}).get("code"),
                "check_in": stay.get("arrival"),
                "check_out": stay.get("departure"),
                "status": item.get("status"),
                "total_amount": item.get("pricing", {}).get("total"),
                "currency": item.get("pricing", {}).get("currency"),
                "adults": counts.get("adults"),
                "children": counts.get("children"),
                "commission_amount": item.get("pricing", {}).get("commission")
            })

        return {
            "success": True,
            "reservations": reservations,
            "endpoint": endpoint
        }

class BookingReservationMapper:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def to_ota_record(self, reservation: dict[str, Any]) -> dict[str, Any]:
        adults = reservation.get("adults", 2)
        children = reservation.get("children", 0)
        ota_res = OTAReservation(
            tenant_id=self.tenant_id,
            channel_type=ChannelType.BOOKING_COM,
            channel_booking_id=reservation.get("id"),
            guest_name=reservation.get("guest_name") or "Booking Guest",
            guest_email=reservation.get("guest_email"),
            guest_phone=reservation.get("guest_phone"),
            room_type=reservation.get("room_code", "standard"),
            check_in=reservation.get("check_in"),
            check_out=reservation.get("check_out"),
            adults=adults,
            children=children,
            total_amount=reservation.get("total_amount", 0.0),
            commission_amount=reservation.get("commission_amount"),
            status=reservation.get("status", "pending"),
            raw_data=reservation
        )
        data = ota_res.model_dump()
        data['channel_type'] = data['channel_type'].value
        data['received_at'] = data['received_at'].isoformat()
        if data.get('processed_at'):
            data['processed_at'] = data['processed_at'].isoformat()
        return data

    def to_booking_payload(self, reservation: dict[str, Any], guest_id: str, room_id: str) -> dict[str, Any]:
        booking_create = BookingCreate(
            guest_id=guest_id,
            room_id=room_id,
            check_in=reservation.get("check_in"),
            check_out=reservation.get("check_out"),
            adults=reservation.get("adults") or 2,
            children=reservation.get("children") or 0,
            guests_count=(reservation.get("adults") or 2) + (reservation.get("children") or 0),
            total_amount=reservation.get("total_amount") or 0,
            channel=ChannelType.BOOKING_COM
        )
        booking = Booking(
            tenant_id=self.tenant_id,
            **booking_create.model_dump(exclude={'check_in', 'check_out'}),
            check_in=datetime.fromisoformat(reservation.get("check_in")),
            check_out=datetime.fromisoformat(reservation.get("check_out"))
        )
        data = booking.model_dump()
        data['check_in'] = data['check_in'].isoformat()
        data['check_out'] = data['check_out'].isoformat()
        data['created_at'] = data['created_at'].isoformat()
        return data

    def to_guest_payload(self, reservation: dict[str, Any]) -> dict[str, Any]:
        guest_create = GuestCreate(
            name=reservation.get("guest_name") or "Booking Guest",
            email=reservation.get("guest_email") or f"{reservation.get('id')}@booking.com",
            phone=reservation.get("guest_phone") or "",
            id_number=f"BOOK-{reservation.get('id')}"
        )
        guest = Guest(
            tenant_id=self.tenant_id,
            **guest_create.model_dump()
        )
        data = guest.model_dump()
        data['created_at'] = data['created_at'].isoformat()
        return data

booking_router = APIRouter(prefix="/booking", tags=["booking-integrations"])

class RoomRate(BaseModel):
    room_code: str
    rate_plan: str
    date: str
    price: float
    currency: str = "EUR"
    min_stay: int = 1
    closed: bool = False


class BookingPushRequest(BaseModel):
    rooms: list[RoomRate]


@booking_router.post("/credentials")
async def upsert_booking_credentials(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    required = ['property_id', 'username', 'password']
    if not all(field in payload for field in required):
        raise HTTPException(status_code=400, detail="property_id, username, password required")
    record = await BookingCredentialManager.upsert_credentials(
        tenant_id=current_user.tenant_id,
        property_id=payload['property_id'],
        username=payload['username'],
        password=payload['password'],
        settings=payload.get('settings')
    )
    return {"success": True, "credentials": record}

@booking_router.get("/credentials")
async def get_booking_credentials(current_user: User = Depends(get_current_user)):
    creds = await BookingCredentialManager.get_credentials(current_user.tenant_id)
    if not creds:
        raise HTTPException(status_code=404, detail="Booking.com credentials not found")
    return creds

@booking_router.post("/ari/push")
async def trigger_booking_ari_push(
    payload: BookingPushRequest,
    current_user: User = Depends(get_current_user)
):
    credentials = await BookingCredentialManager.get_credentials(current_user.tenant_id)
    if not credentials:
        raise HTTPException(status_code=400, detail="Booking.com credentials missing")

    builder = BookingPayloadBuilder(current_user.tenant_id, credentials)
    push_payload = builder.build_rate_payload([room.model_dump() for room in payload.rooms])

    celery_app.send_task('celery_tasks.booking_push_task', args=[current_user.tenant_id, push_payload])
    await BookingIntegrationLogger.log_event(
        current_user.tenant_id,
        'ari_push',
        push_payload,
        'queued',
        message='Booking.com ARI push queued'
    )
    return {"success": True, "queued": True}

@booking_router.post("/reservations/pull")
async def trigger_booking_reservation_pull(
    current_user: User = Depends(get_current_user)
):
    credentials = await BookingCredentialManager.get_credentials(current_user.tenant_id)
    if not credentials:
        raise HTTPException(status_code=400, detail="Booking.com credentials missing")

    celery_app.send_task('celery_tasks.booking_pull_task', args=[current_user.tenant_id])
    await BookingIntegrationLogger.log_event(
        current_user.tenant_id,
        'reservation_pull',
        {"tenant_id": current_user.tenant_id},
        'queued',
        message='Booking.com reservation pull queued'
    )
    return {"success": True, "queued": True}

@booking_router.get("/logs")
async def list_booking_logs(limit: int = 20, current_user: User = Depends(get_current_user)):
    cursor = db.booking_integration_logs.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('created_at', -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"items": items, "count": len(items)}

