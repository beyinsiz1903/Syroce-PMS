"""Read-only preflight for manual sales inventory or automatic physical stock.

The legacy calendar stores base allotments. Store remaining + already sold,
but send remaining unchanged to Exely; subsequent bookings still reduce the
calendar and normal booking-event ARI by one. An explicit manual value may
oversell physical capacity; None resets the selected dates to automatic stock.
Never reinterpret unmarked legacy rows as an overbooking instruction.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException

from .calendar_inventory import booking_room_type, build_sold_count_index, get_active_bookings, get_room_counts, lock_adjusted_capacities


@dataclass(frozen=True)
class RemainingAvailabilityPlan:
    base_values: dict
    remaining_values: dict
    modes: dict


def _blocked(code, message, *, status_code=409, **context):
    raise HTTPException(status_code, detail={
        "error_code": code, "message": message, "delivery_state": "BLOCKED",
        "provider_status_class": "NOT_SENT", "provider_write_count": 0, **context,
    })


async def prepare_exely_remaining_values(database, tenant_id, pairs, room_values, start_date, end_date, selected_days):
    """Validate the entire request before any calendar or provider mutation."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if (end - start).days > 730 or end.year == 9999:
        _blocked("EXELY_REMAINING_RANGE_INVALID", "Net müsaitlik için tek gönderimde en fazla 731 gece seçin.")
    days = []
    day = start
    while day <= end:
        if selected_days is None or day.isoweekday() % 7 in selected_days:
            days.append(day.isoformat())
        day += timedelta(days=1)
    if not days or not pairs or len(pairs) != len(set(pairs)):
        _blocked("EXELY_REMAINING_SELECTION_INVALID", "En az bir hedef gece ve benzersiz oda/tarife seçin.")

    try:
        mappings, (counts, ids), bookings = await asyncio.gather(
            database.exely_room_mappings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(201),
            get_room_counts(database, tenant_id),
            get_active_bookings(database, tenant_id, start_date, end_date),
        )
    except Exception:
        _blocked("EXELY_REMAINING_INVENTORY_UNAVAILABLE", "Güncel envanter okunamadı; hiçbir kayıt değiştirilmedi.", status_code=503)
    if len(mappings) >= 201 or sum(v["total"] for v in counts.values()) >= 500 or len(bookings) >= 10000:
        _blocked("EXELY_REMAINING_INVENTORY_INCOMPLETE", "Oda ve rezervasyon verileri eksiksiz doğrulanamadı; hiçbir kayıt değiştirilmedi.")
    types = {}
    availability_owners = set()
    for room, rate in pairs:
        exact = [m for m in mappings if str(m.get("exely_room_code")) == room and str(m.get("exely_rate_plan_code")) == rate]
        if len(exact) != 1 or not exact[0].get("pms_room_type"):
            _blocked("EXELY_REMAINING_MAPPING_REQUIRED", "Seçili oda/tarife için tek ve açık bir PMS eşleştirmesi gerekli.", room_type_code=room)
        mapping = exact[0]
        room_type = mapping["pms_room_type"]
        if room_type not in counts or (room in types and types[room] != room_type):
            _blocked("EXELY_REMAINING_MAPPING_REQUIRED", "Oda eşleştirmesi fiziksel PMS kategorisiyle doğrulanamadı.", room_type_code=room)
        api_room = bool(str(mapping.get("pms_api_room_code") or "").strip())
        api_rate = bool(str(mapping.get("pms_api_rate_plan_code") or "").strip())
        if api_room != api_rate:
            _blocked("EXELY_PARTIAL_API_PAIR", "Oda ve tarife API kodları birlikte eşleştirilmelidir.")
        types[room] = room_type
        if mapping.get("sync_availability", True):
            availability_owners.add(room)
    if set(types) != availability_owners or not set(types).issubset(room_values):
        _blocked("EXELY_REMAINING_SYNC_REQUIRED", "Her oda için müsaitlik eşleştirmesi açık bir tarife seçin.")
    for room in types:
        owners = [m for m in mappings if str(m.get("exely_room_code")) == room and m.get("sync_availability", True)]
        if len(owners) != 1:
            _blocked("EXELY_REMAINING_SYNC_REQUIRED", "Her oda için yalnız bir müsaitlik tarifesi eşleştirilmelidir.")
    by_id = {rid: room_type for room_type, room_ids in ids.items() for rid in room_ids}
    if len(by_id) != sum(v["total"] for v in counts.values()):
        _blocked("EXELY_REMAINING_INVENTORY_INCOMPLETE", "Fiziksel oda listesi tutarlı değil; hiçbir kayıt değiştirilmedi.")
    for booking in bookings:
        if booking_room_type(booking, by_id, ids) not in types.values():
            continue
        try:
            check_in = datetime.strptime(booking["check_in"][:10], "%Y-%m-%d").date()
            check_out = datetime.strptime(booking["check_out"][:10], "%Y-%m-%d").date()
            if check_out <= check_in:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            _blocked("EXELY_REMAINING_INVENTORY_INCOMPLETE", "Rezervasyon tarihleri doğrulanamadı; hiçbir kayıt değiştirilmedi.")
    automatic_types = {room_type for room, room_type in types.items() if room_values[room] is None}
    automatic_capacities = {}
    if automatic_types:
        try:
            automatic_capacities = await lock_adjusted_capacities(
                database, tenant_id, {t: counts[t] for t in automatic_types},
                {t: ids[t] for t in automatic_types}, bookings, start_date, end_date,
            )
        except Exception:
            _blocked("EXELY_REMAINING_INVENTORY_UNAVAILABLE", "Otomatik müsaitlik için güncel oda-gece kapasitesi doğrulanamadı; hiçbir kayıt değiştirilmedi.", status_code=503)
    sold = build_sold_count_index(ids, bookings, start_date, end_date)
    base_values, remaining_values, modes = {}, {}, {}
    for room, room_type in types.items():
        net = room_values[room]
        if net is not None and (type(net) is not int or not 0 <= net <= 999):
            _blocked("EXELY_REMAINING_VALUE_INVALID", "Net müsaitlik sıfır veya pozitif tam sayı olmalıdır.")
        modes[room] = "automatic" if net is None else "manual_remaining"
        for day in days:
            key = (room_type, day)
            consumed = sold.get(key, 0)
            # Explicitly entered sales stock is an operator override, NOT a
            # physical room assignment. Preserve booking/OOO locks unchanged.
            base_values[(room, day)] = None if net is None else net + consumed
            remaining_values[(room, day)] = automatic_capacities[key] if net is None else net
    return RemainingAvailabilityPlan(base_values, remaining_values, modes)
