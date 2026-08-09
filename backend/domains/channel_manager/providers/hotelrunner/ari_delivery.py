"""Fail-closed HotelRunner ARI delivery and transaction reconciliation."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from core.database import db

from . import endpoints as ep
from .production_safety import ari_write_block_reason

logger = logging.getLogger("hotelrunner.ari_delivery")

COLL_ARI_DELIVERIES = "hotelrunner_ari_deliveries"
ARI_UPDATE_METHOD = "PUT"
ARI_UPDATE_ENDPOINT = ep.ROOMS_DATERANGE
ARI_RECONCILIATION_METHOD = "GET"
ARI_RECONCILIATION_ENDPOINT = ep.TRANSACTION_DETAILS

STATE_BLOCKED = "blocked"
STATE_REJECTED = "rejected"
STATE_AMBIGUOUS = "ambiguous"
STATE_RECONCILIATION_PENDING = "reconciliation_pending"
STATE_PARTIAL_FAILURE = "partial_failure"
STATE_CONFIRMED = "confirmed"

_MUTATION_FIELDS = {
    "availability",
    "price",
    "stop_sale",
    "min_stay",
    "max_stay",
    "cta",
    "ctd",
}
_ALLOWED_FIELDS = {
    "inv_code",
    "start_date",
    "end_date",
    "days",
    "channel_codes",
    *_MUTATION_FIELDS,
}


@dataclass(frozen=True)
class ARIDeliveryResult:
    success: bool
    state: str
    error_code: str
    provider_status_class: str
    provider_write_count: int
    retryable: bool = False
    transaction_id: str | None = None
    retry_after_seconds: int | None = None

    def safe_metadata(self) -> dict[str, Any]:
        """Return non-sensitive metadata suitable for API and audit output."""
        metadata: dict[str, Any] = {
            "delivery_state": self.state,
            "provider_status_class": self.provider_status_class,
            "provider_write_count": self.provider_write_count,
            "write_confirmed": self.success,
        }
        if self.error_code:
            metadata["error_code"] = self.error_code
        if self.retry_after_seconds is not None:
            metadata["retry_after_seconds"] = self.retry_after_seconds
        return metadata


def preview_ari_update(update: dict[str, Any]) -> dict[str, Any]:
    """Validate an ARI update without resolving credentials or making HTTP calls."""
    error = _validate_update(update)
    if error:
        return {
            "success": False,
            "mode": "dry_run",
            "error_code": error,
            "provider_write_count": 0,
        }
    return {
        "success": True,
        "mode": "dry_run",
        "method": ARI_UPDATE_METHOD,
        "endpoint": ARI_UPDATE_ENDPOINT,
        "fields": sorted(set(update) & _MUTATION_FIELDS),
        "provider_write_count": 0,
    }


async def deliver_hotelrunner_ari(
    tenant_id: str,
    update: dict[str, Any],
    *,
    provider=None,
) -> ARIDeliveryResult:
    """Send at most one ARI write and require terminal transaction confirmation."""
    runtime_block = ari_write_block_reason()
    if runtime_block:
        return ARIDeliveryResult(
            success=False,
            state=STATE_BLOCKED,
            error_code=runtime_block,
            provider_status_class="NOT_SENT",
            provider_write_count=0,
        )

    validation_error = _validate_update(update)
    if validation_error:
        return ARIDeliveryResult(
            success=False,
            state=STATE_BLOCKED,
            error_code=validation_error,
            provider_status_class="NOT_SENT",
            provider_write_count=0,
        )

    try:
        live_write_enabled = await _live_write_enabled(tenant_id)
    except Exception:
        live_write_enabled = False
    if not live_write_enabled:
        return ARIDeliveryResult(
            success=False,
            state=STATE_BLOCKED,
            error_code="ARI_LIVE_WRITE_DISABLED",
            provider_status_class="NOT_SENT",
            provider_write_count=0,
        )

    delivery_id = str(uuid.uuid4())
    prepared = await _create_reconciliation_record(delivery_id, tenant_id, update)
    if not prepared:
        return ARIDeliveryResult(
            success=False,
            state=STATE_BLOCKED,
            error_code="ARI_RECONCILIATION_STORE_UNAVAILABLE",
            provider_status_class="NOT_SENT",
            provider_write_count=0,
        )

    if provider is None:
        try:
            from .factory import get_provider

            provider, _ = await get_provider(tenant_id)
        except Exception:
            await _update_reconciliation_record(
                delivery_id,
                state=STATE_BLOCKED,
                error_code="ARI_PROVIDER_UNAVAILABLE",
                provider_status_class="NOT_SENT",
            )
            return ARIDeliveryResult(
                success=False,
                state=STATE_BLOCKED,
                error_code="ARI_PROVIDER_UNAVAILABLE",
                provider_status_class="NOT_SENT",
                provider_write_count=0,
            )

    try:
        send_result = await provider.update_room(**update)
    except Exception as exc:
        error_type = type(exc).__name__
        await _update_reconciliation_record(
            delivery_id,
            state=STATE_AMBIGUOUS,
            error_code=f"ARI_WRITE_{error_type.upper()}",
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
        )
        return ARIDeliveryResult(
            success=False,
            state=STATE_AMBIGUOUS,
            error_code=f"ARI_WRITE_{error_type.upper()}",
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
            provider_write_count=1,
        )

    if not isinstance(send_result, dict):
        await _update_reconciliation_record(
            delivery_id,
            state=STATE_AMBIGUOUS,
            error_code="ARI_WRITE_RESPONSE_INVALID",
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
        )
        return ARIDeliveryResult(
            success=False,
            state=STATE_AMBIGUOUS,
            error_code="ARI_WRITE_RESPONSE_INVALID",
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
            provider_write_count=1,
        )

    if not send_result.get("success"):
        error_type = str(send_result.get("error_type") or "PROVIDER_REJECTED").upper()
        retry_after = send_result.get("retry_after_seconds")
        if "RATELIMIT" in error_type or "RATE_LIMIT" in error_type:
            state = STATE_REJECTED
            status_class = "RATE_LIMITED"
            retryable = True
        elif "TEMPORARY" in error_type or "PARSE" in error_type:
            state = STATE_AMBIGUOUS
            status_class = "WRITE_OUTCOME_UNKNOWN"
            retryable = False
        else:
            state = STATE_REJECTED
            status_class = "DEFINITIVE_REJECTION"
            retryable = False
        await _update_reconciliation_record(
            delivery_id,
            state=state,
            error_code=f"ARI_WRITE_{error_type}",
            provider_status_class=status_class,
        )
        return ARIDeliveryResult(
            success=False,
            state=state,
            error_code=f"ARI_WRITE_{error_type}",
            provider_status_class=status_class,
            provider_write_count=1,
            retryable=retryable,
            retry_after_seconds=retry_after,
        )

    response_data = send_result.get("data") or {}
    if not isinstance(response_data, dict):
        await _update_reconciliation_record(
            delivery_id,
            state=STATE_AMBIGUOUS,
            error_code="ARI_WRITE_RESPONSE_INVALID",
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
        )
        return ARIDeliveryResult(
            success=False,
            state=STATE_AMBIGUOUS,
            error_code="ARI_WRITE_RESPONSE_INVALID",
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
            provider_write_count=1,
        )

    provider_status = str(response_data.get("status") or "").strip().lower()
    transaction_id = str(response_data.get("transaction_id") or "").strip()
    if provider_status != "ok" or not transaction_id:
        error_code = "ARI_PROVIDER_TRY_AGAIN" if provider_status == "try_again" else "ARI_TRANSACTION_ID_MISSING"
        await _update_reconciliation_record(
            delivery_id,
            state=STATE_AMBIGUOUS,
            error_code=error_code,
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
            transaction_id=transaction_id or None,
        )
        return ARIDeliveryResult(
            success=False,
            state=STATE_AMBIGUOUS,
            error_code=error_code,
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
            provider_write_count=1,
            transaction_id=transaction_id or None,
        )

    accepted_persisted = await _update_reconciliation_record(
        delivery_id,
        state=STATE_RECONCILIATION_PENDING,
        error_code="",
        provider_status_class="PENDING",
        transaction_id=transaction_id,
    )
    if not accepted_persisted:
        return ARIDeliveryResult(
            success=False,
            state=STATE_AMBIGUOUS,
            error_code="ARI_RECONCILIATION_STORE_UNAVAILABLE",
            provider_status_class="WRITE_OUTCOME_UNKNOWN",
            provider_write_count=1,
            transaction_id=transaction_id,
        )
    return await _reconcile_delivery(
        delivery_id,
        provider,
        transaction_id,
        provider_write_count=1,
    )


async def reconcile_pending_hotelrunner_ari(
    tenant_id: str,
    *,
    provider=None,
    limit: int = 50,
) -> dict[str, int]:
    """Reconcile accepted transactions using GET only; never resubmit writes."""
    records = (
        await db[COLL_ARI_DELIVERIES]
        .find(
            {
                "tenant_id": tenant_id,
                "state": {"$in": [STATE_RECONCILIATION_PENDING, STATE_AMBIGUOUS]},
                "transaction_id": {"$type": "string", "$ne": ""},
            },
            {"_id": 0, "id": 1, "transaction_id": 1},
        )
        .sort("created_at", 1)
        .limit(limit)
        .to_list(limit)
    )

    if not records:
        return {"checked": 0, "confirmed": 0, "pending": 0, "failed": 0, "provider_write_count": 0}

    if provider is None:
        try:
            from .factory import get_provider

            provider, _ = await get_provider(tenant_id)
        except Exception:
            return {
                "checked": 0,
                "confirmed": 0,
                "pending": len(records),
                "failed": 0,
                "provider_write_count": 0,
            }

    summary = {"checked": 0, "confirmed": 0, "pending": 0, "failed": 0, "provider_write_count": 0}
    for record in records:
        result = await _reconcile_delivery(
            record["id"],
            provider,
            record["transaction_id"],
            provider_write_count=0,
        )
        summary["checked"] += 1
        if result.state == STATE_CONFIRMED:
            summary["confirmed"] += 1
        elif result.state == STATE_RECONCILIATION_PENDING:
            summary["pending"] += 1
        else:
            summary["failed"] += 1
    return summary


async def _reconcile_delivery(
    delivery_id: str,
    provider,
    transaction_id: str,
    *,
    provider_write_count: int,
) -> ARIDeliveryResult:
    try:
        result = await provider.get_transaction_details(transaction_id)
    except Exception as exc:
        error_code = f"ARI_RECONCILIATION_{type(exc).__name__.upper()}"
        await _update_reconciliation_record(
            delivery_id,
            state=STATE_RECONCILIATION_PENDING,
            error_code=error_code,
            provider_status_class="RECONCILIATION_UNAVAILABLE",
        )
        return ARIDeliveryResult(
            success=False,
            state=STATE_RECONCILIATION_PENDING,
            error_code=error_code,
            provider_status_class="RECONCILIATION_UNAVAILABLE",
            provider_write_count=provider_write_count,
            transaction_id=transaction_id,
        )

    if not isinstance(result, dict) or not result.get("success"):
        await _update_reconciliation_record(
            delivery_id,
            state=STATE_RECONCILIATION_PENDING,
            error_code="ARI_RECONCILIATION_UNAVAILABLE",
            provider_status_class="RECONCILIATION_UNAVAILABLE",
        )
        return ARIDeliveryResult(
            success=False,
            state=STATE_RECONCILIATION_PENDING,
            error_code="ARI_RECONCILIATION_UNAVAILABLE",
            provider_status_class="RECONCILIATION_UNAVAILABLE",
            provider_write_count=provider_write_count,
            transaction_id=transaction_id,
        )

    counts = _extract_transaction_counts(result.get("data"))
    if counts is None:
        await _update_reconciliation_record(
            delivery_id,
            state=STATE_AMBIGUOUS,
            error_code="ARI_TRANSACTION_COUNTS_INVALID",
            provider_status_class="PARSE_ERROR",
        )
        return ARIDeliveryResult(
            success=False,
            state=STATE_AMBIGUOUS,
            error_code="ARI_TRANSACTION_COUNTS_INVALID",
            provider_status_class="PARSE_ERROR",
            provider_write_count=provider_write_count,
            transaction_id=transaction_id,
        )

    succeeded, failed, in_progress = counts
    if in_progress > 0:
        state = STATE_RECONCILIATION_PENDING
        error_code = "ARI_TRANSACTION_PENDING"
        status_class = "PENDING"
    elif failed > 0:
        state = STATE_PARTIAL_FAILURE
        error_code = "ARI_TRANSACTION_PARTIAL_FAILURE"
        status_class = "PARTIAL_FAILURE"
    elif succeeded <= 0:
        state = STATE_AMBIGUOUS
        error_code = "ARI_TRANSACTION_EMPTY"
        status_class = "EMPTY_RESULT"
    else:
        state = STATE_CONFIRMED
        error_code = ""
        status_class = "SUCCEEDED"

    persisted = await _update_reconciliation_record(
        delivery_id,
        state=state,
        error_code=error_code,
        provider_status_class=status_class,
        counts={"succeeded": succeeded, "failed": failed, "in_progress": in_progress},
    )
    if not persisted:
        return ARIDeliveryResult(
            success=False,
            state=STATE_AMBIGUOUS,
            error_code="ARI_RECONCILIATION_STORE_UNAVAILABLE",
            provider_status_class="RECONCILIATION_STORE_UNAVAILABLE",
            provider_write_count=provider_write_count,
            transaction_id=transaction_id,
        )
    return ARIDeliveryResult(
        success=state == STATE_CONFIRMED,
        state=state,
        error_code=error_code,
        provider_status_class=status_class,
        provider_write_count=provider_write_count,
        transaction_id=transaction_id,
    )


async def _live_write_enabled(tenant_id: str) -> bool:
    from channel_manager.connectors.hotelrunner_v2.feature_flags import get_flags

    flags = await get_flags(tenant_id)
    return bool(flags.get("connector_enabled") and flags.get("write_enabled") and not flags.get("shadow_mode", True) and not flags.get("dry_run_mode", False))


def _validate_update(update: dict[str, Any]) -> str:
    if not isinstance(update, dict):
        return "ARI_PAYLOAD_INVALID"
    if set(update) - _ALLOWED_FIELDS:
        return "ARI_PAYLOAD_FIELD_UNSUPPORTED"
    for key in ("inv_code", "start_date", "end_date"):
        if not str(update.get(key) or "").strip():
            return f"ARI_{key.upper()}_MISSING"
    try:
        start_date = datetime.strptime(str(update["start_date"]), "%Y-%m-%d").date()
        end_date = datetime.strptime(str(update["end_date"]), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return "ARI_DATE_FORMAT_INVALID"
    if end_date < start_date:
        return "ARI_DATE_RANGE_INVALID"

    mutation_fields = {key for key in _MUTATION_FIELDS if update.get(key) is not None}
    if not mutation_fields:
        return "ARI_MUTATION_FIELD_MISSING"

    if "availability" in mutation_fields:
        availability = update["availability"]
        if isinstance(availability, bool) or not isinstance(availability, int) or availability < 0:
            return "ARI_AVAILABILITY_INVALID"
    if "price" in mutation_fields:
        try:
            price = Decimal(str(update["price"]))
        except (InvalidOperation, TypeError, ValueError):
            return "ARI_PRICE_INVALID"
        if not price.is_finite() or price < 0:
            return "ARI_PRICE_INVALID"
    for field in ("min_stay", "max_stay"):
        if field in mutation_fields:
            value = update[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                return f"ARI_{field.upper()}_INVALID"
    if "min_stay" in mutation_fields and "max_stay" in mutation_fields:
        if update["max_stay"] < update["min_stay"]:
            return "ARI_STAY_RANGE_INVALID"
    for field in ("stop_sale", "cta", "ctd"):
        if field in mutation_fields and update[field] not in (True, False, 0, 1, "0", "1", "true", "false"):
            return f"ARI_{field.upper()}_INVALID"

    days = update.get("days")
    if days is not None:
        if not isinstance(days, list) or not days:
            return "ARI_DAYS_INVALID"
        if any(isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 6 for day in days):
            return "ARI_DAYS_INVALID"
    channel_codes = update.get("channel_codes")
    if channel_codes is not None:
        if not isinstance(channel_codes, list) or not channel_codes:
            return "ARI_CHANNEL_CODES_INVALID"
        if any(not isinstance(code, str) or not code.strip() for code in channel_codes):
            return "ARI_CHANNEL_CODES_INVALID"
    return ""


def _extract_transaction_counts(data: Any) -> tuple[int, int, int] | None:
    if not isinstance(data, dict):
        return None
    transaction = data.get("transaction")
    if not isinstance(transaction, dict):
        return None
    counts = transaction.get("counts")
    if not isinstance(counts, dict):
        return None
    try:
        succeeded = int(counts["succeeded"])
        failed = int(counts["failed"])
        in_progress = int(counts["in_progress"])
    except (KeyError, TypeError, ValueError):
        return None
    if min(succeeded, failed, in_progress) < 0:
        return None
    return succeeded, failed, in_progress


async def _create_reconciliation_record(
    delivery_id: str,
    tenant_id: str,
    update: dict[str, Any],
) -> bool:
    try:
        await db[COLL_ARI_DELIVERIES].insert_one(
            {
                "id": delivery_id,
                "tenant_id": tenant_id,
                "state": "prepared",
                "field_names": sorted(set(update) & _MUTATION_FIELDS),
                "transaction_id": None,
                "provider_status_class": "NOT_SENT",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        return True
    except Exception:
        logger.error("HotelRunner ARI reconciliation record could not be prepared")
        return False


async def _update_reconciliation_record(
    delivery_id: str,
    *,
    state: str,
    error_code: str,
    provider_status_class: str,
    transaction_id: str | None = None,
    counts: dict[str, int] | None = None,
) -> bool:
    update: dict[str, Any] = {
        "state": state,
        "error_code": error_code,
        "provider_status_class": provider_status_class,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if transaction_id is not None:
        update["transaction_id"] = transaction_id
    if counts is not None:
        update["counts"] = counts
    try:
        result = await db[COLL_ARI_DELIVERIES].update_one(
            {"id": delivery_id},
            {"$set": update},
        )
        return getattr(result, "matched_count", 1) == 1
    except Exception:
        logger.error("HotelRunner ARI reconciliation record could not be updated")
        return False
