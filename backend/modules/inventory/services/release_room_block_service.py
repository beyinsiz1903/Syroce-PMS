import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import HTTPException, Request, status

from modules.inventory.events import INVENTORY_RELEASED_EVENT
from modules.inventory.repository import InventoryRepository
from shared_kernel.audit_helper import audit_log
from shared_kernel.event_envelope import build_event_envelope
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

            released_block = {
                **existing_block,
                **update_doc,
            }

            event_envelope = build_event_envelope(
                event_type=INVENTORY_RELEASED_EVENT,
                tenant_id=tenant_context.tenant_id,
                correlation_id=correlation_id,
                payload={
                    "release_scope": {
                        "property_id": property_context.property_id or tenant_context.tenant_id,
                        "room_id": released_block["room_id"],
                        "room_type": room.get("room_type"),
                    },
                    "effective_date_range": {
                        "start_date": released_block.get("start_date"),
                        "end_date": released_block.get("end_date"),
                    },
                    "actor_reference": {
                        "actor_id": current_user.id,
                        "actor_name": current_user.name,
                        "actor_role": tenant_context.role,
                    },
                    "reason": reason or "Released by user",
                    "source": "semantic_inventory_service",
                    "block_type": str(released_block.get("type")),
                    "allow_sell": released_block.get("allow_sell", False),
                },
            ).model_dump()
            outbox_doc = {
                **event_envelope,
                "property_id": property_context.property_id or tenant_context.tenant_id,
                "room_block_id": released_block["id"],
                "released_at": released_at,
                "status": "pending",
                "created_at": event_envelope["timestamp"],
            }
            await self.repository.insert_outbox_event(outbox_doc)

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