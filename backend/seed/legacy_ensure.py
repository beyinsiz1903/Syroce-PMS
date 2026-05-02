"""Idempotent ensure-helpers run on every startup even when full seed is skipped."""
import logging
import random
from datetime import timedelta

from seed._helpers import _encrypt_doc, _now, _uuid, pwd_context

logger = logging.getLogger(__name__)


async def ensure_hr_legacy_connection(db):
    """Ensure hotelrunner_connections exists even when full seed is skipped."""
    user = await db.users.find_one({})
    if not user:
        return
    tid = user.get("tenant_id")
    if not tid:
        return
    existing = await db.hotelrunner_connections.find_one({"tenant_id": tid})
    if existing:
        return
    pc = await db.provider_connections.find_one(
        {"tenant_id": tid, "provider": "hotelrunner", "status": "active"}
    )
    if not pc:
        return
    creds = pc.get("credentials", {})
    hr_legacy = {
        "tenant_id": tid,
        "hr_id": creds.get("hr_id", ""),
        "token": creds.get("token", creds.get("hr_token", "")),
        "property_name": pc.get("display_name", "HotelRunner Connection"),
        "environment": pc.get("environment", "live"),
        "is_active": True,
        "channels": ["booking.com", "expedia", "airbnb"],
        "auto_sync_reservations": True,
        "connected_at": _now().isoformat(),
        "last_sync_at": None,
        "created_by": "auto_ensure",
    }
    await db.hotelrunner_connections.insert_one(hr_legacy)
    logger.info("✅ hotelrunner_connections legacy doc created from provider_connections")


async def ensure_tenant_admin_seeded(db):
    """Ensure a tenant-scoped `admin` user (not super_admin) exists.

    Idempotent — re-runs every startup; only inserts when missing. Used so
    pre-existing dev/Atlas databases that were seeded before this user was
    added still get it without manual re-seed. Tests in
    `backend/tests/test_monitoring_auth.py` rely on this account to verify
    the tenant-admin positive path on `/dispatch-config*`.

    User emails in this codebase are field-encrypted with a search hash
    (`_hash_email`); a plaintext-only `find_one({"email": ...})` misses
    encrypted records and would re-insert a duplicate admin on every
    startup. We use `build_user_email_query` (dual-read: hash OR plaintext)
    for both the existence check and the anchor-tenant lookup so the
    helper is truly idempotent across encrypted and unmigrated documents.

    Anchored strictly on the demo super_admin's tenant (NO fall-through to
    arbitrary users): in shared multi-tenant dev/Atlas databases a generic
    fallback would attach a deterministic-credential admin account to a
    random tenant — i.e. accidental privilege grant.
    """
    try:
        from security.encrypted_lookup import build_user_email_query
    except Exception:  # pragma: no cover — defensive: never fall back to a
        # plaintext probe that could miss an encrypted doc and re-insert.
        logger.warning(
            "tenant_admin seed: encrypted_lookup unavailable — skipping idempotency check"
        )
        return

    email = "tenantadmin@hotel.com"
    existing = await db.users.find_one(build_user_email_query(email))
    if existing:
        return
    # Anchor strictly on the demo super_admin's tenant. We deliberately do
    # NOT fall back to the first user found, because in shared multi-tenant
    # dev/Atlas databases that would attach a deterministic-credential admin
    # account to an arbitrary tenant — i.e. accidental privilege grant.
    anchor = await db.users.find_one(build_user_email_query("demo@hotel.com"))
    if not anchor:
        return
    tid = anchor.get("tenant_id")
    if not tid:
        return
    user_doc = {
        "id": _uuid(),
        "tenant_id": tid,
        "agency_id": None,
        "email": email,
        "name": "Tenant Admin",
        "role": "admin",
        "phone": "+905550000000",
        "is_active": True,
        "email_verified": True,
        "email_verified_at": _now().isoformat(),
        "hashed_password": pwd_context.hash("staff123"),
        "created_at": _now().isoformat(),
    }
    user_doc = _encrypt_doc(user_doc, "users")
    await db.users.insert_one(user_doc)
    logger.info("✅ tenantadmin@hotel.com (role=admin) seeded for monitoring auth tests")


