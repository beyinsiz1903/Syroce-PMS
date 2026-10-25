"""Read-only, tenant-scoped mapping exceptions (not accepted PMS arrivals).

Legacy booking holds and current provider/import inboxes describe the same
exception. Group their identities for display; never cancel/delete a duplicate,
invent a room, acknowledge delivery or mark a guest no-show here.
"""

from datetime import date, datetime

from core.database import db

TERMINAL = {"cancelled", "canceled", "checked_out", "no_show", "resolved"}
HOLD_SOURCE = "ota_unmatched_hold"


def is_mapping_hold(row: dict) -> bool:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    return bool(
        row.get("status") == "pending_mapping"
        or row.get("booking_source") == HOLD_SOURCE
        or row.get("allocation_source") == HOLD_SOURCE
        or source.get("kind") == HOLD_SOURCE
        or row.get("is_inventory_hold") is True
    )


def _day(value) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    try:
        return date.fromisoformat(str(value or "")[:10]).isoformat()
    except ValueError:
        return None


def group_mapping_issues(records: list[tuple[str, dict]], business_date: str | None = None) -> list[dict]:
    from modules.pms_core.demo_source_remediation import is_archived_demo
    groups: dict[tuple[str, str, str], dict] = {}
    for origin, row in records:
        if is_archived_demo(row):
            continue  # Explicit, preserved synthetic archive, not a stay/cancellation.
        if str(row.get("status") or row.get("state") or "").lower() in TERMINAL:
            continue
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        provider = str(row.get("provider") or source.get("provider") or row.get("source_provider") or "unknown").lower()
        external_id = str(row.get("external_reservation_id") or row.get("external_id") or row.get("hr_number") or "")
        property_id = str(row.get("property_id") or row.get("tenant_id") or "")
        # Without a source identity, do not guess that two guests are duplicates.
        key = (property_id, provider, external_id or f"{origin}:{row.get('id')}")
        arrival = row.get("check_in") or row.get("checkin_date") or row.get("arrival_date")
        issue = groups.setdefault(key, {
            "id": f"mapping:{property_id}:{provider}:{key[2]}",
            "queue_kind": "mapping_required", "provider": provider,
            "property_id": property_id, "external_reservation_id": external_id,
            "guest_name": row.get("guest_name") or "Misafir",
            "check_in": arrival,
            "check_out": row.get("check_out") or row.get("checkout_date") or row.get("departure_date"),
            "status": "pending_mapping", "room_id": None,
            "provider_room_code": row.get("provider_room_code") or row.get("room_type_code"),
            "provider_rate_code": row.get("provider_rate_code") or row.get("rate_plan_code"),
            "booking_ids": [], "source_records": [],
            "action_url": f"/{provider}" if provider in {"exely", "hotelrunner"} else "/channel-manager",
        })
        issue["source_records"].append({"collection": origin, "id": row.get("id")})
        if origin == "bookings" and row.get("id") not in issue["booking_ids"]:
            issue["booking_ids"].append(row.get("id"))
        # A conflicting or invalid date must not make an exception disappear.
        candidate_day = _day(arrival)
        prior_day = _day(issue["check_in"])
        if not candidate_day or (prior_day and candidate_day < prior_day):
            issue["check_in"] = arrival
        rooms = row.get("rooms") or []
        if rooms and isinstance(rooms[0], dict):
            issue["provider_room_code"] = issue["provider_room_code"] or rooms[0].get("room_type_code")
            issue["provider_rate_code"] = issue["provider_rate_code"] or rooms[0].get("rate_plan_code")
    for issue in groups.values():
        arrival = _day(issue["check_in"])
        issue["invalid_arrival_date"] = arrival is None
        issue["blocks_close"] = bool(business_date and (not arrival or arrival <= business_date))
        issue["duplicate_hold_count"] = max(0, len(issue["booking_ids"]) - 1)
    return sorted(groups.values(), key=lambda item: (str(item.get("check_in") or ""), item["id"]))


async def load_mapping_issues(tenant_id: str, business_date: str | None = None, *, database=None) -> list[dict]:
    database = database if database is not None else db
    # Projection intentionally excludes contacts, identity documents, raw
    # provider payloads, credentials and any financial amount/guest balance.
    projection = {"_id": 0, **dict.fromkeys([
        "id", "tenant_id", "property_id", "provider", "source.provider", "source.kind", "source_provider",
        "external_reservation_id", "external_id", "hr_number", "guest_name", "check_in", "check_out",
        "checkin_date", "checkout_date", "arrival_date", "departure_date", "status", "state", "pms_status", "demo_reconstruction",
        "provider_room_code", "provider_rate_code", "room_type_code", "rate_plan_code",
        "rooms.room_type_code", "rooms.rate_plan_code",
    ], 1)}
    queries = {
        "bookings": {"status": {"$nin": sorted(TERMINAL)}, "$or": [
            {"status": "pending_mapping"}, {"booking_source": HOLD_SOURCE},
            {"source.kind": HOLD_SOURCE}, {"allocation_source": HOLD_SOURCE}, {"is_inventory_hold": True},
        ]},
        "exely_reservations": {"pms_status": "pending_mapping", "state": {"$nin": sorted(TERMINAL)}},
        "hotelrunner_reservations": {"pms_status": "pending_mapping", "state": {"$nin": sorted(TERMINAL)}},
        "imported_reservations": {"import_status": "review_required", "review_reason": {"$in": ["unmapped_room_type", "unmapped_rate_plan"]}, "status": {"$nin": sorted(TERMINAL)}},
    }
    records = []
    for collection, query in queries.items():
        async for row in database[collection].find({"tenant_id": tenant_id, **query}, projection):
            records.append((collection, row))
    return group_mapping_issues(records, business_date)


def mapping_close_blocker(issues: list[dict]) -> dict | None:
    due = [item for item in issues if item["blocks_close"]]
    if not due:
        return None
    return {
        "category": "unresolved_channel_mapping", "label": "Kanal rezervasyonu eşleştirmesi bekliyor",
        "message": (f"{len(due)} kanal rezervasyonunun geliş tarihi geldi/geçti veya tarihi geçersiz. "
                    "Oda/fiyat eşleştirmesini ve kaynak durumunu inceleyin. Bunlar kabul edilmiş PMS gelişleri değildir; otomatik No-Show uygulanmaz. Gün sonu bu sorun çözülmeden kapatılamaz."),
        "count": len(due), "items": due[:25], "action": "review_channel_mapping", "bypassable": False,
    }
