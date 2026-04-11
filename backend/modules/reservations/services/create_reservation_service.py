import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from core.utils import generate_folio_number, generate_qr_code, generate_time_based_qr_token
from models.enums import FolioType
from models.schemas import BookingCreate, Folio, RateOverrideLog
from modules.reservations.repository import ReservationsRepository
from shared_kernel.audit_helper import audit_log
from shared_kernel.idempotency import ensure_idempotent_request
from shared_kernel.tenancy_context import build_property_context, build_tenant_context


class CreateReservationService:
    def __init__(self, repository: Optional[ReservationsRepository] = None):
        self.repository = repository or ReservationsRepository()

    async def create(self, booking_data: BookingCreate, current_user, request: Request) -> Dict[str, Any]:
        tenant_context = build_tenant_context(current_user, request)
        property_context = build_property_context(current_user, request)
        self._enforce_property_scope(tenant_context.tenant_id, property_context.property_id)

        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        idempotency_key = ensure_idempotent_request(request, required=True)
        request_hash = self._build_request_hash(tenant_context.tenant_id, booking_data)

        lock = await self.repository.acquire_idempotency_lock(
            tenant_id=tenant_context.tenant_id,
            scope="reservation.create",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            correlation_id=correlation_id,
        )

        if lock["status"] == "existing":
            existing = lock["document"]
            if existing.get("request_hash") != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used with a different payload",
                )
            if existing.get("status") == "completed" and existing.get("response_body"):
                return existing["response_body"]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation create request is already in progress",
            )

        try:
            room = await self.repository.get_room_for_tenant(tenant_context.tenant_id, booking_data.room_id)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            guest = await self.repository.get_guest_for_tenant(tenant_context.tenant_id, booking_data.guest_id)
            if not guest:
                raise HTTPException(status_code=404, detail="Guest not found")

            check_in_dt = datetime.fromisoformat(booking_data.check_in.replace('Z', '+00:00'))
            check_out_dt = datetime.fromisoformat(booking_data.check_out.replace('Z', '+00:00'))

            # Geçmiş tarih kontrolü — bugün veya business_date'den hangisi ilerdeyse onu kullan
            from core.database import db as _db
            tenant_settings = await _db.tenant_settings.find_one(
                {"tenant_id": tenant_context.tenant_id}, {"_id": 0}
            )
            business_date_str = (tenant_settings or {}).get(
                "business_date", datetime.now(timezone.utc).date().isoformat()
            )
            today_str = datetime.now(timezone.utc).date().isoformat()
            effective_min_date = max(business_date_str, today_str)
            effective_min_dt = datetime.fromisoformat(effective_min_date + "T00:00:00+00:00")
            if check_in_dt.replace(tzinfo=timezone.utc) < effective_min_dt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Gecmis tarihe rezervasyon yapilamaz (minimum: {effective_min_date})"
                )

            booking_id = str(uuid.uuid4())
            now_ts = datetime.now(timezone.utc)

            booking_dict = {
                'id': booking_id,
                'tenant_id': tenant_context.tenant_id,
                'guest_id': booking_data.guest_id,
                'room_id': booking_data.room_id,
                'check_in': check_in_dt.isoformat(),
                'check_out': check_out_dt.isoformat(),
                'adults': booking_data.adults,
                'children': booking_data.children,
                'children_ages': booking_data.children_ages,
                'guests_count': booking_data.guests_count,
                'total_amount': booking_data.total_amount,
                'base_rate': booking_data.base_rate,
                'paid_amount': 0.0,
                'status': getattr(booking_data, 'status', None) or 'confirmed',
                'channel': booking_data.channel.value if booking_data.channel else 'direct',
                'rate_plan': booking_data.rate_plan or 'Standard',
                'special_requests': booking_data.special_requests,
                'source_channel': booking_data.source_channel or 'direct',
                'origin': booking_data.origin or 'ui',
                'hold_status': booking_data.hold_status or 'none',
                'allocation_source': booking_data.allocation_source or 'manual',
                'company_id': booking_data.company_id,
                'contracted_rate': booking_data.contracted_rate.value if booking_data.contracted_rate else None,
                'rate_type': booking_data.rate_type.value if booking_data.rate_type else None,
                'market_segment': booking_data.market_segment.value if booking_data.market_segment else None,
                'cancellation_policy': booking_data.cancellation_policy.value if booking_data.cancellation_policy else None,
                'billing_address': booking_data.billing_address,
                'billing_tax_number': booking_data.billing_tax_number,
                'billing_contact_person': booking_data.billing_contact_person,
                'ota_channel': booking_data.ota_channel.value if booking_data.ota_channel else None,
                'ota_confirmation': booking_data.ota_confirmation,
                'ota_reference_id': booking_data.ota_reference_id,
                'commission_pct': booking_data.commission_pct,
                'created_at': now_ts.isoformat(),
                '_version': 1,
            }

            if booking_data.base_rate and booking_data.base_rate != booking_data.total_amount and booking_data.override_reason:
                override_log = RateOverrideLog(
                    tenant_id=tenant_context.tenant_id,
                    booking_id=booking_id,
                    user_id=current_user.id,
                    user_name=current_user.name,
                    base_rate=booking_data.base_rate,
                    new_rate=booking_data.total_amount,
                    override_reason=booking_data.override_reason,
                )
                override_dict = override_log.model_dump()
                override_dict['timestamp'] = override_dict['timestamp'].isoformat()
                await self.repository.insert_rate_override_log(override_dict)

            qr_token = generate_time_based_qr_token(booking_id, expiry_hours=72)
            qr_data = f"booking:{booking_id}:token:{qr_token}"
            booking_dict['qr_code'] = generate_qr_code(qr_data)
            booking_dict['qr_code_data'] = qr_token

            await self.repository.insert_booking(booking_dict)

            folio_number = await generate_folio_number(tenant_context.tenant_id)
            folio = Folio(
                tenant_id=tenant_context.tenant_id,
                booking_id=booking_id,
                folio_number=folio_number,
                folio_type=FolioType.GUEST,
                guest_id=booking_data.guest_id,
            )
            folio_dict = folio.model_dump()
            folio_dict['created_at'] = folio_dict['created_at'].isoformat()
            await self.repository.insert_folio(folio_dict)

            # OTA-002: Enqueue outbox event for guaranteed delivery
            # No more fire-and-forget cm_push_event — the outbox worker handles dispatch
            from core.outbox_service import enqueue_outbox_event, BOOKING_CREATED
            from core.database import db as _outbox_db

            await enqueue_outbox_event(
                _outbox_db,
                tenant_id=tenant_context.tenant_id,
                event_type=BOOKING_CREATED,
                entity_type="booking",
                entity_id=booking_id,
                property_id=property_context.property_id or tenant_context.tenant_id,
                correlation_id=correlation_id,
                payload={
                    "booking_id": booking_id,
                    "guest_id": booking_data.guest_id,
                    "room_id": booking_data.room_id,
                    "check_in": booking_dict['check_in'],
                    "check_out": booking_dict['check_out'],
                    "status": booking_dict.get('status', 'confirmed'),
                    "property_id": property_context.property_id or tenant_context.tenant_id,
                    "source_channel": booking_data.source_channel or "direct",
                    "origin": booking_data.origin or "ui",
                },
            )

            await audit_log(
                actor_id=current_user.id,
                tenant_id=tenant_context.tenant_id,
                property_id=property_context.property_id or tenant_context.tenant_id,
                entity_type="reservation",
                entity_id=booking_id,
                action="reservation_created",
                correlation_id=correlation_id,
                metadata={
                    "room_id": booking_data.room_id,
                    "guest_id": booking_data.guest_id,
                    "check_in": booking_dict['check_in'],
                    "check_out": booking_dict['check_out'],
                },
            )

            # Usage metering
            try:
                from core.metering import record_usage, UsageEventType
                await record_usage(tenant_context.tenant_id, UsageEventType.RESERVATION_CREATED)
            except Exception:
                pass

            # Channel availability auto-sync: arka planda müsaitlik güncelle ve kanallara push et
            try:
                from domains.channel_manager.availability_auto_sync import sync_availability_after_booking
                import asyncio
                asyncio.create_task(sync_availability_after_booking(
                    tenant_id=tenant_context.tenant_id,
                    room_id=booking_data.room_id,
                    check_in=booking_dict['check_in'],
                    check_out=booking_dict['check_out'],
                ))
            except Exception:
                pass

            response_body = dict(booking_dict)
            response_body.pop('_id', None)
            await self.repository.complete_idempotency_lock(lock["lock_id"], booking_id, response_body)
            return response_body
        except HTTPException as exc:
            await self.repository.fail_idempotency_lock(lock["lock_id"], exc.detail if isinstance(exc.detail, str) else str(exc.detail))
            raise
        except Exception as exc:
            from core.atomic_booking import BookingConflictError
            if isinstance(exc, BookingConflictError):
                await self.repository.fail_idempotency_lock(lock["lock_id"], str(exc))
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
            await self.repository.fail_idempotency_lock(lock["lock_id"], str(exc))
            raise

    def _build_request_hash(self, tenant_id: str, booking_data: BookingCreate) -> str:
        payload = booking_data.model_dump(mode="json")
        serialized = json.dumps({"tenant_id": tenant_id, "payload": payload}, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _enforce_property_scope(self, tenant_id: str, property_id: Optional[str]) -> None:
        if property_id and property_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Property scope mismatch",
            )