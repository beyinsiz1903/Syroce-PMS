"""Validated, versioned planning settings. Not a reservation/rate-channel engine."""
import hashlib
import json
import math

from fastapi import HTTPException

SECTIONS = {"hurdle_rates", "day_pricing", "overbooking"}
DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
COMPENSATIONS = {"upgrade_nearby", "cash", "free_night", "combo"}
DEFAULTS = {"hurdle_rates": {}, "day_pricing": {}, "overbooking": {
    "enabled": False, "max_percentage": 5, "walk_compensation": "upgrade_nearby", "walk_amount": 0}}


def invalid():
    raise HTTPException(400, "Gelir planlama alanları geçersiz; negatif/kesirli sınırları ve oda tipini kontrol edin.")


def number(value, maximum=1_000_000_000, integer=False, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        invalid()
    if not minimum <= value <= maximum or (integer and int(value) != value):
        invalid()
    return int(value) if integer else value


def fields(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        invalid()


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def snapshot(doc):
    values = {key: (doc or {}).get(key, DEFAULTS[key]) for key in SECTIONS}
    return {**values, "section_revisions": {key: revision(value) for key, value in values.items()},
            "application_mode": "planning_only", "automatic_enforcement": False}


def physical_types(rooms):
    return {str(room.get("room_type_id") or room.get("type_id") or room.get("room_type") or room.get("type") or "").strip()
            for room in rooms if room.get("is_active") is not False and not room.get("is_virtual")} - {""}


def validate_patch(body, room_types):
    if not isinstance(body, dict) or set(body) - SECTIONS - {"expected_revisions"}:
        invalid()
    selected = set(body) & SECTIONS
    if not selected:
        invalid()
    expected = body.get("expected_revisions")
    if not isinstance(expected, dict) or set(expected) != selected or any(not isinstance(v, str) or len(v) != 64 for v in expected.values()):
        raise HTTPException(409, "Ayarları yeniden yükleyin; bölüm sürümü zorunludur.")
    for section in selected:
        value = body[section]
        if section == "overbooking":
            fields(value, DEFAULTS[section])
            if not isinstance(value["enabled"], bool) or not isinstance(value["walk_compensation"], str) or value["walk_compensation"] not in COMPENSATIONS:
                invalid()
            number(value["max_percentage"], maximum=20, integer=True)
            number(value["walk_amount"])
        else:
            if not isinstance(value, dict) or not value or set(value) - room_types or len(value) > 200:
                invalid()
            for row in value.values():
                if section == "hurdle_rates":
                    fields(row, {"min_rate", "bar", "active"})
                    number(row["min_rate"])
                    number(row["bar"])
                    if not isinstance(row["active"], bool):
                        invalid()
                else:
                    if not isinstance(row, dict) or not row or set(row) - DAYS:
                        invalid()
                    for day in row.values():
                        fields(day, {"rate", "min_stay"})
                        number(day["rate"])
                        number(day["min_stay"], maximum=365, minimum=1, integer=True)
    return {key: body[key] for key in selected}, expected


def validate_walk(body, room_types):
    fields(body, {"guest_name", "room_type", "compensation_type", "compensation_amount", "nearby_hotel", "notes", "request_id"})
    for key, maximum in (("guest_name", 200), ("room_type", 200), ("nearby_hotel", 200), ("notes", 2000), ("request_id", 64)):
        if not isinstance(body[key], str) or len(body[key]) > maximum:
            invalid()
    if not body["guest_name"].strip() or not body["request_id"].strip() or body["room_type"] not in room_types:
        invalid()
    if not isinstance(body["compensation_type"], str) or body["compensation_type"] not in COMPENSATIONS:
        invalid()
    number(body["compensation_amount"])
    return {key: value.strip() if isinstance(value, str) else value for key, value in body.items()}