async def ensure_complaints_seeded(db):
    """Ensure service_complaints exist even when full seed is skipped."""
    count = await db.service_complaints.count_documents({})
    if count > 0:
        return
    user = await db.users.find_one({})
    if not user:
        return
    tid = user.get("tenant_id")
    if not tid:
        return

    bookings_list = await db.bookings.find(
        {"tenant_id": tid, "status": {"$in": ["checked_in", "checked_out"]}},
        {"_id": 0}
    ).to_list(30)
    if not bookings_list:
        return

    complaint_categories = ["room", "service", "cleanliness", "fnb", "noise", "maintenance"]
    complaint_subjects = {
        "room": ["Klima calismiyor", "Sicak su yok", "TV bozuk", "Oda kokuyor", "Yatak rahatsiz"],
        "service": ["Check-in cok yavas", "Personel ilgisiz", "Room service gec geldi", "Bilgi yanlis verildi", "Bagaj kayboldu"],
        "cleanliness": ["Oda kirli", "Banyo temiz degil", "Havlu degismemis", "Hali lekeli", "Cop bosaltilmamis"],
        "fnb": ["Yemek soguk geldi", "Kahvalti cesidi az", "Garson kaba davranıyor", "Alerjene dikkat edilmedi", "Menu fiyatlari yanlis"],
        "noise": ["Yan oda gurultulu", "Insaat sesi var", "Gece muzik sesi", "Koridor gurultusu", "Asansor sesi"],
        "maintenance": ["Dustan su akiyor", "Kapı kilidi bozuk", "Priz calismiyor", "Pencere acilmiyor", "Tuvalet tıkanmıs"],
    }
    departments = ["front_office", "housekeeping", "fnb", "maintenance", "management"]
    severities = ["low", "medium", "high", "critical"]

    checked_in = [b for b in bookings_list if b.get("status") == "checked_in"]
    checked_out = [b for b in bookings_list if b.get("status") == "checked_out"]
    selected = checked_in + checked_out[:5]

    complaints = []
    for bk in selected:
        cat = random.choice(complaint_categories)
        sev = random.choices(severities, weights=[3, 4, 2, 1])[0]
        subj = random.choice(complaint_subjects[cat])
        days_ago = random.randint(0, 5) if bk.get("status") == "checked_in" else random.randint(5, 30)
        created = (_now() - timedelta(days=days_ago, hours=random.randint(0, 12))).isoformat()
        is_resolved = bk.get("status") == "checked_out" and random.random() < 0.7
        status = "resolved" if is_resolved else random.choice(["open", "in_progress", "escalated"])

        comp = {
            "id": _uuid(),
            "tenant_id": tid,
            "guest_id": bk.get("guest_id"),
            "guest_name": bk.get("guest_name"),
            "booking_id": bk.get("id"),
            "room_id": bk.get("room_id"),
            "room_number": bk.get("room_number"),
            "room_type": bk.get("room_type"),
            "category": cat,
            "severity": sev,
            "subject": subj,
            "description": f"{subj}. Misafir {bk.get('guest_name', '')} (Oda {bk.get('room_number', '')}) sikayet etti.",
            "status": status,
            "assigned_department": random.choice(departments),
            "assigned_to": None,
            "created_at": created,
            "updated_at": created,
        }
        if is_resolved:
            comp["resolved_at"] = (_now() - timedelta(days=max(0, days_ago - 1))).isoformat()
            comp["resolved_by"] = "system"
            comp["resolution_notes"] = random.choice([
                "Oda degistirildi", "Teknik ekip sorunu giderdi",
                "Misafire ozur dilendi ve indirim uygulandi",
                "Housekeeping tekrar temizlik yapti",
                "Yonetici ile gorusuldu ve cozuldu"])
            comp["compensation_offered"] = random.choice([None, "room_upgrade", "fnb_credit", "discount"])
            comp["compensation_amount"] = random.choice([0, 50, 100, 200]) if comp["compensation_offered"] else 0
        complaints.append(comp)

    if complaints:
        await db.service_complaints.insert_many(complaints)
        logger.info(f"✅ {len(complaints)} service complaints seeded")


