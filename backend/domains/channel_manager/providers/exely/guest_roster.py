"""Room-scoped named occupants, independent of booking contact and occupancy.

No ACK, inventory, financial, check-in or KBS side effects. All membership
writes are transactional and fenced against a newer import or manual edit.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from security.guest_write import encrypt_guest_insert, encrypt_guest_update

from .read_reservation import ReadReservationError


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise ReadReservationError(code)


def _names(person: dict) -> dict:
    first = str(person.get("guest_firstname") or "").strip()
    last = str(person.get("guest_lastname") or "").strip()
    _require(bool(first or last) and len(first) <= 200 and len(last) <= 200, "EXELY_ROSTER_NAME_INVALID")
    return {"first_name": first, "last_name": last, "name": " ".join(filter(None, (first, last)))}


def _name_hash(person: dict) -> str:
    return hashlib.sha256(json.dumps([
        " ".join(str(person.get(key) or "").split()).casefold()
        for key in ("first_name", "last_name")
    ], ensure_ascii=False).encode()).hexdigest()


def rest_roster(raw: list, primary: dict) -> list[dict]:
    _require(isinstance(raw, list) and 0 < len(raw) <= 1000, "EXELY_ROSTER_NOT_AVAILABLE")
    result, occurrences = [], {}
    for person in raw:
        _require(isinstance(person, dict), "EXELY_ROSTER_NAME_INVALID")
        item = {"guest_firstname": person.get("firstName"), "guest_lastname": person.get("lastName")}
        digest = _name_hash(_names(item))
        occurrences[digest] = occurrences.get(digest, 0) + 1
        item["source_rph"] = f"rest:{digest}:{occurrences[digest]}"
        result.append(item)
    matches = [index for index, item in enumerate(result) if _name_hash(_names(item)) == _name_hash(primary)]
    _require(len(matches) == 1, "EXELY_ROSTER_PRIMARY_AMBIGUOUS")
    result.insert(0, result.pop(matches[0]))
    return result


def preserve_primary(roster: list[dict], previous: dict | None) -> list[dict]:
    """Room-reference order may change without changing its lead occupant."""
    members = (previous or {}).get("members") or []
    if not members:
        return roster
    matches = [index for index, person in enumerate(roster) if person.get("source_rph") == members[0]["key"]]
    if not matches:
        matches = [index for index, person in enumerate(roster) if _name_hash(_names(person)) == members[0]["name_hash"]]
    _require(len(matches) == 1, "EXELY_ROSTER_PRIMARY_REASSIGNMENT_REVIEW")
    return [roster[matches[0]], *[person for index, person in enumerate(roster) if index != matches[0]]]


async def sync_room_roster(database, tenant_id: str, booking: dict, roster: list[dict], *,
                           source: str = "pmsconnect", proof: dict | None = None,
                           connection: dict | None = None, reservation: dict | None = None) -> dict:
    """Preserve primary ID, create/link every additional named room occupant.

    REST completion requires a twice-read, identity-verified plan from
    demographics.stable_reconciliation_plan. It never mutates its SOAP source.
    """
    _require(isinstance(roster, list) and 0 < len(roster) <= 1000, "EXELY_ROSTER_NOT_AVAILABLE")
    names = [_names(person) for person in roster]
    keys = [str(person.get("source_rph") or "") for person in roster]
    _require(all(keys) and len(set(keys)) == len(keys), "EXELY_ROSTER_REFERENCE_INVALID")
    now = datetime.now(UTC).isoformat()
    fence = {key: booking.get(key) for key in (
        "id", "property_id", "provider_version_key", "provider_group_reservation_id", "booking_source",
        "guest_id", "status", "updated_at", "_version", "exely_processing_generation",
        "check_in", "check_out", "room_type", "total_amount", "currency", "adults", "children", "children_ages", "guests_count",
    )}
    fence["tenant_id"] = tenant_id
    _require(booking.get("status") == "confirmed" and booking.get("booking_source") == "exely", "EXELY_ROSTER_BOOKING_NOT_EDITABLE")
    _require(len(roster) <= int(booking.get("guests_count") or 0), "EXELY_ROSTER_EXCEEDS_OCCUPANCY")
    async with await database.client.start_session() as session:
        async with session.start_transaction():
            current = await database.bookings.find_one(fence, {"_id": 0}, session=session)
            _require(bool(current), "EXELY_ROSTER_CONCURRENT_BOOKING_CHANGE")
            if connection is not None:
                _require(reservation is not None and proof is not None, "EXELY_ROSTER_SOURCE_REQUIRED")
                _require(bool(await database.exely_connections.find_one({
                    "tenant_id": tenant_id, "id": connection["id"], "hotel_code": connection["hotel_code"],
                    "mode": connection["mode"], "is_active": True, "read_reservation_enabled": True,
                }, session=session)), "EXELY_READ_CONNECTION_CHANGED")
                _require(bool(await database.exely_reservations.find_one({
                    "tenant_id": tenant_id, "property_id": booking["property_id"],
                    "external_id": reservation["external_id"], "provider_version_identity": reservation["provider_version_identity"],
                }, session=session)), "EXELY_READ_CURRENT_VERSION_CHANGED")
            primary = await database.guests.find_one({"tenant_id": tenant_id, "id": booking["guest_id"]}, {"_id": 0}, session=session)
            _require(bool(primary) and _name_hash(primary) == _name_hash(names[0]), "EXELY_ROSTER_PRIMARY_CHANGED")
            previous = current.get("exely_guest_roster") or {}
            if proof and previous.get("rest_modified_at"):
                from .demographics import _rest_time
                _require(_rest_time(proof["rest_modified_at"]) >= _rest_time(previous["rest_modified_at"]), "EXELY_ROSTER_SOURCE_REGRESSED")
                if _rest_time(proof["rest_modified_at"]) == _rest_time(previous["rest_modified_at"]):
                    _require(proof["rest_snapshot_hash"] == previous.get("rest_snapshot_hash"), "EXELY_ROSTER_SOURCE_CONFLICT")
            prior = previous.get("members") or []
            links = await database.booking_guests.find({"tenant_id": tenant_id, "booking_id": booking["id"]}, {"_id": 0}, session=session).to_list(1001)
            # Never replace receptionist-added occupants or their checkout data.
            owned = {member["guest_id"] for member in prior[1:]}
            _require({link.get("guest_id") for link in links} == owned and
                     all(link.get("source") == "exely_guest_roster" and not link.get("checkin_date") and not link.get("checkout_date") for link in links), "EXELY_ROSTER_MANUAL_MEMBERSHIP_REVIEW")
            for member in prior[1:]:
                person = await database.guests.find_one({"tenant_id": tenant_id, "id": member["guest_id"]}, {"_id": 0}, session=session)
                _require(bool(person) and person.get("exely_roster_name_hash") == _name_hash(person) == member["name_hash"], "EXELY_ROSTER_GUEST_EDITED")
            members = [{"key": keys[0], "guest_id": booking["guest_id"], "name_hash": _name_hash(names[0])}]
            used_ids = {booking["guest_id"]}
            for person, name, key in zip(roster[1:], names[1:], keys[1:], strict=True):
                digest = _name_hash(name)
                prior_matches = [member for member in prior[1:] if member["guest_id"] not in used_ids and member["key"] == key]
                if not prior_matches:
                    # SOAP RPH and REST name-based references are different
                    # namespaces; reuse a unique existing person across them.
                    prior_matches = [member for member in prior[1:] if member["guest_id"] not in used_ids and member["name_hash"] == digest]
                _require(len(prior_matches) <= 1, "EXELY_ROSTER_MEMBER_AMBIGUOUS")
                guest_id = prior_matches[0]["guest_id"] if prior_matches else str(uuid.uuid5(uuid.NAMESPACE_URL, f"exely-occupant:{tenant_id}:{booking['property_id']}:{booking['id']}:{key}"))
                existing = await database.guests.find_one({"tenant_id": tenant_id, "id": guest_id}, {"_id": 0}, session=session)
                if existing:
                    _require(existing.get("exely_roster_name_hash") == _name_hash(existing), "EXELY_ROSTER_GUEST_EDITED")
                    if _name_hash(existing) != digest:
                        await database.guests.update_one({"tenant_id": tenant_id, "id": guest_id}, {"$set": encrypt_guest_update({**name, "exely_roster_name_hash": digest, "updated_at": now}, existing=existing)}, session=session)
                else:
                    guest = {"id": guest_id, "tenant_id": tenant_id, **name,
                             "email": str(person.get("guest_email") or ""), "phone": str(person.get("guest_phone") or ""),
                             "nationality": str(person.get("guest_country") or ""), "id_number": "",
                             "total_stays": 0, "vip_level": "none", "loyalty_tier": "none",
                             "created_at": now, "notes": "Exely kanal rezervasyonu",
                             "exely_roster_name_hash": digest}
                    await database.guests.insert_one(encrypt_guest_insert(guest), session=session)
                link_id = f"exely-guest:{booking['id']}:{guest_id}"
                await database.booking_guests.update_one({"_id": link_id, "tenant_id": tenant_id}, {"$setOnInsert": {
                    "id": link_id, "booking_id": booking["id"], "guest_id": guest_id, "source": "exely_guest_roster", "created_at": now,
                }}, upsert=True, session=session)
                members.append({"key": key, "guest_id": guest_id, "name_hash": digest})
                used_ids.add(guest_id)
            stale = owned - used_ids
            if stale:
                await database.booking_guests.delete_many({"tenant_id": tenant_id, "booking_id": booking["id"], "guest_id": {"$in": list(stale)}, "source": "exely_guest_roster"}, session=session)
            manifest = {"source": source, "provider_version_key": booking["provider_version_key"], "members": members}
            if proof:
                manifest.update({key: proof[key] for key in ("rest_modified_at", "rest_snapshot_hash")})
            changed = await database.bookings.update_one(fence, {"$set": {"exely_guest_roster": manifest}, "$inc": {"_version": 1}}, session=session)
            _require(changed.matched_count == 1, "EXELY_ROSTER_CONCURRENT_BOOKING_CHANGE")
    _require(await roster_readback(database, tenant_id, booking["id"], manifest), "EXELY_ROSTER_READBACK_FAILED")
    return manifest


async def roster_readback(database, tenant_id: str, booking_id: str, manifest: dict) -> bool:
    booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": booking_id}, {"_id": 0})
    actual = (booking or {}).get("exely_guest_roster") or {}
    # A REST verification can add provenance to the same durable people while
    # a SOAP ACK is pending. Compare membership, not the reference namespace.
    if (not booking or actual.get("provider_version_key") != manifest["provider_version_key"]
            or booking.get("provider_version_key") != manifest["provider_version_key"]
            or {(row["guest_id"], row["name_hash"]) for row in actual.get("members") or []}
            != {(row["guest_id"], row["name_hash"]) for row in manifest["members"]}
            or booking.get("guest_id") != manifest["members"][0]["guest_id"]):
        return False
    for index, member in enumerate(manifest["members"]):
        person = await database.guests.find_one({"tenant_id": tenant_id, "id": member["guest_id"]}, {"_id": 0})
        if not person or _name_hash(person) != member["name_hash"]:
            return False
        if index and not await database.booking_guests.find_one({"tenant_id": tenant_id, "booking_id": booking_id, "guest_id": member["guest_id"], "source": "exely_guest_roster"}):
            return False
    return True


async def reconcile_guest_roster(database, tenant_id: str, connection: dict, number: str, client) -> dict:
    from .demographics import stable_reconciliation_plan

    reservation = await database.exely_reservations.find_one({"tenant_id": tenant_id, "property_id": str(connection["hotel_code"]), "external_id": number}, {"_id": 0})
    _require(bool(reservation), "EXELY_READ_LOCAL_RESERVATION_NOT_FOUND")
    plans = await stable_reconciliation_plan(tenant_id, connection, reservation, client)
    # Validate the complete group before performing any room write.
    for plan in plans:
        primary = await database.guests.find_one({"tenant_id": tenant_id, "id": plan["booking"]["guest_id"]}, {"_id": 0})
        _require(bool(primary), "EXELY_ROSTER_PRIMARY_CHANGED")
        plan["roster"] = rest_roster(plan.get("remote_guests"), primary)
    results = []
    for plan in plans:
        manifest = await sync_room_roster(database, tenant_id, plan["booking"], plan["roster"], source="read_reservation_v1",
                                          proof=plan["proof"], connection=connection, reservation=reservation)
        results.append({"booking_id": plan["booking"]["id"], "named_guests": len(manifest["members"])})
    return {"success": True, "status": "roster_verified", "rooms": results, "provider_write_count": 0}
