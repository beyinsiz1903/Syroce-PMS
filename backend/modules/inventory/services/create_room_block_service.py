import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import HTTPException, Request, status

from modules.inventory.events import INVENTORY_BLOCKED_EVENT
from modules.inventory.repository import InventoryRepository
from room_block_models import BlockStatus, RoomBlock, RoomBlockCreate
from shared_kernel.audit_helper import audit_log
from shared_kernel.event_envelope import build_event_envelope
from shared_kernel.idempotency import ensure_idempotent_request
from shared_kernel.tenancy_context import build_property_context, build_tenant_context


class CreateRoomBlockService:
    def __init__(self, repository: Optional[InventoryRepository] = None):
        self.repository = repository or InventoryRepository()

    async def create(self, block_data: RoomBlockCreate, current_user, request: Request) -> Dict:
        tenant_context = build_tenant_context(current_user, request)
        property_context = build_property_context(current_user, request)
        self._enforce_property_scope(tenant_context.tenant_id, property_context.property_id)

        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        idempotency_key = ensure_idempotent_request(request, required=True)
        request_hash = self._build_request_hash(tenant_context.tenant_id, block_data)

        lock = await self.repository.acquire_idempotency_lock(
            tenant_id=tenant_context.tenant_id,
            scope="inventory.room_block.create",
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
                detail="Room block create request is already in progress",
            )

        try:
            room = await self.repository.get_room_for_tenant(tenant_context.tenant_id, block_data.room_id)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            start_date = datetime.fromisoformat(block_data.start_date).date()
            end_date = datetime.fromisoformat(block_data.end_date).date() if block_data.end_date else None
            if end_date and end_date < start_date:
                raise HTTPException(status_code=400, detail="End date must be after start date")

            conflicting_bookings = await self.repository.list_conflicting_bookings(
                tenant_id=tenant_context.tenant_id,
                room_id=block_data.room_id,
                start_date=block_data.start_date,
                end_date=block_data.end_date,
            )

            block = RoomBlock(
                id=str(uuid.uuid4()),
                room_id=block_data.room_id,
                type=block_data.type,
                reason=block_data.reason,
                details=block_data.details,
                start_date=block_data.start_date,
                end_date=block_data.end_date,
                allow_sell=block_data.allow_sell,
                created_by=current_user.id,
                created_at=datetime.now(timezone.utc).isoformat(),
                status=BlockStatus.ACTIVE,
            )
            block_dict = block.model_dump()
            block_with_tenant = {**block_dict, 'tenant_id': tenant_context.tenant_id}
            await self.repository.insert_room_block(block_with_tenant)

            if conflicting_bookings and not block_data.allow_sell:
                for booking in conflicting_bookings:
                    await self.repository.insert_exception({
                        'id': str(uuid.uuid4()),
                        'tenant_id': tenant_context.tenant_id,
                        'exception_type': 'room_blocked_with_reservation',
                        'entity_type': 'booking',
                        'entity_id': booking['id'],
                        'severity': 'high',
                        'message': f"Room {room['room_number']} blocked ({block.type}) but has active reservation",
                        'details': {
                            'room_id': block_data.room_id,
                            'room_number': room['room_number'],
                            'block_id': block.id,
                            'block_type': block.type.value,
                            'block_reason': block.reason,
                            'booking_id': booking['id'],
                            'guest_name': booking.get('guest_name', 'Unknown'),
                            'check_in': booking['check_in'],
                            'check_out': booking['check_out'],
                        },
                        'status': 'pending',
                        'created_at': datetime.now(timezone.utc).isoformat(),
                    })

            event_envelope = build_event_envelope(
                event_type=INVENTORY_BLOCKED_EVENT,
                tenant_id=tenant_context.tenant_id,
                correlation_id=correlation_id,
                payload={
                    'room_block_id': block.id,
                    'room_id': block.room_id,
                    'block_type': block.type.value,
                    'start_date': block.start_date,
                    'end_date': block.end_date,
                    'allow_sell': block.allow_sell,
                    'source': 'semantic_inventory_service',
                },
            ).model_dump()
            outbox_doc = {
                **event_envelope,
                'property_id': property_context.property_id or tenant_context.tenant_id,
                'room_block_id': block.id,
                'status': 'pending',
                'created_at': event_envelope['timestamp'],
            }
            await self.repository.insert_outbox_event(outbox_doc)

            await audit_log(
                actor_id=current_user.id,
                tenant_id=tenant_context.tenant_id,
                property_id=property_context.property_id or tenant_context.tenant_id,
                entity_type='room_block',
                entity_id=block.id,
                action='room_block_created',
                correlation_id=correlation_id,
                metadata={
                    'room_id': block.room_id,
                    'type': block.type.value,
                    'reason': block.reason,
                    'start_date': block.start_date,
                    'end_date': block.end_date,
                    'allow_sell': block.allow_sell,
                },
            )

            response = {
                'message': 'Room block created successfully',
                'block': block_dict,
                'room_number': room['room_number'],
                'warnings': [],
            }
            if conflicting_bookings and not block_data.allow_sell:
                response['warnings'].append({
                    'type': 'conflicting_reservations',
                    'count': len(conflicting_bookings),
                    'message': f"{len(conflicting_bookings)} active reservation(s) conflict with this block. Move or cancel required.",
                })

            await self.repository.complete_idempotency_lock(lock['lock_id'], block.id, response)
            return response
        except HTTPException as exc:
            await self.repository.fail_idempotency_lock(lock['lock_id'], exc.detail if isinstance(exc.detail, str) else str(exc.detail))
            raise
        except Exception as exc:
            await self.repository.fail_idempotency_lock(lock['lock_id'], str(exc))
            raise

    def _build_request_hash(self, tenant_id: str, block_data: RoomBlockCreate) -> str:
        payload = block_data.model_dump(mode='json')
        serialized = json.dumps({'tenant_id': tenant_id, 'payload': payload}, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    def _enforce_property_scope(self, tenant_id: str, property_id: Optional[str]) -> None:
        if property_id and property_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Property scope mismatch',
            )