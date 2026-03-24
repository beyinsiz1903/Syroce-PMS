import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import HTTPException, Request, status

from modules.inventory.repository import InventoryRepository
from shared_kernel.audit_helper import audit_log
from shared_kernel.idempotency import ensure_idempotent_request
from shared_kernel.tenancy_context import build_property_context, build_tenant_context


class ReleaseRoomBlockService:
    def __init__(self, repository: Optional[InventoryRepository] = None):
        self.repository = repository or InventoryRepository()

    async def release(
        self,
        block_id: str,
        current_user,
        request: Request,
        reason: Optional[str] = None,
    ) -> Dict:
        tenant_context = build_tenant_context(current_user, request)
        property_context = build_property_context(current_user, request)
        self._enforce_property_scope(tenant_context.tenant_id, property_context.property_id)

        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        idempotency_key = ensure_idempotent_request(request, required=True)
        request_hash = self._build_request_hash(tenant_context.tenant_id, block_id, reason)

        lock = await self.repository.acquire_idempotency_lock(
            tenant_id=tenant_context.tenant_id,
            scope="inventory.room_block.release",
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
                detail="Room block release request is already in progress",
            )

        try:
            existing_block = await self.repository.get_room_block_for_tenant(tenant_context.tenant_id, block_id)
            if not existing_block:
                raise HTTPException(status_code=404, detail="Block not found")

            room = await self.repository.get_room_for_tenant(tenant_context.tenant_id, existing_block["room_id"])
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            if existing_block.get("status") == "released":
                response = self._build_response(
                    block=existing_block,
                    room=room,
                    property_id=property_context.property_id or tenant_context.tenant_id,
                    correlation_id=correlation_id,
                )
                await self.repository.complete_idempotency_lock(lock["lock_id"], block_id, response)
                return response

            if existing_block.get("status") == "cancelled":
                raise HTTPException(status_code=400, detail="Block already cancelled")

            if existing_block.get("status") == "expired":
                raise HTTPException(status_code=400, detail="Block already expired")

            released_at = datetime.now(timezone.utc).isoformat()
            update_doc = {
                "status": "released",
                "released_at": released_at,
                "released_by": current_user.id,
                "release_reason": reason or "Released by user",
                "release_correlation_id": correlation_id,
            }
            await self.repository.update_room_block(tenant_context.tenant_id, block_id, update_doc)

            # INV-5: Also release from room_night_locks (single source of truth)
            block_type_map = {
                "out_of_order": "ooo",
                "out_of_service": "oos",
                "maintenance": "maintenance",
            }
            lock_block_type = block_type_map.get(
                str(existing_block.get("type", "out_of_order")), "ooo"
            )
            try:
                from core.atomic_booking import release_room_block as release_lock
                await release_lock(
                    tenant_id=tenant_context.tenant_id,
                    room_id=existing_block["room_id"],
                    block_type=lock_block_type,
                    start_date=existing_block.get("start_date"),
                    end_date=existing_block.get("end_date"),
                    actor=current_user.id,
                )
            except Exception as exc:
                import logging
                logging.getLogger("inventory.release_room_block").warning(
                    "room_night_locks release failed for block %s: %s", block_id, exc
                )

            released_block = {
                **existing_block,
                **update_doc,
            }

            # OTA-002: Enqueue outbox event for guaranteed OTA delivery
            from core.database import db as _outbox_db
            from core.outbox_service import INVENTORY_RELEASED, enqueue_outbox_event

            await enqueue_outbox_event(
                _outbox_db,
                tenant_id=tenant_context.tenant_id,
                event_type=INVENTORY_RELEASED,
                entity_type="room_block",
                entity_id=released_block["id"],
                property_id=property_context.property_id or tenant_context.tenant_id,
                correlation_id=correlation_id,
                payload={
                    "room_block_id": released_block["id"],
                    "room_id": released_block["room_id"],
                    "room_type": room.get("room_type"),
                    "start_date": released_block.get("start_date"),
                    "end_date": released_block.get("end_date"),
                    "date_start": released_block.get("start_date"),
                    "date_end": released_block.get("end_date"),
                    "property_id": property_context.property_id or tenant_context.tenant_id,
                    "block_type": str(released_block.get("type")),
                    "allow_sell": released_block.get("allow_sell", False),
                    "reason": reason or "Released by user",
                },
            )

            await audit_log(
                actor_id=current_user.id,
                tenant_id=tenant_context.tenant_id,
                property_id=property_context.property_id or tenant_context.tenant_id,
                entity_type="room_block",
                entity_id=released_block["id"],
                action="room_block_released",
                correlation_id=correlation_id,
                metadata={
                    "room_id": released_block["room_id"],
                    "room_type": room.get("room_type"),
                    "release_reason": reason or "Released by user",
                    "start_date": released_block.get("start_date"),
                    "end_date": released_block.get("end_date"),
                },
            )

            response = self._build_response(
                block=released_block,
                room=room,
                property_id=property_context.property_id or tenant_context.tenant_id,
                correlation_id=correlation_id,
            )
            await self.repository.complete_idempotency_lock(lock["lock_id"], block_id, response)
            return response
        except HTTPException as exc:
            await self.repository.fail_idempotency_lock(lock["lock_id"], exc.detail if isinstance(exc.detail, str) else str(exc.detail))
            raise
        except Exception as exc:
            await self.repository.fail_idempotency_lock(lock["lock_id"], str(exc))
            raise

    def _build_request_hash(self, tenant_id: str, block_id: str, reason: Optional[str]) -> str:
        serialized = json.dumps(
            {
                "tenant_id": tenant_id,
                "block_id": block_id,
                "reason": reason or "",
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _build_response(self, block: Dict, room: Dict, property_id: str, correlation_id: str) -> Dict:
        released_at = block.get("released_at") or block.get("cancelled_at")
        return {
            "message": "Block cancelled successfully",
            "block_id": block["id"],
            "room_block_id": block["id"],
            "status": block.get("status", "released"),
            "released_at": released_at,
            "property_id": property_id,
            "room_id": block.get("room_id"),
            "room_type": room.get("room_type"),
            "correlation_id": block.get("release_correlation_id") or correlation_id,
        }

    def _enforce_property_scope(self, tenant_id: str, property_id: Optional[str]) -> None:
        if property_id and property_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Property scope mismatch",
            )