async def ensure_agencies_seeded(db):
    """Seed demo travel agencies, agency bookings, and transactions if not present."""
    count = await db.agencies.count_documents({})
    if count > 0:
        return
    user = await db.users.find_one({})
    if not user:
        return
    tid = user.get("tenant_id")
    if not tid:
        return

    logger.info("🌱 Seeding travel agencies and AR/AP data...")

    agency_defs = [
        {"name": "Antalya Sun Tours", "contact_name": "Mehmet Yılmaz", "contact_email": "mehmet@antsunsuntours.com", "contact_phone": "+905551001001", "commission_rate": 12, "notes": "Premium partner since 2020"},
        {"name": "Blue Horizon Travel", "contact_name": "Elena Popov", "contact_email": "elena@bluehorizon.eu", "contact_phone": "+442071234567", "commission_rate": 15, "notes": "UK market specialist"},
        {"name": "Deutsche Reisen GmbH", "contact_name": "Hans Müller", "contact_email": "mueller@deutschereisen.de", "contact_phone": "+4930123456", "commission_rate": 10, "notes": "German market, high volume"},
        {"name": "Orient Express Tours", "contact_name": "Ayşe Demir", "contact_email": "ayse@orientexpress.com.tr", "contact_phone": "+905552002002", "commission_rate": 8, "notes": "Domestic tours, corporate groups"},
        {"name": "Riviera Holiday Agency", "contact_name": "Pierre Dubois", "contact_email": "pierre@rivieraholiday.fr", "contact_phone": "+33142123456", "commission_rate": 14, "notes": "French Riviera clientele"},
    ]

    guests_list = await db.guests.find({"tenant_id": tid}).to_list(50)
    rooms_list = await db.rooms.find({"tenant_id": tid}).to_list(50)
    if not guests_list or not rooms_list:
        return

    agencies = []
    all_bookings = []
    all_transactions = []
    now = _now()

    for idx, adef in enumerate(agency_defs):
        agency_id = _uuid()
        agency = {
            "id": agency_id,
            "tenant_id": tid,
            **adef,
            "status": "active",
            "created_at": (now - timedelta(days=180 + idx * 30)).isoformat(),
        }
        agencies.append(agency)

        num_bookings = random.randint(5, 15)
        agency_total_commission = 0
        for bi in range(num_bookings):
            guest = random.choice(guests_list)
            room = random.choice(rooms_list)
            days_ago = random.randint(5, 120)
            ci = now - timedelta(days=days_ago)
            nights = random.randint(2, 7)
            co = ci + timedelta(days=nights)
            rate = random.choice([8000, 10000, 12000, 15000, 18000, 22000, 25000])
            total = rate * nights
            commission_amount = round(total * adef["commission_rate"] / 100, 2)
            agency_total_commission += commission_amount

            status_options = ["checked_out"] * 6 + ["confirmed"] * 2 + ["checked_in"] * 2
            bk_status = random.choice(status_options)

            booking = {
                "id": _uuid(),
                "tenant_id": tid,
                "agency_id": agency_id,
                "guest_id": guest.get("id"),
                "guest_name": guest.get("name", guest.get("first_name", "Guest")),
                "room_id": room.get("id"),
                "room_number": room.get("number", room.get("room_number", "101")),
                "room_type": room.get("type", room.get("room_type", "standard")),
                "check_in": ci.strftime("%Y-%m-%d"),
                "check_out": co.strftime("%Y-%m-%d"),
                "nights": nights,
                "adults": random.randint(1, 3),
                "children": random.randint(0, 2),
                "base_rate": rate,
                "total_amount": total,
                "status": bk_status,
                "source": "agency",
                "channel": "agency",
                "source_channel": f"agency:{adef['name']}",
                "rate_plan": "agency_negotiated",
                "paid_amount": total if bk_status == "checked_out" else 0,
                "created_at": ci.isoformat(),
            }
            all_bookings.append(booking)

        paid_pct = random.uniform(0.3, 0.85)
        paid_amount = round(agency_total_commission * paid_pct, 2)

        num_payments = random.randint(1, 4)
        remaining = paid_amount
        for pi in range(num_payments):
            if remaining <= 0:
                break
            pmt = round(remaining / (num_payments - pi), 2) if pi < num_payments - 1 else remaining
            pmt = min(pmt, remaining)
            payment_date = now - timedelta(days=random.randint(2, 90))
            txn = {
                "id": _uuid(),
                "tenant_id": tid,
                "agency_id": agency_id,
                "type": "payment",
                "amount": pmt,
                "payment_method": random.choice(["bank_transfer", "check", "credit_card", "wire_transfer"]),
                "reference": f"PAY-{random.randint(10000, 99999)}",
                "notes": f"Commission payment for {adef['name']}",
                "recorded_by": "info@syroce.com",
                "created_at": payment_date.isoformat(),
            }
            all_transactions.append(txn)
            remaining = round(remaining - pmt, 2)

    await db.agencies.insert_many(agencies)
    if all_bookings:
        await db.bookings.insert_many(all_bookings)
    if all_transactions:
        await db.agency_transactions.insert_many(all_transactions)

    logger.info(f"  ✅ Agencies: {len(agencies)}")
    logger.info(f"  ✅ Agency bookings: {len(all_bookings)}")
    logger.info(f"  ✅ Agency transactions: {len(all_transactions)}")
