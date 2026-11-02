"""Two operational views; expiry hides PII, NEVER deletes jobs or receipts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from core.kbs_payload_builder import build_kbs_payload_snapshot
from core.kbs_readiness import identity_issues

VISIBILITY_HOURS = 24


def as_utc(value, timezone: str = "Europe/Istanbul") -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
        return parsed.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def visible_stay(booking: dict, now: datetime, *, guest_checkout=None, timezone="Europe/Istanbul") -> bool:
    if booking.get("status") not in {"checked_in", "checked_out"}:
        return False
    if guest_checkout:
        departure = as_utc(guest_checkout, timezone)
    elif booking.get("status") == "checked_in":
        return True  # An overdue planned departure is NOT a real checkout.
    else:
        departure = as_utc(booking.get("checked_out_at") or booking.get("check_out"), timezone)
    # Legacy rows with no usable departure must not expose names forever.
    return departure is not None and departure + timedelta(hours=VISIBILITY_HOURS) > now


def delivery_reason(job: dict | None, missing: list[str]) -> str:
    job = job or {}
    error = str(job.get("last_error") or "").lower()
    if job.get("delivery_uncertain"):
        return "delivery_uncertain"
    if "already_registered" in error or "müşteri tesiste zaten kayıtlı" in error or "musteri tesiste zaten kayitli" in error:
        return "already_registered"
    if job.get("status") == "done" and not job.get("kbs_test"):
        return "accepted"
    if missing:
        return "missing_data"
    if job.get("awaiting_checkin") or error == "awaiting_checkin_confirmation":
        return "awaiting_checkin"
    if job.get("kbs_test"):
        return "test_only"
    if job.get("status") in {"dead", "failed"}:
        return "authority_rejected"
    return "processing" if job.get("status") == "in_progress" else "awaiting_delivery"


async def operational_notifications(database, tenant_id: str, *, now=None, booking_id=None) -> dict:
    """Canonical per-person/action projection, including missing-data non-jobs.

    A rejected job never erases a durable successful receipt. Historical hidden
    failures remain in the dispatch queue; only an anonymous count is returned.
    This endpoint cannot export identity numbers or transport bodies.
    """
    now = now or datetime.now(UTC)
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "timezone": 1}) or {}
    timezone = settings.get("timezone") or "Europe/Istanbul"
    try:
        ZoneInfo(timezone)
    except (ValueError, KeyError):
        timezone = "Europe/Istanbul"
    query = {"tenant_id": tenant_id, "status": {"$in": ["checked_in", "checked_out"]}}
    if booking_id:
        query["id"] = booking_id
    bookings = await database.bookings.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "guest_id": 1,
            "room_number": 1,
            "status": 1,
            "check_out": 1,
            "checked_out_at": 1,
            "adults": 1,
            "children": 1,
            "kbs_reported": 1,
            "kbs_test": 1,
            "kbs_checkout_reported": 1,
            "kbs_checkout_test": 1,
            "kbs_reported_at": 1,
            "kbs_checkout_reported_at": 1,
        },
    ).to_list(None)
    booking_ids = [b["id"] for b in bookings]
    links_by_booking = {}
    jobs_by_booking = {}
    if booking_ids:
        async for link in database.booking_guests.find({"tenant_id": tenant_id, "booking_id": {"$in": booking_ids}}, {"_id": 0, "booking_id": 1, "guest_id": 1, "checkout_date": 1}):
            links_by_booking.setdefault(link["booking_id"], []).append(link)
        async for row in database.kbs_reports.find(
            {"tenant_id": tenant_id, "_kind": "queue_job", "booking_id": {"$in": booking_ids}},
            {
                "_id": 0,
                "id": 1,
                "booking_id": 1,
                "guest_id": 1,
                "action": 1,
                "status": 1,
                "kbs_test": 1,
                "delivery_uncertain": 1,
                "awaiting_checkin": 1,
                "last_error": 1,
                "created_at": 1,
                "completed_at": 1,
            },
        ).sort("created_at", -1):
            jobs_by_booking.setdefault(row["booking_id"], []).append(row)
    items = []
    hidden_unresolved = 0
    for booking in bookings:
        bid = booking["id"]
        links = links_by_booking.get(bid, [])
        occupants = {booking.get("guest_id"): None}
        occupants.update({r["guest_id"]: r for r in links if r.get("guest_id") and r["guest_id"] != booking.get("guest_id")})
        jobs = jobs_by_booking.get(bid, [])
        for gid, link in occupants.items():
            guest_checkout = (link or {}).get("checkout_date")
            visible = visible_stay(booking, now, guest_checkout=guest_checkout, timezone=timezone)
            guest = payload = None
            if visible:
                _, guest, payload = await build_kbs_payload_snapshot(database, tenant_id, bid, gid)
            actions = ["checkin", "checkout"] if booking["status"] == "checked_out" or guest_checkout else ["checkin"]
            for action in actions:
                candidates = [r for r in jobs if (r.get("guest_id") or booking.get("guest_id")) == gid and r.get("action") == action]
                accepted = next((r for r in candidates if r.get("status") == "done" and not r.get("kbs_test")), None)
                legacy = (
                    gid == booking.get("guest_id")
                    and bool(booking.get("kbs_checkout_reported" if action == "checkout" else "kbs_reported"))
                    and not booking.get("kbs_checkout_test" if action == "checkout" else "kbs_test")
                )
                job = accepted or (candidates[0] if candidates else {})
                sent = bool(accepted or legacy)
                if not visible:
                    hidden_unresolved += int(not sent)
                    continue
                missing = identity_issues(payload, action) if guest else ["guest_record"]
                reason = "accepted" if sent else delivery_reason(job, missing)
                items.append(
                    {
                        "id": job.get("id") or f"{bid}:{gid or 'missing'}:{action}",
                        "booking_id": bid,
                        "guest_id": gid,
                        "guest_name": payload.get("guest_name") or "Misafir",
                        "room_number": payload.get("room_number"),
                        "action": action,
                        "nationality": payload.get("nationality"),
                        "id_type": payload.get("id_type"),
                        "delivery_group": "sent" if sent else "not_sent",
                        "status": "done" if sent else job.get("status", "not_enqueued"),
                        "status_reason": reason,
                        "missing_fields": missing if not sent else [],
                        "delivery_uncertain": bool(job.get("delivery_uncertain")),
                        "can_retry": bool(job.get("id")) and reason == "authority_rejected",
                        "created_at": job.get("created_at"),
                        "completed_at": job.get("completed_at") or booking.get("kbs_checkout_reported_at" if action == "checkout" else "kbs_reported_at") if sent else None,
                        "kbs_test": bool(job.get("kbs_test")) and not sent,
                    }
                )
        if visible_stay(booking, now, timezone=timezone) and booking["status"] == "checked_in":
            expected = max(1, int(booking.get("adults") or 0) + int(booking.get("children") or 0))
            absent = max(0, expected - len([gid for gid in occupants if gid]))
            if absent:
                items.append(
                    {
                        "id": f"{bid}:unregistered",
                        "booking_id": bid,
                        "guest_id": None,
                        "guest_name": f"{absent} konaklayan kaydı eksik",
                        "room_number": booking.get("room_number"),
                        "action": "checkin",
                        "delivery_group": "not_sent",
                        "status": "not_enqueued",
                        "status_reason": "missing_data",
                        "missing_fields": ["guest_record"],
                        "can_retry": False,
                        "delivery_uncertain": False,
                        "kbs_test": False,
                    }
                )
    items.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"items": items, "hidden_unresolved_count": hidden_unresolved, "visibility_hours": VISIBILITY_HOURS}
