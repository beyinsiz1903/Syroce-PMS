"""One room/property boundary for canonical and legacy single-property stays."""


def room_property_id(tenant_id, room, booking=None):
    booking = booking or {}
    if any(row.get("tenant_id") not in (None, tenant_id) for row in (room, booking)):
        return None
    if booking.get("room_id") and room.get("id") and booking["room_id"] != room["id"]:
        return None
    room_id, booking_id = room.get("property_id"), booking.get("property_id")
    if room_id and booking_id and room_id != booking_id:
        return None
    # This is the existing QR-session canonical key, not an arbitrary property.
    return room_id or booking_id or tenant_id


async def guest_property_context(db, tenant_id, property_id, session=None):
    """Read existing property metadata, or the exact legacy tenant's settings.

    No property record is manufactured. A missing/foreign explicit property
    never falls back to some other property in the tenant or database.
    """
    kwargs = {"session": session} if session is not None else {}
    prop = await db["properties"].find_one({"id": property_id, "tenant_id": tenant_id}, **kwargs)
    if prop:
        return prop
    if property_id != tenant_id:
        return None
    tenant = await db["tenants"].find_one({"id": tenant_id}, **kwargs)
    if not tenant or tenant.get("tenant_id") not in (None, tenant_id):
        return None
    # A configured explicit property is authoritative; don't silently create a
    # second legacy catalogue when that configured property is missing.
    if tenant.get("property_id") not in (None, "", tenant_id):
        return None
    settings = await db["hotel_settings"].find_one({"tenant_id": tenant_id}, **kwargs) or {}
    result = {"id": tenant_id, "tenant_id": tenant_id, "scope": "legacy_single_property"}
    for field in ("property_name", "name", "display_name", "logo_url", "logo", "primary_color", "timezone", "default_language", "checkout_time", "currency"):
        value = settings.get(field) or tenant.get(field)
        if value is not None:
            result[field] = value
    return result
