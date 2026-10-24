"""Tenant catalog based room-type labels; never expose an orphan UUID as a name."""
import re

UUID = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.I)


class RoomTypeLabels:
    def __init__(self, catalog=(), rooms=()):
        self.ids, candidates = {}, {}
        for row in catalog:
            name = str(row.get("name") or row.get("room_type_name") or row.get("type_name") or "").strip()
            if name and row.get("id"):
                self.ids[str(row["id"])] = name
                candidates.setdefault(name.casefold(), set()).add(name)
        self.names = {key: next(iter(names)) for key, names in candidates.items() if len(names) == 1}
        unknown = sorted({str(row.get("room_type_id") or row.get("room_type")) for row in rooms
            if UUID.match(str(row.get("room_type_id") or row.get("room_type") or ""))
            and str(row.get("room_type_id") or row.get("room_type")) not in self.ids})
        self.unknown = {key: f"Eşleştirilmemiş oda tipi {index + 1}" for index, key in enumerate(unknown)}
        # Without a catalog, normalize case variants deterministically. A
        # catalog with genuinely different names remains authoritative.
        for row in rooms:
            name = str(row.get("room_type") or "").strip()
            if name and not UUID.match(name) and (name.casefold() not in candidates or len(candidates[name.casefold()]) == 1):
                self.names.setdefault(name.casefold(), name[:1].upper() + name[1:])

    def __call__(self, value):
        raw = str(value or "").strip()
        if raw in self.ids:
            return self.ids[raw]
        if UUID.match(raw):
            return self.unknown.get(raw, "Envanter dışı oda tipi")
        return self.names.get(raw.casefold(), raw or "Eşleştirilmemiş")

    def normalize(self, rows):
        return [{**row, "room_type": self(row.get("room_type_id") or row.get("room_type"))}
            if row.get("room_type_id") or row.get("room_type") else dict(row) for row in rows]


async def load_room_type_labels(database, tenant_id, rooms=()):
    collection = getattr(database, "room_types", None)
    catalog = await collection.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "name": 1, "room_type_name": 1, "type_name": 1}).to_list(None) if collection is not None else []
    return RoomTypeLabels(catalog, rooms)


async def room_revenue_by_type(charges, tenant_id, *, database):
    from modules.pms_core.report_money import add_amount, rounded_totals
    from modules.pms_core.reporting_ledger import charge_amount, charge_category

    bookings_collection = getattr(database, "bookings", None)
    folios_collection = getattr(database, "folios", None)
    folio_ids = sorted({str(row["folio_id"]) for row in charges if row.get("folio_id") and not row.get("booking_id")})
    folios = await folios_collection.find({"tenant_id": tenant_id, "id": {"$in": folio_ids}}, {"_id": 0, "id": 1, "booking_id": 1}).to_list(None) if folio_ids and folios_collection is not None else []
    folio_bookings = {str(row["id"]): row.get("booking_id") for row in folios}
    ids = {str(row.get("booking_id") or folio_bookings.get(str(row.get("folio_id")))) for row in charges if row.get("booking_id") or folio_bookings.get(str(row.get("folio_id")))}
    bookings = await bookings_collection.find({"tenant_id": tenant_id, "id": {"$in": sorted(ids)}}, {"_id": 0, "id": 1, "room_id": 1, "room_type": 1, "room_type_id": 1}).to_list(None) if ids and bookings_collection is not None else []
    by_id = {str(row["id"]): row for row in bookings}
    rooms_collection = getattr(database, "rooms", None)
    rooms = await rooms_collection.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "room_type": 1, "room_type_id": 1}).to_list(None) if rooms_collection is not None else []
    room_map = {str(row["id"]): row for row in rooms}
    labels = await load_room_type_labels(database, tenant_id, rooms)
    totals = {}
    for charge in charges:
        if charge_category(charge) != "room":
            continue
        booking = by_id.get(str(charge.get("booking_id") or folio_bookings.get(str(charge.get("folio_id")))), {})
        room = room_map.get(str(booking.get("room_id")), {})
        label = labels(booking.get("room_type_id") or booking.get("room_type") or room.get("room_type_id") or room.get("room_type"))
        add_amount(totals.setdefault(label, {}), charge.get("currency"), charge_amount(charge))
    return [{"name": label, "revenue_by_currency": rounded_totals(values)} for label, values in sorted(totals.items())]
