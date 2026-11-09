"""Durable, single-write Exely ARI delivery contract."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db
from shared_kernel.idempotency import claim_idempotency, release_idempotency

from .production_safety import ari_write_block_reason
from .rate_delta import UnconfirmedRateDelivery, changed_rate_messages, rate_periods

logger = logging.getLogger("exely.ari_delivery")

COLL_EXELY_ARI_DELIVERIES = "exely_ari_deliveries"

STATE_PREPARED = "prepared"
STATE_DRY_RUN = "dry_run"
STATE_BLOCKED = "blocked"
STATE_REJECTED = "rejected"
STATE_AMBIGUOUS = "ambiguous"
STATE_RECONCILIATION_PENDING = "reconciliation_pending"
STATE_CONFIRMED = "confirmed"
STATE_WARNING_SUCCESS = "warning_success"

SUPPORTED_OPERATIONS = frozenset(
    {
        "availability",
        "availability_batch",
        "rate",
        "rate_batch",
        "restriction_batch",
        "stop_sell",
        "min_los",
        "min_los_arrival",
        "max_los",
        "cta",
        "ctd",
    }
)


@dataclass(frozen=True)
class ExelyARIDeliveryResult:
    success: bool
    state: str
    error_code: str
    provider_status_class: str
    provider_write_count: int
    operation_identity: str
    warning_codes: tuple[str, ...] = ()
    message_count: int | None = None

    def safe_metadata(self) -> dict[str, Any]:
        result = {
            "delivery_state": self.state,
            "provider_status_class": self.provider_status_class,
            "provider_write_count": self.provider_write_count,
            "write_confirmed": self.success,
            "operation_tag": self.operation_identity[:12],
        }
        if self.error_code:
            result["error_code"] = self.error_code
        if self.warning_codes:
            result["warning_codes"] = list(self.warning_codes)
        return result


def preview_exely_ari(operation: str, update: dict[str, Any]) -> ExelyARIDeliveryResult:
    """Validate an update without DB, credential, or provider access."""
    error = _validate_update(operation, update)
    identity = _operation_identity(operation, update)
    return ExelyARIDeliveryResult(
        success=False,
        state=STATE_BLOCKED if error else STATE_DRY_RUN,
        error_code=error,
        provider_status_class="NOT_SENT",
        provider_write_count=0,
        operation_identity=identity,
    )


async def deliver_exely_ari(
    tenant_id: str,
    operation: str,
    update: dict[str, Any],
    *,
    provider=None,
    write_enabled: bool | None = None,
    dry_run: bool = False,
    changed_prices_only: bool = False,
) -> ExelyARIDeliveryResult:
    """Persist one operation and send it at most once without mutation retry."""
    normalized = {**update, "tenant_id": tenant_id}
    error = _validate_update(operation, normalized)
    identity = _operation_identity(operation, normalized)
    if error:
        return _result(False, STATE_BLOCKED, error, "NOT_SENT", 0, identity)
    if dry_run:
        return _result(False, STATE_DRY_RUN, "", "NOT_SENT", 0, identity)

    runtime_block = ari_write_block_reason()
    if runtime_block:
        return _result(False, STATE_BLOCKED, runtime_block, "NOT_SENT", 0, identity)

    if write_enabled is None:
        try:
            connection = await db.exely_connections.find_one(
                {"tenant_id": tenant_id, "is_active": True},
                {"_id": 0, "ari_write_enabled": 1},
            )
            write_enabled = bool(connection and connection.get("ari_write_enabled") is True)
        except Exception:
            write_enabled = False
    if not write_enabled:
        return _result(False, STATE_BLOCKED, "EXELY_ARI_WRITE_DISABLED", "NOT_SENT", 0, identity)

    if operation not in {"rate", "rate_batch"}:
        return await _deliver(operation, normalized, identity, provider)

    # Serialize price comparison and write across workers for this property.
    # The Mongo claim is recovered by TTL after a crash. A durable sending
    # receipt still prevents a delta over any unresolved placement.
    try:
        claim = await claim_idempotency(
            db, tenant_id=tenant_id, scope="exely-ari-rate-write", idempotency_key=normalized["property_id"],
        )
    except Exception:
        return _result(False, STATE_BLOCKED, "EXELY_ARI_DELIVERY_STORE_UNAVAILABLE", "NOT_SENT", 0, identity)
    if claim["status"] != "acquired":
        return _result(False, STATE_BLOCKED, "EXELY_ARI_RATE_WRITE_IN_PROGRESS", "NOT_SENT", 0, identity)
    try:
        if changed_prices_only and operation == "rate_batch":
            try:
                messages = await _changed_rate_messages(normalized)
            except UnconfirmedRateDelivery:
                return _result(False, STATE_RECONCILIATION_PENDING, "EXELY_ARI_WRITE_OUTCOME_UNKNOWN", "WRITE_OUTCOME_UNKNOWN", 0, identity)
            except Exception:
                return _result(False, STATE_BLOCKED, "EXELY_ARI_DELIVERY_STORE_UNAVAILABLE", "NOT_SENT", 0, identity)
            if not messages:
                return _result(True, "unchanged", "", "NOT_SENT", 0, identity, message_count=0)
            if len(messages) > 200:
                return _result(False, STATE_BLOCKED, "EXELY_ARI_RATE_DELTA_PERIOD_LIMIT", "NOT_SENT", 0, identity)
            normalized["value"] = messages
        result = await _deliver(operation, normalized, identity, provider)
        if operation == "rate_batch" and result.success:
            return _result(True, result.state, "", result.provider_status_class, result.provider_write_count,
                           identity, result.warning_codes, message_count=len(normalized["value"]))
        return result
    finally:
        try:
            await release_idempotency(db, lock_id=claim["lock_id"])
        except Exception:
            logger.warning("Exely rate write claim release failed")


async def _changed_rate_messages(update):
    messages = update["value"]
    rooms = sorted({row["room_type_code"] for row in messages})
    plans = sorted({row["rate_plan_code"] for row in messages})
    cursor = db[COLL_EXELY_ARI_DELIVERIES].find({
        "tenant_id": update["tenant_id"],
        "property_id": update["property_id"],
        "state": {"$in": [STATE_CONFIRMED, STATE_WARNING_SUCCESS, STATE_AMBIGUOUS, STATE_RECONCILIATION_PENDING, "sending"]},
        "rate_periods": {"$exists": True, "$elemMatch": {
            "room_type_code": {"$in": rooms}, "rate_plan_code": {"$in": plans},
            "start_date": {"$lte": max(row["end_date"] for row in messages)},
            "end_date": {"$gte": min(row["start_date"] for row in messages)},
        }},
    }, {"state": 1, "rate_periods": 1}).sort([("created_at", -1), ("_id", -1)])
    return changed_rate_messages(messages, [receipt async for receipt in cursor])


async def _deliver(operation, normalized, identity, provider):
    owner_token = str(uuid.uuid4())
    prepared, existing = await _prepare_delivery(identity, owner_token, operation, normalized)
    if not prepared:
        if existing and existing.get("payload_fingerprint") and existing["payload_fingerprint"] != _payload_fingerprint(operation, normalized):
            return _result(False, STATE_BLOCKED, "EXELY_ARI_IDENTITY_PAYLOAD_MISMATCH", "NOT_SENT", 0, identity)
        if existing and existing.get("state") in {STATE_CONFIRMED, STATE_WARNING_SUCCESS}:
            state = str(existing["state"])
            return _result(
                True,
                state,
                "",
                "WARNING_SUCCESS" if state == STATE_WARNING_SUCCESS else "SUCCESS",
                0,
                identity,
                tuple(existing.get("warning_codes") or ()),
            )
        error_code = "EXELY_ARI_DELIVERY_IN_PROGRESS" if existing else "EXELY_ARI_DELIVERY_STORE_UNAVAILABLE"
        return _result(False, STATE_BLOCKED, error_code, "NOT_SENT", 0, identity)

    if provider is None:
        try:
            from .factory import get_exely_provider

            provider, _connection = await get_exely_provider(normalized["tenant_id"])
        except Exception:
            await _finish(identity, owner_token, STATE_BLOCKED, "EXELY_ARI_PROVIDER_UNAVAILABLE", "NOT_SENT")
            return _result(False, STATE_BLOCKED, "EXELY_ARI_PROVIDER_UNAVAILABLE", "NOT_SENT", 0, identity)

    marked = await _mark_sending(identity, owner_token)
    if not marked:
        return _result(False, STATE_BLOCKED, "EXELY_ARI_DELIVERY_STORE_UNAVAILABLE", "NOT_SENT", 0, identity)

    try:
        placement = {"number_of_guests": normalized["number_of_guests"]} if normalized.get("number_of_guests") is not None else {}
        provider_result = await provider.push_ari_operation(
            operation=operation,
            room_type_code=normalized.get("room_type_code", ""),
            rate_plan_code=normalized.get("rate_plan_code", ""),
            start_date=normalized.get("start_date", ""),
            end_date=normalized.get("end_date", ""),
            value=normalized["value"],
            currency=normalized.get("currency", "TRY"),
            **placement,
        )
    except Exception as exc:
        error_code = f"EXELY_ARI_WRITE_{type(exc).__name__.upper()}"
        await _finish(identity, owner_token, STATE_AMBIGUOUS, error_code, "WRITE_OUTCOME_UNKNOWN")
        return _result(False, STATE_AMBIGUOUS, error_code, "WRITE_OUTCOME_UNKNOWN", 1, identity)

    metadata = provider_result.metadata if isinstance(provider_result.metadata, dict) else {}
    provider_write_count = 1 if metadata.get("provider_write_count") == 1 else 0
    status_class = str(metadata.get("provider_status_class") or "MALFORMED")
    warning_codes = _safe_codes(metadata.get("warning_codes"))
    if provider_result.success and status_class in {"SUCCESS", "WARNING_SUCCESS"}:
        state = STATE_WARNING_SUCCESS if status_class == "WARNING_SUCCESS" else STATE_CONFIRMED
        persisted = await _finish(identity, owner_token, state, "", status_class, warning_codes=warning_codes)
        if not persisted:
            return _result(
                False,
                STATE_AMBIGUOUS,
                "EXELY_ARI_CONFIRMATION_STORE_UNAVAILABLE",
                "WRITE_OUTCOME_UNKNOWN",
                1,
                identity,
            )
        return _result(True, state, "", status_class, provider_write_count, identity, warning_codes)

    if provider_write_count == 0:
        error_type = str(provider_result.error_type or status_class or "PROVIDER_ERROR").upper()
        error_code = f"EXELY_ARI_{error_type}"
        await _finish(identity, owner_token, STATE_BLOCKED, error_code, status_class)
        return _result(False, STATE_BLOCKED, error_code, status_class, 0, identity)

    error_type = str(provider_result.error_type or status_class or "PROVIDER_ERROR").upper()
    if status_class in {"AMBIGUOUS", "MALFORMED", "WRITE_OUTCOME_UNKNOWN"} or error_type in {
        "EXELYTEMPORARYERROR",
        "EXELYPARSEERROR",
        "MALFORMED",
    }:
        state = STATE_AMBIGUOUS
        result_class = "WRITE_OUTCOME_UNKNOWN"
    else:
        state = STATE_REJECTED
        result_class = "RATE_LIMITED" if "RATELIMIT" in error_type else "DEFINITIVE_REJECTION"
    error_code = "EXELY_ARI_UNCONFIRMED_WARNING_783" if "783" in warning_codes else f"EXELY_ARI_{error_type}"
    await _finish(identity, owner_token, state, error_code, result_class, warning_codes=warning_codes)
    return _result(False, state, error_code, result_class, provider_write_count, identity, warning_codes)


async def reconcile_pending_exely_ari(tenant_id: str, *, limit: int = 50) -> dict[str, Any]:
    """Report unconfirmed writes without resubmitting; PMSConnect has no ARI read-back."""
    count = await db[COLL_EXELY_ARI_DELIVERIES].count_documents(
        {
            "tenant_id": tenant_id,
            "state": {"$in": [STATE_PREPARED, STATE_AMBIGUOUS, STATE_RECONCILIATION_PENDING, "sending"]},
        },
        limit=limit,
    )
    return {
        "checked": min(count, limit),
        "confirmed": 0,
        "pending": min(count, limit),
        "provider_write_count": 0,
        "reconciliation_status": "PROVIDER_READBACK_UNSUPPORTED",
    }


def _validate_update(operation: str, update: dict[str, Any]) -> str:
    if operation not in SUPPORTED_OPERATIONS:
        return "EXELY_ARI_OPERATION_UNSUPPORTED"
    for field in ("tenant_id", "property_id"):
        if not str(update.get(field) or "").strip():
            return f"EXELY_ARI_{field.upper()}_MISSING"
    if operation in {"availability_batch", "rate_batch", "restriction_batch"}:
        messages = update.get("value")
        if not isinstance(messages, list) or not messages or len(messages) > 200:
            return "EXELY_ARI_BATCH_INVALID"
        for message in messages:
            if not isinstance(message, dict):
                return "EXELY_ARI_BATCH_INVALID"
            for field in ("room_type_code", "rate_plan_code", "start_date", "end_date"):
                if not str(message.get(field) or "").strip():
                    return f"EXELY_ARI_{field.upper()}_MISSING"
            try:
                start = datetime.strptime(str(message["start_date"]), "%Y-%m-%d").date()
                end = datetime.strptime(str(message["end_date"]), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                return "EXELY_ARI_DATE_FORMAT_INVALID"
            if start.isoformat() != message["start_date"] or end.isoformat() != message["end_date"]:
                return "EXELY_ARI_DATE_FORMAT_INVALID"
            if end < start:
                return "EXELY_ARI_DATE_RANGE_INVALID"
            if operation == "availability_batch":
                availability = message.get("availability")
                if isinstance(availability, bool) or not isinstance(availability, int) or not 0 <= availability <= 999:
                    return "EXELY_ARI_AVAILABILITY_INVALID"
            elif operation == "rate_batch":
                if "guest_prices" in message:
                    from .rate_placements import validate_guest_prices

                    try:
                        validate_guest_prices(message["guest_prices"], require_adult=False)
                    except ValueError:
                        return "EXELY_ARI_PLACEMENTS_INVALID"
                guests = message.get("number_of_guests")
                if guests is not None and (type(guests) is not int or not 1 <= guests <= 20):
                    return "EXELY_ARI_OCCUPANCY_INVALID"
                try:
                    amount = Decimal(str(message.get("rate_amount")))
                except (InvalidOperation, TypeError, ValueError):
                    return "EXELY_ARI_RATE_INVALID"
                if not amount.is_finite() or amount < 0:
                    return "EXELY_ARI_RATE_INVALID"
                if not re.fullmatch(r"[A-Z]{3}", str(message.get("currency") or "")):
                    return "EXELY_ARI_CURRENCY_INVALID"
            else:
                restriction = str(message.get("operation") or "")
                value = message.get("value")
                if restriction not in {"stop_sell", "min_los", "min_los_arrival", "max_los", "cta", "ctd"}:
                    return "EXELY_ARI_RESTRICTION_INVALID"
                if restriction in {"stop_sell", "cta", "ctd"}:
                    if not isinstance(value, bool):
                        return f"EXELY_ARI_{restriction.upper()}_INVALID"
                elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    return f"EXELY_ARI_{restriction.upper()}_INVALID"
        return ""

    for field in ("room_type_code", "rate_plan_code", "start_date", "end_date"):
        if not str(update.get(field) or "").strip():
            return f"EXELY_ARI_{field.upper()}_MISSING"
    try:
        start = datetime.strptime(str(update["start_date"]), "%Y-%m-%d").date()
        end = datetime.strptime(str(update["end_date"]), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return "EXELY_ARI_DATE_FORMAT_INVALID"
    if start.isoformat() != update["start_date"] or end.isoformat() != update["end_date"]:
        return "EXELY_ARI_DATE_FORMAT_INVALID"
    if end < start:
        return "EXELY_ARI_DATE_RANGE_INVALID"

    value = update.get("value")
    if operation == "availability":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return "EXELY_ARI_AVAILABILITY_INVALID"
    elif operation == "rate":
        guests = update.get("number_of_guests")
        if guests is not None and (type(guests) is not int or not 1 <= guests <= 20):
            return "EXELY_ARI_OCCUPANCY_INVALID"
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return "EXELY_ARI_RATE_INVALID"
        if not amount.is_finite() or amount < 0:
            return "EXELY_ARI_RATE_INVALID"
        if not re.fullmatch(r"[A-Z]{3}", str(update.get("currency") or "")):
            return "EXELY_ARI_CURRENCY_INVALID"
    elif operation in {"stop_sell", "cta", "ctd"}:
        if not isinstance(value, bool):
            return f"EXELY_ARI_{operation.upper()}_INVALID"
    elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return f"EXELY_ARI_{operation.upper()}_INVALID"
    return ""


def _operation_identity(operation: str, update: dict[str, Any]) -> str:
    durable_identity = str(update.get("operation_identity") or "").strip()
    if durable_identity:
        seed = f"{update.get('tenant_id', '')}:{durable_identity}".encode()
        return hashlib.sha256(seed).hexdigest()
    return _payload_fingerprint(operation, update)


def _payload_fingerprint(operation: str, update: dict[str, Any]) -> str:
    canonical = {
        "tenant_id": str(update.get("tenant_id") or ""),
        "property_id": str(update.get("property_id") or ""),
        "operation": operation,
        "room_type_code": str(update.get("room_type_code") or ""),
        "rate_plan_code": str(update.get("rate_plan_code") or ""),
        "start_date": str(update.get("start_date") or ""),
        "end_date": str(update.get("end_date") or ""),
        "value": update.get("value"),
        "currency": str(update.get("currency") or ""),
    }
    if update.get("number_of_guests") is not None:
        canonical["number_of_guests"] = update["number_of_guests"]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def _prepare_delivery(identity: str, owner: str, operation: str, update: dict[str, Any]):
    now = datetime.now(UTC).isoformat()
    document = {
        "id": str(uuid.uuid4()),
        "operation_identity": identity,
        "owner_token": owner,
        "tenant_id": update["tenant_id"],
        "property_id": update["property_id"],
        "operation": operation,
        "room_type_code": update.get("room_type_code", ""),
        "rate_plan_code": update.get("rate_plan_code", ""),
        "start_date": update.get("start_date", ""),
        "end_date": update.get("end_date", ""),
        "payload_fingerprint": _payload_fingerprint(operation, update),
        "active_fingerprint": _payload_fingerprint(operation, update),
        "state": STATE_PREPARED,
        "attempts": 0,
        "provider_result_class": "NOT_SENT",
        "reconciliation_status": "SYNC_RESPONSE_REQUIRED",
        "created_at": now,
        "updated_at": now,
    }
    if operation in {"rate", "rate_batch"}:
        document["rate_periods"] = rate_periods(operation, update)
    try:
        await db[COLL_EXELY_ARI_DELIVERIES].insert_one(document)
        return True, None
    except DuplicateKeyError:
        try:
            existing = await db[COLL_EXELY_ARI_DELIVERIES].find_one(
                {
                    "$or": [
                        {"operation_identity": identity},
                        {"active_fingerprint": document["active_fingerprint"]},
                    ]
                },
                {"_id": 0, "state": 1, "warning_codes": 1, "payload_fingerprint": 1},
            )
            return False, existing
        except Exception:
            return False, None
    except Exception:
        return False, None


async def _mark_sending(identity: str, owner: str) -> bool:
    try:
        result = await db[COLL_EXELY_ARI_DELIVERIES].update_one(
            {"operation_identity": identity, "owner_token": owner, "state": STATE_PREPARED},
            {
                "$set": {"state": "sending", "updated_at": datetime.now(UTC).isoformat()},
                "$inc": {"attempts": 1},
            },
        )
        return result.modified_count == 1
    except Exception:
        return False


async def _finish(
    identity: str,
    owner: str,
    state: str,
    error_code: str,
    result_class: str,
    *,
    warning_codes: tuple[str, ...] = (),
) -> bool:
    try:
        terminal = state in {STATE_BLOCKED, STATE_CONFIRMED, STATE_WARNING_SUCCESS, STATE_REJECTED}
        update = {
            "$set": {
                "state": state,
                "error_code": error_code,
                "provider_result_class": result_class,
                "warning_codes": list(warning_codes),
                "reconciliation_status": ("NOT_REQUIRED_SYNC_CONFIRMED" if state in {STATE_CONFIRMED, STATE_WARNING_SUCCESS, STATE_REJECTED} else "PROVIDER_READBACK_UNSUPPORTED"),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        }
        if terminal:
            update["$unset"] = {"active_fingerprint": ""}
        result = await db[COLL_EXELY_ARI_DELIVERIES].update_one(
            {"operation_identity": identity, "owner_token": owner},
            update,
        )
        return result.matched_count == 1
    except Exception:
        return False


def _safe_codes(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    return tuple(sorted({str(value)[:64] for value in values if re.fullmatch(r"[A-Za-z0-9_.:-]+", str(value)[:64])}))


def _result(
    success: bool,
    state: str,
    error_code: str,
    status_class: str,
    write_count: int,
    identity: str,
    warning_codes: tuple[str, ...] = (),
    *,
    message_count: int | None = None,
) -> ExelyARIDeliveryResult:
    return ExelyARIDeliveryResult(
        success=success,
        state=state,
        error_code=error_code,
        provider_status_class=status_class,
        provider_write_count=write_count,
        operation_identity=identity,
        warning_codes=warning_codes,
        message_count=message_count,
    )
