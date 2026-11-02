"""Read-only, tenant/person-scoped KBS preflight. Never calls an authority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from core.kbs_payload_builder import build_kbs_payload_snapshot
from core.kbs_payload_validation import validate_kbs_payload


def identity_issues(payload: dict, action: str = "checkin") -> list[str]:
    # Reuse the actual transport contract rather than guessing TC/passport
    # requirements in every reservation client. No credentials/network used.
    from core.kbs_jandarma import JandarmaError, _country, _date

    _, missing = validate_kbs_payload({**payload, "room_number": "preflight", "check_in": "2000-01-01", "check_out": "2000-01-02"}, action)
    from core.kbs_payload_validation import _is_foreign_identity_card, _is_turkish_nationality

    if action == "checkin" and not _is_turkish_nationality(payload.get("nationality")) and not _is_foreign_identity_card(payload.get("id_type")):
        if len(str(payload.get("guest_name") or "").split()) < 2 and "guest_name" not in missing:
            missing.append("guest_name")
        if str(payload.get("gender") or "").upper() not in {"F", "FEMALE", "K", "KADIN", "M", "MALE", "E", "ERKEK"} and "gender" not in missing:
            missing.append("gender")
        if payload.get("birth_date"):
            try:
                parsed = datetime.fromisoformat(_date(payload["birth_date"]))
                if parsed > datetime.now(UTC):
                    raise ValueError("future birth date")
            except (JandarmaError, ValueError):
                missing.append("birth_date_invalid")
        try:
            _country(payload.get("nationality"))
        except JandarmaError:
            missing.append("nationality_unsupported")
    return sorted(set(missing))


async def booking_readiness(database, tenant_id: str, booking_id: str, action: str = "checkin") -> dict:
    booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    links = await database.booking_guests.find({"tenant_id": tenant_id, "booking_id": booking_id}, {"_id": 0}).to_list(None)
    ids = list(dict.fromkeys([booking.get("guest_id"), *(r.get("guest_id") for r in links if not r.get("checkout_date"))]))
    ids = [gid for gid in ids if gid]
    guests = []
    for gid in ids:
        _, guest, payload = await build_kbs_payload_snapshot(database, tenant_id, booking_id, gid)
        missing = identity_issues(payload, action)
        if not guest:
            missing.append("guest_record")
        guests.append({"guest_id": gid, "guest_name": payload.get("guest_name") or "Misafir", "ready": not missing, "missing_fields": missing})
    expected = max(1, int(booking.get("adults") or 0) + int(booking.get("children") or 0))
    unregistered = max(0, expected - len(ids))
    config = await database.kbs_cloud_configs.find_one({"tenant_id": tenant_id, "id": "kbs_cloud_jandarma"}, {"_id": 1})
    return {
        "booking_id": booking_id,
        "action": action,
        "ready": bool(guests) and not unregistered and all(g["ready"] for g in guests),
        "enforced_at_checkin": bool(config),
        "expected_occupants": expected,
        "unregistered_occupants": unregistered,
        "guests": guests,
    }


async def checkin_confirmed(database, job: dict) -> bool:
    query = {"tenant_id": job["tenant_id"], "id": job["booking_id"]}
    booking = await database.bookings.find_one(query, {"_id": 0, "guest_id": 1, "kbs_reported": 1, "kbs_test": 1}) or {}
    guest_id = job.get("guest_id") or booking.get("guest_id")
    receipt = await database.kbs_reports.find_one(
        {"tenant_id": job["tenant_id"], "_kind": "queue_job", "booking_id": job["booking_id"], "guest_id": guest_id, "action": "checkin", "status": "done", "kbs_test": {"$ne": True}}, {"_id": 1}
    )
    return bool(receipt) or (guest_id == booking.get("guest_id") and bool(booking.get("kbs_reported")) and not booking.get("kbs_test"))


async def defer_checkout(database, job: dict) -> bool:
    """Park only this checkout until its OWN guest's check-in is accepted."""
    if job.get("action") != "checkout" or await checkin_confirmed(database, job):
        return False
    now = datetime.now(UTC)
    await database.kbs_reports.update_one(
        {"tenant_id": job["tenant_id"], "_kind": "queue_job", "id": job["id"], "status": "in_progress", "worker_id": job.get("worker_id")},
        {
            "$set": {
                "status": "pending",
                "awaiting_checkin": True,
                "last_error": "awaiting_checkin_confirmation",
                "worker_id": None,
                "leased_until": None,
                "next_retry_at": (now + timedelta(seconds=60)).isoformat(),
                "updated_at": now.isoformat(),
            },
            "$inc": {"attempts": -1},
        },
    )
    return True
