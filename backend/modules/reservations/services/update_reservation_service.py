import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status

from modules.reservations.events import RESERVATION_MODIFIED_EVENT
from modules.reservations.repository import ReservationsRepository
from shared_kernel.audit_helper import audit_log
from shared_kernel.event_envelope import build_event_envelope
from shared_kernel.idempotency import ensure_idempotent_request
from shared_kernel.tenancy_context import build_property_context, build_tenant_context

DEFAULT_EMPTY_FIELDS = {
    "source_channel": "direct",
    "origin": "ui",
    "hold_status": "none",
    "allocation_source": "manual",
}

ALLOWED_FIELDS = {
    "room_id",
    "guest_id",
    "total_amount",
    "status",
    "adults",
    "children",
    "check_in",
    "check_out",
    "special_requests",
    "company_id",
    "rate_plan",
    "source_channel",
    "origin",
    "hold_status",
    "allocation_source",
    "children_ages",
    "guests_count",
    "contracted_rate",
    "rate_type",
    "market_segment",
}


class UpdateReservationService:
    def __init__(self, repository: ReservationsRepository | None = None):
        self.repository = repository or ReservationsRepository()

    async def update(
        self,
        booking_id: str,
        booking_data: dict[str, Any],
        current_user,
        request: Request,
    ) -> dict[str, Any]:
        tenant_context = build_tenant_context(current_user, request)
        property_context = build_property_context(current_user, request)
        self._enforce_property_scope(tenant_context.tenant_id, property_context.property_id)

        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        idempotency_key = ensure_idempotent_request(request, required=True)
        normalized_payload = self._normalize_payload(booking_data)
        request_hash = self._build_request_hash(tenant_context.tenant_id, booking_id, normalized_payload)

        lock = await self.repository.acquire_idempotency_lock(
            tenant_id=tenant_context.tenant_id,
            scope="reservation.modify",
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
                detail="Reservation modify request is already in progress",
            )

        try:
            existing_booking = await self.repository.get_booking_for_tenant(tenant_context.tenant_id, booking_id)
            if not existing_booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            update_data = await self._build_update_data(
                tenant_id=tenant_context.tenant_id,
                booking_id=booking_id,
                existing_booking=existing_booking,
                booking_data=normalized_payload,
            )

            if not update_data:
                response = dict(existing_booking)
                response.pop("_id", None)
                await self.repository.complete_idempotency_lock(lock["lock_id"], booking_id, response)
                return response

            room_changed = update_data.get("room_id") and update_data["room_id"] != existing_booking.get("room_id")
            effective_status = update_data.get("status", existing_booking.get("status"))
            old_status = existing_booking.get("status")
            new_status = update_data.get("status")

            # ── If status is transitioning to checked_in → use atomic check-in ──
            if new_status == "checked_in" and old_status != "checked_in":
                from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
                status_fields = {k: v for k, v in update_data.items() if k != "status"}
                try:
                    await check_in_booking_atomic(
                        booking_id=booking_id,
                        tenant_id=tenant_context.tenant_id,
                        actor_id=str(getattr(current_user, "id", "system")),
                        actor_name=str(getattr(current_user, "name", "system")),
                        extra_fields={k: v for k, v in status_fields.items() if k not in ("room_id",)},
                    )
                except CheckInError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                # Remove status/room keys from update_data so they aren't double-written
                update_data.pop("status", None)
                # Handle room change if also requested
                if room_changed:
                    update_data.pop("room_id", None)

            # ── If status is transitioning to checked_out → use atomic check-out ──
            elif new_status == "checked_out" and old_status != "checked_out":
                from core.atomic_checkin_checkout import CheckOutError, check_out_booking_atomic
                try:
                    await check_out_booking_atomic(
                        booking_id=booking_id,
                        tenant_id=tenant_context.tenant_id,
                        actor_id=str(getattr(current_user, "id", "system")),
                        actor_name=str(getattr(current_user, "name", "system")),
                        force=True,
                    )
                except CheckOutError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                update_data.pop("status", None)

            else:
                # Non-check-in/check-out status changes: handle room updates manually
                if room_changed and existing_booking.get("room_id"):
                    await self.repository.update_room_for_tenant(
                        tenant_context.tenant_id,
                        existing_booking["room_id"],
                        {"status": "available", "current_booking_id": None},
                    )

                if room_changed and effective_status == "checked_in":
                    await self.repository.update_room_for_tenant(
                        tenant_context.tenant_id,
                        update_data["room_id"],
                        {"status": "occupied", "current_booking_id": booking_id},
                    )

            # Release room-night locks when status transitions to cancelled/no_show (INV-6)
            if new_status in ("cancelled", "no_show") and old_status not in ("cancelled", "no_show"):
                try:
                    from core.atomic_booking import release_booking_nights
                    await release_booking_nights(
                        tenant_context.tenant_id, booking_id,
                        reason=f"{new_status}:update_service",
                        correlation_id=correlation_id,
                    )
                except Exception:
                    pass

            # Apply remaining field updates with optimistic locking (INV-4)
            if update_data:
                expected_version = existing_booking.get("_version")
                version_ok = await self.repository.update_booking(
                    tenant_context.tenant_id, booking_id, update_data,
                    expected_version=expected_version,
                )
                if not version_ok:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Concurrent modification detected. Please retry.",
                    )
            updated_booking = await self.repository.get_booking_for_tenant(tenant_context.tenant_id, booking_id)

            if not updated_booking:
                raise HTTPException(status_code=500, detail="Booking update failed")

            changes = {
                field: {
                    "from": existing_booking.get(field),
                    "to": updated_booking.get(field),
                }
                for field in update_data
                if existing_booking.get(field) != updated_booking.get(field)
            }

            if changes:
                event_envelope = build_event_envelope(
                    event_type=RESERVATION_MODIFIED_EVENT,
                    tenant_id=tenant_context.tenant_id,
                    correlation_id=correlation_id,
                    payload={
                        "reservation_id": booking_id,
                        "room_id": updated_booking.get("room_id"),
                        "guest_id": updated_booking.get("guest_id"),
                        "check_in": updated_booking.get("check_in"),
                        "check_out": updated_booking.get("check_out"),
                        "status": updated_booking.get("status"),
                        "changed_fields": list(changes.keys()),
                        "changes": changes,
                        "actor_reference": {
                            "actor_id": current_user.id,
                            "actor_name": current_user.name,
                            "actor_role": tenant_context.role,
                        },
                        "source": "semantic_reservations_service",
                    },
                ).model_dump()
                outbox_doc = {
                    **event_envelope,
                    "property_id": property_context.property_id or tenant_context.tenant_id,
                    "reservation_id": booking_id,
                    "status": "pending",
                    "modified_at": event_envelope["timestamp"],
                    "created_at": event_envelope["timestamp"],
                }
                await self.repository.insert_outbox_event(outbox_doc)

                await audit_log(
                    actor_id=current_user.id,
                    tenant_id=tenant_context.tenant_id,
                    property_id=property_context.property_id or tenant_context.tenant_id,
                    entity_type="reservation",
                    entity_id=booking_id,
                    action="reservation_modified",
                    correlation_id=correlation_id,
                    metadata={
                        "changed_fields": list(changes.keys()),
                        "changes": changes,
                        "room_id": updated_booking.get("room_id"),
                        "guest_id": updated_booking.get("guest_id"),
                    },
                )

            # Channel availability auto-sync: müsaitlik güncelle ve kanallara push et
            _avail_sync_fields = {"status", "room_id", "check_in", "check_out"}
            if changes and _avail_sync_fields & set(changes.keys()):
                try:
                    import asyncio

                    from domains.channel_manager.availability_auto_sync import sync_availability_after_booking

                    # Güncel booking tarihlerini sync et
                    asyncio.create_task(sync_availability_after_booking(
                        tenant_id=tenant_context.tenant_id,
                        room_id=updated_booking.get("room_id", ""),
                        check_in=updated_booking.get("check_in", ""),
                        check_out=updated_booking.get("check_out", ""),
                    ))
                    # Oda veya tarih değiştiyse eski oda/tarih için de sync et
                    old_room = existing_booking.get("room_id", "")
                    old_ci = existing_booking.get("check_in", "")
                    old_co = existing_booking.get("check_out", "")
                    new_room = updated_booking.get("room_id", "")
                    new_ci = updated_booking.get("check_in", "")
                    new_co = updated_booking.get("check_out", "")
                    if old_room != new_room or old_ci != new_ci or old_co != new_co:
                        asyncio.create_task(sync_availability_after_booking(
                            tenant_id=tenant_context.tenant_id,
                            room_id=old_room,
                            check_in=old_ci,
                            check_out=old_co,
                        ))
                except Exception:
                    pass

            response = dict(updated_booking)
            response.pop("_id", None)
            await self.repository.complete_idempotency_lock(lock["lock_id"], booking_id, response)
            return response
        except HTTPException as exc:
            await self.repository.fail_idempotency_lock(
                lock["lock_id"],
                exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            )
            raise
        except Exception as exc:
            await self.repository.fail_idempotency_lock(lock["lock_id"], str(exc))
            raise

    async def _build_update_data(
        self,
        tenant_id: str,
        booking_id: str,
        existing_booking: dict[str, Any],
        booking_data: dict[str, Any],
    ) -> dict[str, Any]:
        update_data: dict[str, Any] = {}

        if "guest_id" in booking_data and booking_data["guest_id"] != existing_booking.get("guest_id"):
            guest = await self.repository.get_guest_for_tenant(tenant_id, booking_data["guest_id"])
            if not guest:
                raise HTTPException(status_code=404, detail="Guest not found")

        if "room_id" in booking_data and booking_data["room_id"] != existing_booking.get("room_id"):
            room = await self.repository.get_room_for_tenant(tenant_id, booking_data["room_id"])
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")
            booking_data["room_number"] = room.get("room_number")

        for field, value in booking_data.items():
            if field not in ALLOWED_FIELDS and field != "room_number":
                continue
            if existing_booking.get(field) != value:
                update_data[field] = value

        if update_data.get("room_id") == existing_booking.get("room_id"):
            update_data.pop("room_id", None)
            update_data.pop("room_number", None)

        if not update_data:
            return {}

        return update_data

    def _normalize_payload(self, booking_data: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for field in ALLOWED_FIELDS:
            if field not in booking_data:
                continue

            value = booking_data[field]
            if field in {"check_in", "check_out"}:
                normalized[field] = self._normalize_datetime_value(value)
                continue

            if field in DEFAULT_EMPTY_FIELDS and not value:
                normalized[field] = DEFAULT_EMPTY_FIELDS[field]
                continue

            normalized[field] = value

        return normalized

    def _normalize_datetime_value(self, raw_value: Any) -> Any:
        if not isinstance(raw_value, str):
            return raw_value
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.isoformat()

    def _build_request_hash(self, tenant_id: str, booking_id: str, payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            {
                "tenant_id": tenant_id,
                "booking_id": booking_id,
                "payload": payload,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _enforce_property_scope(self, tenant_id: str, property_id: str | None) -> None:
        if property_id and property_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Property scope mismatch",
            )
