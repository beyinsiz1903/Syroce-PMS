"""Seed sections 5 + 5b + 6: bookings (past/current/future), folios, complaints.

Mutates ctx['rooms'] in-place (sets status occupied/dirty/cleaning) and writes
ctx['bookings'], ctx['folios'], ctx['service_complaints'].
"""
import random
from datetime import timedelta

from seed._helpers import _encrypt_doc, _now, _uuid

CHANNELS = ["direct", "booking_com", "expedia", "airbnb", "own_website"]
RATE_PLANS = ["Standard", "Best Available", "Non-Refundable", "Early Bird", "Last Minute"]


async def seed_bookings_and_folios(db, ctx):
    tenant_id = ctx["tenant_id"]
    rooms = ctx["rooms"]
    guests = ctx["guests"]

    # ── 5. Bookings (45 booking) ──────────────────────────
    bookings = []

    # Past bookings (15) - checked_out
    for _ in range(15):
        guest = random.choice(guests)
        room = random.choice(rooms)
        ci = _now() - timedelta(days=random.randint(5, 90))
        nights = random.randint(1, 7)
        co = ci + timedelta(days=nights)
        total = room["base_price"] * nights

        bookings.append({
            "id": _uuid(),
            "tenant_id": tenant_id,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "guest_name": guest["name"],
            "room_number": room["room_number"],
            "room_type": room["room_type"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "nights": nights,
            "adults": random.randint(1, 2),
            "children": random.randint(0, 2),
            "children_ages": [],
            "guests_count": random.randint(1, 3),
            "total_amount": total,
            "base_rate": room["base_price"],
            "paid_amount": total,
            "status": "checked_out",
            "channel": random.choice(CHANNELS),
            "source_channel": "direct",
            "origin": "ui",
            "hold_status": "none",
            "allocation_source": "manual",
            "rate_plan": random.choice(RATE_PLANS),
            "special_requests": None,
            "group_booking_id": None,
            "company_id": None,
            "created_at": (ci - timedelta(days=random.randint(1, 30))).isoformat(),
        })

    # Current bookings (10) - checked_in → mark rooms as occupied
    occupied_rooms = random.sample(rooms, min(10, len(rooms)))
    for idx, room in enumerate(occupied_rooms):
        guest = random.choice(guests)
        ci = _now() - timedelta(days=random.randint(0, 3))
        nights = random.randint(2, 7)
        co = ci + timedelta(days=nights)
        total = room["base_price"] * nights
        bid = _uuid()

        room["status"] = "occupied"
        room["current_booking_id"] = bid

        bookings.append({
            "id": bid,
            "tenant_id": tenant_id,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "guest_name": guest["name"],
            "room_number": room["room_number"],
            "room_type": room["room_type"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "nights": nights,
            "adults": random.randint(1, 2),
            "children": random.randint(0, 1),
            "children_ages": [],
            "guests_count": random.randint(1, 3),
            "total_amount": total,
            "base_rate": room["base_price"],
            "paid_amount": round(total * random.uniform(0.5, 1.0), 2),
            "status": "checked_in",
            "channel": random.choice(CHANNELS),
            "source_channel": "direct",
            "origin": "ui",
            "hold_status": "none",
            "allocation_source": "manual",
            "rate_plan": random.choice(RATE_PLANS),
            "special_requests": random.choice([None, "High floor", "Extra pillows", "Late check-out"]),
            "group_booking_id": None,
            "company_id": None,
            "created_at": (ci - timedelta(days=random.randint(1, 60))).isoformat(),
        })

    # Future bookings (20) - confirmed
    for _ in range(20):
        guest = random.choice(guests)
        room = random.choice(rooms)
        ci = _now() + timedelta(days=random.randint(1, 90))
        nights = random.randint(1, 7)
        co = ci + timedelta(days=nights)
        total = room["base_price"] * nights

        bookings.append({
            "id": _uuid(),
            "tenant_id": tenant_id,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "guest_name": guest["name"],
            "room_number": room["room_number"],
            "room_type": room["room_type"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "nights": nights,
            "adults": random.randint(1, 2),
            "children": random.randint(0, 2),
            "children_ages": [],
            "guests_count": random.randint(1, 3),
            "total_amount": total,
            "base_rate": room["base_price"],
            "paid_amount": round(total * random.uniform(0, 0.5), 2),
            "status": "confirmed",
            "channel": random.choice(CHANNELS),
            "source_channel": "direct",
            "origin": "ui",
            "hold_status": "none",
            "allocation_source": "manual",
            "rate_plan": random.choice(RATE_PLANS),
            "special_requests": None,
            "group_booking_id": None,
            "company_id": None,
            "created_at": (_now() - timedelta(days=random.randint(0, 30))).isoformat(),
        })

    bookings = [_encrypt_doc(b, "bookings") for b in bookings]
    await db.bookings.insert_many(bookings)

    # Update occupied room statuses in DB
    for room in occupied_rooms:
        await db.rooms.update_one(
            {"id": room["id"]},
            {"$set": {"status": "occupied", "current_booking_id": room["current_booking_id"]}}
        )

    # Mark a few rooms as dirty/cleaning
    dirty_rooms = random.sample([r for r in rooms if r["status"] == "available"], min(4, len(rooms)))
    for room in dirty_rooms:
        new_status = random.choice(["dirty", "cleaning"])
        await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": new_status}})
        room["status"] = new_status

    ctx["bookings"] = bookings

    # ── 5b. Service Complaints (linked to rooms/guests/bookings) ────
    complaint_categories = ["room", "service", "cleanliness", "fnb", "noise", "maintenance"]
    complaint_severities = ["low", "medium", "high", "critical"]
    complaint_subjects = {
        "room": ["Klima calismiyor", "Sicak su yok", "TV bozuk", "Oda kokuyor", "Yatak rahatsiz"],
        "service": ["Check-in cok yavas", "Personel ilgisiz", "Room service gec geldi", "Bilgi yanlis verildi", "Bagaj kayboldu"],
        "cleanliness": ["Oda kirli", "Banyo temiz degil", "Havlu degismemis", "Hali lekeli", "Cop bosaltilmamis"],
        "fnb": ["Yemek soguk geldi", "Kahvalti cesidi az", "Garson kaba davranıyor", "Alerjene dikkat edilmedi", "Menu fiyatlari yanlis"],
        "noise": ["Yan oda gurultulu", "Insaat sesi var", "Gece muzik sesi", "Koridor gurultusu", "Asansor sesi"],
        "maintenance": ["Dustan su akiyor", "Kapı kilidi bozuk", "Priz calismiyor", "Pencere acilmiyor", "Tuvalet tıkanmıs"],
    }
    complaint_departments = ["front_office", "housekeeping", "fnb", "maintenance", "management"]

    checked_in_bks = [b for b in bookings if b["status"] == "checked_in"]
    past_bks = [b for b in bookings if b["status"] == "checked_out"]
    all_complaint_bks = checked_in_bks + random.sample(past_bks, min(5, len(past_bks)))

    service_complaints = []
    for idx, bk in enumerate(all_complaint_bks):
        cat = random.choice(complaint_categories)
        sev = random.choices(complaint_severities, weights=[3, 4, 2, 1])[0]
        subj = random.choice(complaint_subjects[cat])
        days_ago = random.randint(0, 5) if bk["status"] == "checked_in" else random.randint(5, 30)
        created = (_now() - timedelta(days=days_ago, hours=random.randint(0, 12))).isoformat()

        is_resolved = bk["status"] == "checked_out" and random.random() < 0.7
        status = "resolved" if is_resolved else random.choice(["open", "in_progress", "escalated"])

        comp = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "guest_id": bk["guest_id"],
            "guest_name": bk["guest_name"],
            "booking_id": bk["id"],
            "room_id": bk.get("room_id"),
            "room_number": bk["room_number"],
            "room_type": bk["room_type"],
            "category": cat,
            "severity": sev,
            "subject": subj,
            "description": f"{subj}. Misafir {bk['guest_name']} (Oda {bk['room_number']}) sikayet etti.",
            "status": status,
            "assigned_department": random.choice(complaint_departments),
            "assigned_to": None,
            "created_at": created,
            "updated_at": created,
        }
        if is_resolved:
            comp["resolved_at"] = (_now() - timedelta(days=max(0, days_ago - 1))).isoformat()
            comp["resolved_by"] = "system"
            comp["resolution_notes"] = random.choice([
                "Oda degistirildi", "Teknik ekip sorunu giderdi", "Misafire ozur dilendi ve indirim uygulandi",
                "Housekeeping tekrar temizlik yapti", "Yonetici ile gorusuldu ve cozuldu"])
            comp["compensation_offered"] = random.choice([None, "room_upgrade", "fnb_credit", "discount", "free_night"])
            comp["compensation_amount"] = random.choice([0, 50, 100, 200]) if comp["compensation_offered"] else 0

        service_complaints.append(comp)

    if service_complaints:
        await db.service_complaints.insert_many(service_complaints)
    ctx["service_complaints"] = service_complaints

    # ── 6. Folios (for checked-in bookings) ───────────────
    folio_counter = 1
    folios = []
    checked_in_bookings = [b for b in bookings if b["status"] == "checked_in"]
    for b in checked_in_bookings:
        folio = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "booking_id": b["id"],
            "folio_number": f"F-{_now().year}-{folio_counter:04d}",
            "folio_type": "guest",
            "status": "open",
            "guest_id": b["guest_id"],
            "company_id": None,
            "balance": round(b["total_amount"] - b["paid_amount"], 2),
            "notes": None,
            "created_at": b["created_at"],
            "closed_at": None,
        }
        folios.append(folio)
        folio_counter += 1

    # Folios for past bookings (closed)
    past_bookings = [b for b in bookings if b["status"] == "checked_out"]
    for b in past_bookings[:10]:
        folio = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "booking_id": b["id"],
            "folio_number": f"F-{_now().year}-{folio_counter:04d}",
            "folio_type": "guest",
            "status": "closed",
            "guest_id": b["guest_id"],
            "company_id": None,
            "balance": 0.0,
            "notes": None,
            "created_at": b["created_at"],
            "closed_at": b["check_out"],
        }
        folios.append(folio)
        folio_counter += 1

    if folios:
        await db.folios.insert_many(folios)
    ctx["folios"] = folios
