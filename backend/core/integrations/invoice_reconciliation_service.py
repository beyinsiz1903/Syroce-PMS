import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.integrations.invoice_sync_repository import InvoiceSyncRepository
from core.integrations.nilvera.errors import NilveraApiError
from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_sync import InvoiceSync, InvoiceSyncState

logger = logging.getLogger(__name__)


class InvoiceReconciliationReader(Protocol):
    """Read-only interface for reconciliation verification."""
    async def get_sale_status(self, uuid_str: str) -> dict: ...
    async def get_sale_details(self, uuid_str: str) -> dict: ...


class InvoiceReconciliationService:
    """Read-only reconciliation service for ambiguous dispatch results."""

    @staticmethod
    async def execute_reconciliation(
        tenant_id: str,
        dispatch_id: str,
        expected_version: int,
        worker_id: str,
        reader: InvoiceReconciliationReader | None = None
    ) -> bool:
        """
        Executes a two-channel reconciliation lookup to verify the existence of an invoice
        after an ambiguous POST failure.
        """
        db = get_db_for_tenant(tenant_id)
        sync_doc = await db.invoice_sync.find_one({"id": dispatch_id, "tenant_id": tenant_id})
        if not sync_doc:
            return False

        sync_model = InvoiceSync(**sync_doc)

        if sync_model.state != InvoiceSyncState.RECONCILIATION_REQUIRED:
            return False

        now = datetime.now(UTC)

        if sync_model.reconciliation_attempt_count >= 8:
            await InvoiceSyncRepository.transition_reconciliation_state(
                tenant_id,
                dispatch_id,
                current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                expected_version=expected_version,
                worker_id=worker_id,
                target_state=InvoiceSyncState.MANUAL_REVIEW_REQUIRED,
                update_fields={
                    "reconciliation_note": "Max reconciliation poll count (8) exceeded",
                    "reconciled_at": now,
                },
            )
            return False

        if reader is None:
            await InvoiceSyncRepository.transition_reconciliation_state(
                tenant_id,
                dispatch_id,
                current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                expected_version=expected_version,
                worker_id=worker_id,
                target_state=None,  # stay in same state
                update_fields={
                    "reconciliation_note": "Missing API configuration during reconciliation",
                    "next_reconciliation_at": now + timedelta(minutes=5),
                },
                inc_fields={"reconciliation_attempt_count": 1},
            )
            return False

        uuid_to_check = sync_model.request_uuid
        status_code = None
        status_provider_code = None
        detail_code = None
        detail_provider_code = None
        status_response = {}
        detail_response = {}

        # Channel 1: Status
        try:
            status_response = await reader.get_sale_status(uuid_to_check)
            status_code = 200
        except NilveraApiError as e:
            status_code = e.http_status
            status_provider_code = getattr(e, "provider_code", None)

        # Channel 2: Details
        try:
            detail_response = await reader.get_sale_details(uuid_to_check)
            detail_code = 200
        except NilveraApiError as e:
            detail_code = e.http_status
            detail_provider_code = getattr(e, "provider_code", None)

        # 401/403 Configuration Error
        if status_code in (401, 403) or detail_code in (401, 403):
            await InvoiceSyncRepository.transition_reconciliation_state(
                tenant_id,
                dispatch_id,
                current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                expected_version=expected_version,
                worker_id=worker_id,
                target_state=InvoiceSyncState.CONFIGURATION_ERROR,
                update_fields={"reconciliation_note": "API Auth failed during reconciliation", "reconciled_at": now},
                inc_fields={"reconciliation_attempt_count": 1},
            )
            return False

        # BOTH 200 (Found)
        if status_code == 200 and detail_code == 200:
            res_uuid = detail_response.get("UUID") or status_response.get("UUID")
            if res_uuid and str(res_uuid).lower() != str(uuid_to_check).lower():
                await InvoiceSyncRepository.transition_reconciliation_state(
                    tenant_id,
                    dispatch_id,
                    current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                    expected_version=expected_version,
                    worker_id=worker_id,
                    target_state=InvoiceSyncState.MANUAL_REVIEW_REQUIRED,
                    update_fields={
                        "reconciliation_note": f"UUID mismatch. Expected {uuid_to_check}, got {res_uuid}",
                        "reconciled_at": now,
                    },
                    inc_fields={"reconciliation_attempt_count": 1},
                )
                return False

            await InvoiceSyncRepository.transition_reconciliation_state(
                tenant_id,
                dispatch_id,
                current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                expected_version=expected_version,
                worker_id=worker_id,
                target_state=InvoiceSyncState.SUBMITTED,
                update_fields={
                    "reconciliation_note": "Found successfully in provider",
                    "reconciled_at": now,
                    "reconciliation_required": False,
                    "provider_document_id": uuid_to_check,
                    "submitted_at": now,
                },
                inc_fields={"reconciliation_attempt_count": 1},
            )
            return True

        # BOTH 404 (Missing)
        if status_code == 404 and detail_code == 404:
            if status_provider_code in ("3003", "3004") and detail_provider_code in ("3003", "3004"):
                updates = {"last_reconciliation_at": now}
                incs = {"reconciliation_attempt_count": 1}

                # Cycle Idempotency: only increment not_found_count if cycle is new
                curr_cycle = sync_model.current_reconciliation_cycle_id
                last_counted = sync_model.last_counted_reconciliation_cycle_id

                new_not_found = sync_model.not_found_count
                if curr_cycle and curr_cycle != last_counted:
                    new_not_found += 1
                    incs["not_found_count"] = 1
                    updates["last_counted_reconciliation_cycle_id"] = curr_cycle

                first_not_found = sync_model.first_not_found_at
                if not first_not_found:
                    first_not_found = now
                    updates["first_not_found_at"] = now

                reference_time = sync_model.sending_at or sync_model.last_attempt_at or now
                if reference_time.tzinfo is None:
                    reference_time = reference_time.replace(tzinfo=UTC)
                mins_passed = (now - reference_time).total_seconds() / 60.0

                if new_not_found >= 3 and mins_passed >= 15:
                    if sync_model.redispatch_count < 1:
                        await InvoiceSyncRepository.transition_reconciliation_state(
                            tenant_id,
                            dispatch_id,
                            current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                            expected_version=expected_version,
                            worker_id=worker_id,
                            target_state=InvoiceSyncState.SAFE_TO_RETRY,
                            update_fields={
                                "reconciliation_note": "Absence verified (Safe to retry)",
                                "reconciliation_required": False,
                                **updates,
                            },
                            inc_fields=incs,
                        )
                        return True
                    else:
                        await InvoiceSyncRepository.transition_reconciliation_state(
                            tenant_id,
                            dispatch_id,
                            current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                            expected_version=expected_version,
                            worker_id=worker_id,
                            target_state=InvoiceSyncState.MANUAL_REVIEW_REQUIRED,
                            update_fields={
                                "reconciliation_note": "Absence verified but max redispatch count reached",
                                "reconciled_at": now,
                                **updates,
                            },
                            inc_fields=incs,
                        )
                        return False

                if mins_passed >= 60:
                    await InvoiceSyncRepository.transition_reconciliation_state(
                        tenant_id,
                        dispatch_id,
                        current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                        expected_version=expected_version,
                        worker_id=worker_id,
                        target_state=InvoiceSyncState.MANUAL_REVIEW_REQUIRED,
                        update_fields={
                            "reconciliation_note": f"Max reconciliation age (60m) exceeded. Count: {new_not_found}",
                            "reconciled_at": now,
                            **updates,
                        },
                        inc_fields=incs,
                    )
                    return False

                delay_mins = min(15, 2 * (2 ** sync_model.reconciliation_attempt_count))
                updates["next_reconciliation_at"] = now + timedelta(minutes=delay_mins)
                updates["reconciliation_note"] = f"Valid 404 received. Count: {new_not_found}"

                await InvoiceSyncRepository.transition_reconciliation_state(
                    tenant_id,
                    dispatch_id,
                    current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                    expected_version=expected_version,
                    worker_id=worker_id,
                    target_state=None,
                    update_fields=updates,
                    inc_fields=incs,
                )
                return False

        # Any contradiction, 429, 5xx, or invalid 404 code
        reference_time = sync_model.sending_at or sync_model.last_attempt_at or now
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=UTC)
        mins_passed = (now - reference_time).total_seconds() / 60.0

        if mins_passed >= 60:
            await InvoiceSyncRepository.transition_reconciliation_state(
                tenant_id,
                dispatch_id,
                current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                expected_version=expected_version,
                worker_id=worker_id,
                target_state=InvoiceSyncState.MANUAL_REVIEW_REQUIRED,
                update_fields={
                    "reconciliation_note": f"Max reconciliation age (60m) exceeded due to contradiction/error. Status: {status_code}/{status_provider_code}, Details: {detail_code}/{detail_provider_code}",
                    "reconciled_at": now,
                },
                inc_fields={"reconciliation_attempt_count": 1},
            )
            return False

        delay_mins = min(15, 2 * (2 ** sync_model.reconciliation_attempt_count))
        await InvoiceSyncRepository.transition_reconciliation_state(
            tenant_id,
            dispatch_id,
            current_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
            expected_version=expected_version,
            worker_id=worker_id,
            target_state=None,
            update_fields={
                "last_reconciliation_at": now,
                "next_reconciliation_at": now + timedelta(minutes=delay_mins),
                "reconciliation_note": f"Contradiction or retryable error. Status: {status_code}/{status_provider_code}, Details: {detail_code}/{detail_provider_code}",
            },
            inc_fields={"reconciliation_attempt_count": 1},
        )
        return False
