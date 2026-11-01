"""Version-fenced demographic reconciliation, separate from immutable SOAP events.

Only adult/child counts and provenance may change. No re-import, repricing, ACK,
room assignment, KBS, payment, folio, guest profile or source-payload mutation.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from core.database import db

from .lifecycle import PMS_DURABLE, _provider_time
from .mapping_codes import inbound_mapping_query
from .read_reservation import ReadReservationError, read_client, saved_read_credentials

SOURCE = "exely_read_reservation_v1"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ReadReservationError(code)


def _money(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
        _require(result.is_finite() and result >= 0, "EXELY_READ_AMOUNT_INVALID")
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ReadReservationError("EXELY_READ_AMOUNT_INVALID") from None


def _rest_time(value: Any) -> datetime:
    """REST uses offset-bearing timestamps, independent of SOAP's clock."""
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        _require(parsed.tzinfo is not None, "EXELY_READ_REST_VERSION_INVALID")
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        raise ReadReservationError("EXELY_READ_REST_VERSION_INVALID") from None


def _rest_hash(remote: dict[str, Any]) -> str:
    # Hash the full snapshot, not just counts: a same-timestamp provider change
    # must also prevent reconciliation. Never persist the guest/contact payload.
    try:
        return hashlib.sha256(json.dumps(remote, sort_keys=True, allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError):
        raise ReadReservationError("EXELY_READ_DATA_INVALID") from None


async def stable_reconciliation_plan(tenant_id: str, connection: dict[str, Any], reservation: dict[str, Any], client) -> list[dict[str, Any]]:
    number = str(reservation.get("external_id") or "")
    remote = await client.booking(number)
    plans = await reconciliation_plan(tenant_id, connection, reservation, remote)
    expected_hash = _rest_hash(remote)
    latest = await client.booking(number)
    _require(_rest_hash(latest) == expected_hash, "EXELY_READ_REMOTE_CHANGED")
    return plans


def _date(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        raise ReadReservationError("EXELY_READ_STAY_INVALID") from None


async def inspect_reconciliation(tenant_id: str, connection: dict[str, Any], number: str, client) -> dict[str, Any]:
    """Read-only, allowlisted comparison; never return guest/contact payloads.

    A zero-match failure used to be indistinguishable from identical rooms.
    Inspect both provider reads before returning even diagnostic evidence.
    This endpoint cannot apply a plan or acknowledge a reservation.
    """
    reservation = await db.exely_reservations.find_one({
        "tenant_id": tenant_id, "property_id": str(connection["hotel_code"]), "external_id": number,
    }, {"_id": 0})
    _require(bool(reservation), "EXELY_READ_LOCAL_RESERVATION_NOT_FOUND")
    remote = await client.booking(number)
    _require(str(remote.get("propertyId")) == str(connection["hotel_code"]) and remote.get("number") == number,
             "EXELY_READ_BOOKING_SCOPE_MISMATCH")
    snapshot_hash = _rest_hash(remote)
    _require(_rest_hash(await client.booking(number)) == snapshot_hash, "EXELY_READ_REMOTE_CHANGED")
    try:
        await reconciliation_plan(tenant_id, connection, reservation, remote)
        status = "ready"
    except ReadReservationError as exc:
        status = str(exc)

    def safe_id(value):
        value = str(value) if value is not None else ""
        return value if value.isascii() and value.isdecimal() and len(value) <= 32 else None

    def services(items, *, soap=False):
        return [{
            "id": safe_id(item.get("provider_id" if soap else "id")),
            "inclusive": item.get("inclusive") if type(item.get("inclusive")) is bool else None,
            "amount": str(_money(item.get("amount") if soap else (item.get("total") or {}).get("priceAfterTax")))
            if (item.get("amount") if soap else (item.get("total") or {}).get("priceAfterTax")) is not None else None,
        } for item in items or []]

    source_rooms = []
    for room in reservation.get("rooms") or []:
        mapping = await db.exely_room_mappings.find_one(inbound_mapping_query(
            tenant_id, str(room.get("room_type_code") or ""), str(room.get("rate_plan_code") or "")), {"_id": 0})
        source_rooms.append({
            "index": safe_id(room.get("index_number")),
            "mapped_room_type_id": safe_id((mapping or {}).get("exely_room_code")),
            "arrival": _date(room.get("check_in") or reservation.get("checkin_date")),
            "departure": _date(room.get("check_out") or reservation.get("checkout_date")),
            "amount": str(_money(room.get("amount"))), "services": services(room.get("services"), soap=True),
        })
    return {
        "status": status, "property_id": str(connection["hotel_code"]), "reservation_id": number,
        "rest_snapshot_hash": snapshot_hash, "source_total": str(_money(reservation.get("total"))),
        "rest_total": str(_money((remote.get("total") or {}).get("priceAfterTax"))),
        "currency_matches": remote.get("currencyCode") == reservation.get("currency"),
        "source_rooms": source_rooms,
        "rest_rooms": [{
            "index": item.get("index") if type(item.get("index")) is int else None,
            "room_type_id": safe_id((item.get("roomType") or {}).get("id")),
            "arrival": _date((item.get("stayDates") or {}).get("arrivalDateTime")),
            "departure": _date((item.get("stayDates") or {}).get("departureDateTime")),
            "amount": str(_money((item.get("total") or {}).get("priceAfterTax"))),
            "services": services(item.get("services")),
        } for item in remote.get("roomStays") or []],
        "applied": False, "provider_write_count": 0,
    }


def verified_booking(booking: dict[str, Any]) -> bool:
    proof = booking.get("exely_demographics") or {}
    ages = booking.get("children_ages")
    return bool(
        proof.get("status") == "verified" and proof.get("source") == SOURCE
        and proof.get("property_id") == booking.get("property_id")
        and proof.get("reservation_id") == booking.get("provider_group_reservation_id")
        and proof.get("provider_version_key") == booking.get("provider_version_key")
        and type(booking.get("adults")) is int and booking["adults"] == proof.get("adults")
        and isinstance(ages, list) and all(type(age) is int and 0 <= age <= 17 for age in ages)
        and ages == proof.get("children_ages") and booking.get("children") == len(ages)
        and booking.get("guests_count") == booking["adults"] + len(ages)
        and all(proof.get(key) == booking.get(key) and proof.get(key) is not None for key in (
            "check_in", "check_out", "room_type", "currency", "total_amount",
        ))
    )


async def reconciliation_plan(tenant_id: str, connection: dict[str, Any], reservation: dict[str, Any], remote: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        return await _build_plan(tenant_id, connection, reservation, remote)
    except (TypeError, ValueError, AttributeError, ArithmeticError):
        raise ReadReservationError("EXELY_READ_DATA_INVALID") from None


async def _build_plan(tenant_id: str, connection: dict[str, Any], reservation: dict[str, Any], remote: dict[str, Any]) -> list[dict[str, Any]]:
    property_id, number = str(connection["hotel_code"]), str(reservation.get("external_id") or "")
    _require(reservation.get("tenant_id") == tenant_id and str(reservation.get("property_id")) == property_id, "EXELY_READ_LOCAL_SCOPE_MISMATCH")
    _require(str(remote.get("propertyId")) == property_id and remote.get("number") == number, "EXELY_READ_BOOKING_SCOPE_MISMATCH")
    _require(remote.get("status") == "Active" and reservation.get("state") in {"confirmed", "modified"}, "EXELY_READ_BOOKING_NOT_ACTIVE")
    # SOAP LastModifyDateTime and REST modifiedDateTime are NOT a shared
    # revision identifier. The observed TEST payloads even differ by seconds
    # after timezone conversion. Fence each source independently; never apply
    # guessed offsets or a permissive cross-API time tolerance.
    _require(bool(reservation.get("provider_version_key")), "EXELY_READ_SOURCE_VERSION_INVALID")
    _provider_time(reservation["provider_version_key"])
    rest_time = _rest_time(remote.get("modifiedDateTime"))
    rest_hash = _rest_hash(remote)
    _require(remote.get("currencyCode") == reservation.get("currency"), "EXELY_READ_CURRENCY_MISMATCH")
    _require(_money((remote.get("total") or {}).get("priceAfterTax")) == _money(reservation.get("total")), "EXELY_READ_TOTAL_MISMATCH")
    version = await db.exely_reservation_versions.find_one({
        "tenant_id": tenant_id, "property_id": property_id,
        "version_identity": reservation.get("provider_version_identity"),
    }, {"_id": 0})
    _require(bool(version) and version.get("processing_state") == PMS_DURABLE, "EXELY_READ_VERSION_NOT_DURABLE")
    rooms, remote_rooms = reservation.get("rooms") or [], remote.get("roomStays") or []
    _require(bool(rooms) and isinstance(remote_rooms, list) and len(rooms) == len(remote_rooms), "EXELY_READ_ROOM_COUNT_MISMATCH")
    remaining = list(remote_rooms)
    plans = []
    for room in rooms:
        mapping = await db.exely_room_mappings.find_one(inbound_mapping_query(tenant_id, str(room.get("room_type_code") or ""), str(room.get("rate_plan_code") or "")), {"_id": 0})
        _require(bool(mapping), "EXELY_READ_ROOM_MAPPING_MISSING")
        check_in = _date(room.get("check_in") or reservation.get("checkin_date"))
        check_out = _date(room.get("check_out") or reservation.get("checkout_date"))
        # Zero-price accommodation is not a missing amount. The booking total
        # may contain paid extra services and must not replace an explicit zero.
        raw_amount = room.get("amount")
        amount = _money(raw_amount if raw_amount is not None else (reservation.get("total") if len(rooms) == 1 else 0))
        candidates = [item for item in remaining if (
            isinstance(item, dict)
            and str((item.get("roomType") or {}).get("id")) == str(mapping.get("exely_room_code"))
            and _date((item.get("stayDates") or {}).get("arrivalDateTime")) == check_in
            and _date((item.get("stayDates") or {}).get("departureDateTime")) == check_out
            and _money((item.get("total") or {}).get("priceAfterTax")) == amount
        )]
        # Do not guess the relation between SOAP's one-based RoomStay indexes
        # and Connect's indexes, or distribute ages across identical rooms.
        _require(bool(candidates), "EXELY_READ_ROOM_JOIN_NOT_FOUND")
        _require(len(candidates) == 1, "EXELY_READ_ROOM_JOIN_AMBIGUOUS")
        remote_room = candidates[0]
        remaining.remove(remote_room)
        count = remote_room.get("guestCount") or {}
        adults, ages = count.get("adultCount"), count.get("childAges")
        _require(type(adults) is int and 0 <= adults <= 1000 and isinstance(ages, list) and len(ages) <= 1000 and all(type(age) is int and 0 <= age <= 17 for age in ages), "EXELY_READ_GUEST_COUNTS_INVALID")
        _require(adults + len(ages) > 0 and adults + len(ages) == int(room.get("adults") or 0) + int(room.get("children") or 0), "EXELY_READ_GUEST_TOTAL_MISMATCH")
        if room.get("children"):
            # Fill absent bed-count demographics, but never silently choose
            # between two contradictory structured provider child records.
            known_ages = list(room.get("children_ages") or [])
            _require(len(ages) == room["children"] and not (Counter(known_ages) - Counter(ages)), "EXELY_READ_STRUCTURED_DEMOGRAPHICS_CONFLICT")
        lineage = [item for item in reservation.get("room_stay_lineage") or [] if item.get("active", True) and str(item.get("index_number") or "") == str(room.get("index_number") or "")]
        _require(len(lineage) == 1, "EXELY_READ_PMS_LINEAGE_AMBIGUOUS")
        booking_id = lineage[0].get("pms_booking_id")
        _require(booking_id in (reservation.get("pms_booking_ids") or [reservation.get("pms_booking_id")]), "EXELY_READ_PMS_LINEAGE_MISMATCH")
        booking = await db.bookings.find_one({"tenant_id": tenant_id, "id": booking_id}, {"_id": 0})
        _require(bool(booking) and booking.get("property_id") == property_id and booking.get("provider_group_reservation_id") == number and booking.get("booking_source") == "exely", "EXELY_READ_PMS_SCOPE_MISMATCH")
        previous = booking.get("exely_demographics") or {}
        if previous.get("status") == "verified" and previous.get("source") == SOURCE:
            previous_time = _rest_time(previous.get("rest_modified_at"))
            _require(rest_time >= previous_time, "EXELY_READ_REST_VERSION_REGRESSED")
            if rest_time == previous_time and previous.get("rest_snapshot_hash"):
                _require(previous["rest_snapshot_hash"] == rest_hash, "EXELY_READ_REST_VERSION_CONFLICT")
        _require(booking.get("status") == "confirmed" and booking.get("provider_version_key") == reservation.get("provider_version_key"), "EXELY_READ_PMS_VERSION_OR_STATUS_CHANGED")
        _require(bool(mapping.get("pms_room_type")) and booking.get("room_type") == mapping["pms_room_type"], "EXELY_READ_PMS_ROOM_TYPE_CHANGED")
        _require(_date(booking.get("check_in")) == check_in and _date(booking.get("check_out")) == check_out and booking.get("currency") == reservation.get("currency") and _money(booking.get("total_amount")) == amount, "EXELY_READ_PMS_STAY_OR_AMOUNT_CHANGED")
        raw_counts = (room.get("adults"), room.get("children", 0), list(room.get("children_ages") or []))
        actual_counts = (booking.get("adults"), booking.get("children", 0), list(booking.get("children_ages") or []))
        _require(actual_counts == raw_counts or verified_booking(booking), "EXELY_READ_PMS_DEMOGRAPHICS_EDITED")
        proof = {
            "status": "verified", "source": SOURCE, "property_id": property_id,
            "reservation_id": number, "provider_version_key": booking["provider_version_key"],
            "rest_modified_at": remote["modifiedDateTime"], "rest_room_index": remote_room.get("index"),
            "rest_snapshot_hash": rest_hash,
            "adults": adults, "children_ages": ages,
            **{key: booking[key] for key in ("check_in", "check_out", "room_type", "currency", "total_amount")},
        }
        evidence_hash = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
        proof.update(evidence_hash=evidence_hash, verified_at=datetime.now(UTC).isoformat())
        plans.append({"booking": booking, "proof": proof})
    return plans


async def apply_plan(tenant_id: str, connection: dict[str, Any], reservation: dict[str, Any], plans: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for plan in plans:
        booking, proof = plan["booking"], plan["proof"]
        current = await db.exely_reservations.find_one({
            "tenant_id": tenant_id, "property_id": str(connection["hotel_code"]),
            "external_id": reservation["external_id"], "provider_version_identity": reservation["provider_version_identity"],
        }, {"_id": 0, "provider_version_identity": 1})
        _require(bool(current), "EXELY_READ_CURRENT_VERSION_CHANGED")
        _require(bool(await db.exely_connections.find_one({
            "tenant_id": tenant_id, "id": connection["id"], "hotel_code": connection["hotel_code"],
            "mode": connection["mode"], "is_active": True, "read_reservation_enabled": True,
        }, {"_id": 0, "id": 1})), "EXELY_READ_CONNECTION_CHANGED")
        fields = {
            "adults": proof["adults"], "children": len(proof["children_ages"]),
            "children_ages": proof["children_ages"], "children_ages_complete": True,
            "guests_count": proof["adults"] + len(proof["children_ages"]), "exely_demographics": proof,
            "updated_at": proof["verified_at"],
        }
        fence = {key: booking.get(key) for key in (
            "id", "property_id", "provider_version_key", "provider_group_reservation_id", "booking_source", "status", "room_type",
            "adults", "children", "children_ages", "updated_at", "_version", "check_in", "check_out", "total_amount", "currency",
        )}
        fence["tenant_id"] = tenant_id
        changed = await db.bookings.update_one(fence, {"$set": fields, "$inc": {"_version": 1}})
        _require(changed.matched_count == 1, "EXELY_READ_CONCURRENT_BOOKING_CHANGE")
        from cache_manager import cache
        from cache_warmer import cache_warmer

        if cache_warmer:
            cache_warmer.invalidate(f"bookings:{tenant_id}")
        for prefix in ("bookings", "dashboard", "reports"):
            cache.safe_invalidate(tenant_id, prefix)
        readback = await db.bookings.find_one({"tenant_id": tenant_id, "id": booking["id"]}, {"_id": 0})
        _require(bool(readback) and verified_booking(readback) and readback["exely_demographics"]["evidence_hash"] == proof["evidence_hash"], "EXELY_READ_PMS_READBACK_FAILED")
        # Append-only evidence; source reservation/version payloads stay intact.
        evidence_id = hashlib.sha256(f"{tenant_id}:{booking['id']}:{proof['evidence_hash']}".encode()).hexdigest()
        await db.exely_demographic_checks.update_one(
            {"_id": evidence_id, "tenant_id": tenant_id, "booking_id": booking["id"], "evidence_hash": proof["evidence_hash"]},
            {"$setOnInsert": {"property_id": proof["property_id"], "before": {
                "adults": booking.get("adults"), "children": booking.get("children"), "children_ages": booking.get("children_ages"),
            }, "after": proof}}, upsert=True,
        )
        results.append({"booking_id": booking["id"], "adults": fields["adults"], "children_ages": fields["children_ages"], "status": "verified"})
    return {"success": True, "status": "verified", "rooms": results, "provider_write_count": 0}


async def reconcile_one(tenant_id: str, connection: dict[str, Any], number: str, client) -> dict[str, Any]:
    reservation = await db.exely_reservations.find_one({"tenant_id": tenant_id, "property_id": str(connection["hotel_code"]), "external_id": number}, {"_id": 0})
    _require(bool(reservation), "EXELY_READ_LOCAL_RESERVATION_NOT_FOUND")
    plans = await stable_reconciliation_plan(tenant_id, connection, reservation, client)
    return await apply_plan(tenant_id, connection, reservation, plans)


async def reconcile_pending(tenant_id: str, property_id: str) -> dict[str, Any]:
    connection = await db.exely_connections.find_one({"tenant_id": tenant_id, "hotel_code": property_id, "is_active": True}, {"_id": 0})
    if not connection or not connection.get("read_reservation_enabled"):
        return {"status": "not_configured", "verified": 0}
    try:
        credentials = await saved_read_credentials(tenant_id, connection)
        pending = await db.bookings.find({
            "tenant_id": tenant_id, "property_id": property_id, "booking_source": "exely", "status": "confirmed",
            "check_out": {"$gte": datetime.now(UTC).date().isoformat()},
            "exely_demographics.status": {"$ne": "verified"},
        }, {"_id": 0, "provider_group_reservation_id": 1}).sort([("exely_demographics.last_attempt_at", 1), ("id", 1)]).to_list(25)
        numbers = sorted({row["provider_group_reservation_id"] for row in pending if row.get("provider_group_reservation_id")})
        verified, errors = 0, []
        async with read_client(connection, credentials) as client:
            for number in numbers:
                try:
                    await reconcile_one(tenant_id, connection, number, client)
                    verified += 1
                except ReadReservationError as exc:
                    errors.append(str(exc))
                    await db.bookings.update_many({
                        "tenant_id": tenant_id, "property_id": property_id, "booking_source": "exely", "status": "confirmed",
                        "provider_group_reservation_id": number, "exely_demographics.status": {"$ne": "verified"},
                    }, {"$set": {"exely_demographics": {"status": "needs_review", "last_attempt_at": datetime.now(UTC).isoformat(), "error_code": str(exc)}}})
                    # Do not multiply an outage/auth/quota failure by 25 requests.
                    if str(exc).startswith(("EXELY_READ_HTTP_", "EXELY_READ_RESPONSE_")):
                        break
        return {"status": "needs_review" if errors else "verified", "verified": verified, "errors": errors}
    except ReadReservationError as exc:
        return {"status": "needs_review", "verified": 0, "errors": [str(exc)]}
