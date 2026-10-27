"""Read-only service-time projection from tenant-scoped source documents.

Posting timestamps/business dates are not proof of when a service happened.
Never backfill financial documents or invent an unrecorded service time.
"""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


async def project_service_times(database, tenant_id, charges):
    sources = (
        ("source_spa_appointment_id", "spa_appointments", "starts_at", "spa_appointment"),
        ("source_pos_order_id", "pos_orders", "created_at", "pos_order"),
    )
    pending = [row for row in charges if not row.get("service_date")]
    if not any(row.get(field) for row in pending for field, *_ in sources):
        return
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "timezone": 1})
    zone_name = str((settings or {}).get("timezone") or "Europe/Istanbul")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone_name, zone = "UTC", UTC
    for field, collection, instant_field, source in sources:
        ids = {row[field] for row in pending if row.get(field)}
        if not ids:
            continue
        records = await database[collection].find(
            {"tenant_id": tenant_id, "id": {"$in": list(ids)}}, {"_id": 0, "id": 1, instant_field: 1}
        ).to_list(len(ids))
        by_id = {row["id"]: row.get(instant_field) for row in records}
        for row in pending:
            value = by_id.get(row.get(field))
            if not value or row.get("service_date"):
                continue
            try:
                instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if instant.tzinfo is None:
                    instant = instant.replace(tzinfo=UTC)
                local = instant.astimezone(zone)
            except (ValueError, TypeError, OverflowError):
                continue
            row.update(service_date=local.date().isoformat(), service_time=local.strftime("%H:%M"),
                       service_timezone=zone_name, service_timing_source=source)
