import hashlib
import json
import uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from core.helpers import load_tenant_doc
from core.utils import generate_folio_number
from models.enums import FolioType
from models.schemas import Folio, FolioCreate
from modules.folio.events import FOLIO_OPENED_EVENT
from modules.folio.repository import FolioRepository
from shared_kernel.audit_helper import audit_log
from shared_kernel.event_envelope import build_event_envelope
from shared_kernel.idempotency import ensure_idempotent_request
from shared_kernel.tenancy_context import build_property_context, build_tenant_context


class OpenFolioService:
    def __init__(self, repository: Optional[FolioRepository] = None):
        self.repository = repository or FolioRepository()

    async def create(self, folio_data: FolioCreate, current_user, request: Request) -> Dict[str, Any]:
        tenant_context = build_tenant_context(current_user, request)
        property_context = build_property_context(current_user, request)
        self._enforce_property_scope(tenant_context.tenant_id, property_context.property_id)

        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        idempotency_key = ensure_idempotent_request(request, required=True)
        request_hash = self._build_request_hash(tenant_context.tenant_id, folio_data)

        lock = await self.repository.acquire_idempotency_lock(
            tenant_id=tenant_context.tenant_id,
            scope="folio.open",
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
                detail="Folio open request is already in progress",
            )

        try:
            booking = await self.repository.get_booking_for_tenant(tenant_context.tenant_id, folio_data.booking_id)
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")

            tenant_doc = await load_tenant_doc(tenant_context.tenant_id)
            if not tenant_doc:
                raise HTTPException(status_code=404, detail="Tenant not found")

            resolved_guest_id = folio_data.guest_id or booking.get("guest_id")
            resolved_company_id = folio_data.company_id or booking.get("company_id")

            if folio_data.folio_type == FolioType.GUEST:
                if not resolved_guest_id:
                    raise HTTPException(status_code=400, detail="Guest folio requires guest_id")
                guest = await self.repository.get_guest_for_tenant(tenant_context.tenant_id, resolved_guest_id)
                if not guest:
                    raise HTTPException(status_code=404, detail="Guest not found")
                if booking.get("guest_id") and resolved_guest_id != booking.get("guest_id"):
                    raise HTTPException(status_code=400, detail="Guest does not match booking")

            if folio_data.folio_type == FolioType.COMPANY:
                if not resolved_company_id:
                    raise HTTPException(status_code=400, detail="Company folio requires company_id")
                company = await self.repository.get_company_for_tenant(tenant_context.tenant_id, resolved_company_id)
                if not company:
                    raise HTTPException(status_code=404, detail="Company not found")
                if booking.get("company_id") and resolved_company_id != booking.get("company_id"):
                    raise HTTPException(status_code=400, detail="Company does not match booking")

            existing_open_folio = await self.repository.get_open_folio_for_booking(
                tenant_id=tenant_context.tenant_id,
                booking_id=folio_data.booking_id,
                folio_type=folio_data.folio_type.value,
            )
            if existing_open_folio:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Open folio already exists for this booking and folio type",
                )

            created_at = build_event_envelope(
                event_type=FOLIO_OPENED_EVENT,
                tenant_id=tenant_context.tenant_id,
                correlation_id=correlation_id,
            ).timestamp
            currency = (
                tenant_doc.get("currency")
                or tenant_doc.get("default_currency")
                or booking.get("currency")
                or "TRY"
            )

            folio = Folio(
                tenant_id=tenant_context.tenant_id,
                booking_id=folio_data.booking_id,
                folio_number=await generate_folio_number(tenant_context.tenant_id),
                folio_type=folio_data.folio_type,
                guest_id=resolved_guest_id,
                company_id=resolved_company_id,
                notes=folio_data.notes,
            )
            folio_dict = folio.model_dump()
            folio_dict["created_at"] = created_at
            folio_dict["currency"] = currency

            await self.repository.insert_folio(folio_dict)

            event_envelope = build_event_envelope(
                event_type=FOLIO_OPENED_EVENT,
                tenant_id=tenant_context.tenant_id,
                correlation_id=correlation_id,
                payload={
                    "folio_id": folio.id,
                    "reservation_id": booking["id"],
                    "stay_id": None,
                    "booking_id": booking["id"],
                    "currency": currency,
                    "folio_type": folio_data.folio_type.value,
                    "guest_id": resolved_guest_id,
                    "company_id": resolved_company_id,
                    "created_at": created_at,
                    "property_id": property_context.property_id or tenant_context.tenant_id,
                    "source": "semantic_folio_service",
                },
            ).model_dump()
            outbox_doc = {
                **event_envelope,
                "property_id": property_context.property_id or tenant_context.tenant_id,
                "folio_id": folio.id,
                "reservation_id": booking["id"],
                "status": "pending",
                "created_at": event_envelope["timestamp"],
            }
            await self.repository.insert_outbox_event(outbox_doc)

            await audit_log(
                actor_id=current_user.id,
                tenant_id=tenant_context.tenant_id,
                property_id=property_context.property_id or tenant_context.tenant_id,
                entity_type="folio",
                entity_id=folio.id,
                action="folio_opened",
                correlation_id=correlation_id,
                metadata={
                    "booking_id": booking["id"],
                    "folio_type": folio_data.folio_type.value,
                    "currency": currency,
                    "guest_id": resolved_guest_id,
                    "company_id": resolved_company_id,
                },
            )

            response_body = {
                key: value
                for key, value in folio_dict.items()
                if key in {
                    "id",
                    "tenant_id",
                    "booking_id",
                    "folio_number",
                    "folio_type",
                    "status",
                    "guest_id",
                    "company_id",
                    "balance",
                    "notes",
                    "created_at",
                    "closed_at",
                }
            }
            await self.repository.complete_idempotency_lock(lock["lock_id"], folio.id, response_body)
            return response_body
        except HTTPException as exc:
            await self.repository.fail_idempotency_lock(
                lock["lock_id"],
                exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            )
            raise
        except Exception as exc:
            await self.repository.fail_idempotency_lock(lock["lock_id"], str(exc))
            raise

    def _build_request_hash(self, tenant_id: str, folio_data: FolioCreate) -> str:
        payload = folio_data.model_dump(mode="json")
        serialized = json.dumps({"tenant_id": tenant_id, "payload": payload}, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _enforce_property_scope(self, tenant_id: str, property_id: Optional[str]) -> None:
        if property_id and property_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Property scope mismatch",
            )
