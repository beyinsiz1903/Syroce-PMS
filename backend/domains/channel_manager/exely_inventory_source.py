"""Keep diagnostic/legacy ARI resends aligned with the PMS inventory source.

Inventory edits belong to the unified remaining-availability editor, which
persists net + sold and the explicit manual/automatic mode before delivery.
Other endpoints may resend that projection, but must not establish a second
provider-only allotment that the next booking event would overwrite.
"""

from datetime import date, timedelta

from fastapi import HTTPException

from .calendar_inventory import (
    exely_publishable_availability,
    get_active_bookings,
    get_room_counts,
    lock_adjusted_capacities,
)


def _reject(code, message, status=409, **context):
    raise HTTPException(status, detail={
        "error_code": code, "message": message,
        "delivery_state": "BLOCKED", "provider_write_count": 0, **context,
    })


async def assert_exely_inventory_source(database, tenant_id, updates):
    """Preflight every supplied inventory period before *any* sibling write.

    Each item uses panel or complete wire room/rate identifiers. No calendar,
    booking, lock, or provider mutation is performed here.
    """
    updates = [row for row in updates if row.get("availability") is not None]
    if not updates:
        return
    try:
        spans = [(date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])) for row in updates]
        start, end = min(a for a, _ in spans), max(b for _, b in spans)
        if any(b < a for a, b in spans) or (end - start).days > 730:
            raise ValueError("Invalid inventory window")
        if any(type(row["availability"]) is not int or not 0 <= row["availability"] <= 999 for row in updates):
            raise ValueError("Invalid inventory value")
    except (KeyError, TypeError, ValueError):
        _reject("EXELY_INVENTORY_SOURCE_INVALID", "Geçerli müsaitlik değerleri ve en fazla 731 gecelik dönem seçin.", status=422)

    try:
        mappings = await database.exely_room_mappings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(201)
        if len(mappings) >= 201:
            raise ValueError("Incomplete mappings")
        resolved = []
        for row in updates:
            pair = (str(row.get("room_type_code") or ""), str(row.get("rate_plan_code") or ""))
            matches = []
            for mapping in mappings:
                panel = (str(mapping.get("exely_room_code") or ""), str(mapping.get("exely_rate_plan_code") or ""))
                wire = (str(mapping.get("pms_api_room_code") or ""), str(mapping.get("pms_api_rate_plan_code") or ""))
                if pair == panel or (all(wire) and pair == wire):
                    matches.append(mapping)
            if len(matches) != 1 or not matches[0].get("pms_room_type") or not matches[0].get("sync_availability", True):
                _reject("EXELY_INVENTORY_SOURCE_MAPPING_REQUIRED", "Müsaitlik için tek ve açık bir oda eşleştirmesi gerekli.")
            mapping = matches[0]
            if bool(mapping.get("pms_api_room_code")) != bool(mapping.get("pms_api_rate_plan_code")):
                _reject("EXELY_INVENTORY_SOURCE_MAPPING_REQUIRED", "Oda ve tarife API kodları birlikte eşleştirilmelidir.")
            owners = [m for m in mappings if m.get("pms_room_type") == mapping["pms_room_type"] and m.get("sync_availability", True)]
            if len(owners) != 1:
                _reject("EXELY_INVENTORY_SOURCE_MAPPING_REQUIRED", "Her oda tipi için yalnız bir müsaitlik eşleştirmesi gerekli.")
            resolved.append((row, mapping))

        counts, ids = await get_room_counts(database, tenant_id)
        bookings = await get_active_bookings(database, tenant_id, start.isoformat(), end.isoformat())
        capacities = await lock_adjusted_capacities(database, tenant_id, counts, ids, bookings, start.isoformat(), end.isoformat())
        projected = {}
        for row, mapping in resolved:
            room_type = mapping["pms_room_type"]
            if room_type not in counts:
                raise ValueError("Unknown inventory category")
            owner = (mapping["exely_room_code"], mapping["exely_rate_plan_code"])
            if owner not in projected:
                canonical = {day: value for (category, day), value in capacities.items() if category == room_type}
                projected[owner] = await exely_publishable_availability(database, tenant_id, room_type, mapping, canonical)
            day, last = date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])
            while day <= last:
                expected = projected[owner][day.isoformat()]
                if row["availability"] != expected:
                    _reject(
                        "EXELY_INVENTORY_SOURCE_MISMATCH",
                        "Müsaitlik PMS takvimiyle eşleşmiyor. Kontenjanı Fiyat ve Müsaitlik ekranından güncelleyin; hiçbir veri gönderilmedi.",
                        room_type_code=owner[0], date=day.isoformat(),
                        expected_availability=expected, requested_availability=row["availability"],
                    )
                day += timedelta(days=1)
    except HTTPException:
        raise
    except Exception:
        _reject("EXELY_INVENTORY_SOURCE_UNAVAILABLE", "Güncel PMS müsaitliği doğrulanamadı; hiçbir veri gönderilmedi.", status=503)
