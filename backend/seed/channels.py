"""Seed sections 8 + 9 + 9b + 10 + 11 + 11b + 11c: Exely + Channel Manager.

- Exely webhook test connection (upsert by hotel_code)
- CM provider connections (HotelRunner + Exely) — 9-collection model
- HotelRunner legacy doc for overview
- Room mappings + rate plan mappings (v1)
- Connector flags (LIVE for both)
- CM v2 connectors + external room types/rate plans + mappings
"""

import os
from seed._helpers import _now, _uuid


async def seed_channels(db, ctx):
    tenant_id = ctx["tenant_id"]

    hr_token = os.environ.get("SEED_HOTELRUNNER_TOKEN", "")
    hr_id = os.environ.get("SEED_HOTELRUNNER_HR_ID", "")
    # Seed never creates active connections to avoid dangling credential refs
    hr_is_active = False
    hr_status = "inactive"
    
    ex_user = os.environ.get("SEED_EXELY_USERNAME", "")
    ex_pass = os.environ.get("SEED_EXELY_PASSWORD", "")
    ex_hotel = os.environ.get("SEED_EXELY_HOTEL_CODE", "")
    # Seed never creates active connections to avoid dangling credential refs
    ex_is_active = False
    ex_status = "inactive"

    hr_sync_enabled = hr_is_active
    ex_sync_enabled = ex_is_active
    hr_mapping_active = hr_is_active
    hr_validation = "valid" if hr_is_active else "unverified"
    ex_mapping_active = ex_is_active
    ex_validation = "valid" if ex_is_active else "unverified"

    # ── 8. Exely Connection (for webhook tests) ──────────
    exely_conn = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "hotel_code": ex_hotel if ex_is_active else "DEMO-EXELY",
        "credentials_ref": f"vault:exely:{ex_hotel if ex_is_active else 'DEMO-EXELY'}",
        "endpoint_url": f"https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc?HotelCode={ex_hotel}" if ex_is_active else None,

        "property_name": "TEST Syroce PMS (Exely)",
        "auto_sync_reservations": False,
        "sync_interval_minutes": 15,
        "mode": "sandbox",
        "currency": "USD",
        "is_active": ex_is_active,
        "room_types": [
            {"code": "5001574", "name": "Standart", "max_occupancy": 2},
            {"code": "5001575", "name": "Deluxe", "max_occupancy": 3},
            {"code": "5001576", "name": "Suite", "max_occupancy": 4},
        ],
        "rate_plans": [
            {"code": "10003870", "name": "Base rate USD"},
            {"code": "10003541", "name": "Dynamic Rate USD"},
            {"code": "10003869", "name": "Non-ref rate USD"},
            {"code": "10003186", "name": "Mixed rate USD"},
            {"code": "10003182", "name": "Best daily rate"},
        ],
        "connected_at": _now().isoformat(),
        "last_sync_at": None,
        "created_by": "auto_seed",
    }
    await db.exely_connections.update_one(
        {"hotel_code": ex_hotel if ex_is_active else "DEMO-EXELY"},
        {"$set": exely_conn},
        upsert=True,
    )

    # ── 9. Channel Manager: Provider Connections (9-collection model) ──
    now_iso = _now().isoformat()
    hr_conn = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "status": hr_status,
        "display_name": "HotelRunner Connection",
        "credentials_ref": f"secrets_manager::hotelrunner::{hr_id if hr_is_active else 'DEMO-HR'}",
        "sync_inventory": False,
        "sync_rates": False,
        "sync_reservations": False,
        "sync_restrictions": False,
        "max_requests_per_minute": 60,
        "max_requests_per_hour": 1000,
        "consecutive_failures": 0,
        "total_syncs": 0,
        "total_errors": 0,
        "created_at": now_iso,
        "created_by": "auto_seed",
    }
    ex_conn = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "status": ex_status,
        "display_name": "Exely Connection",
        "credentials_ref": f"vault:exely:{ex_hotel if ex_is_active else 'DEMO-EXELY'}",
        "sync_inventory": False,
        "sync_rates": False,
        "sync_reservations": False,
        "sync_restrictions": False,
        "max_requests_per_minute": 60,
        "max_requests_per_hour": 1000,
        "consecutive_failures": 0,
        "total_syncs": 0,
        "total_errors": 0,
        "created_at": now_iso,
        "created_by": "auto_seed",
    }
    await db.provider_connections.insert_many([hr_conn, ex_conn])

    # ── 9b. hotelrunner_connections (legacy format for overview) ──
    hr_legacy = {
        "tenant_id": tenant_id,
        "hr_id": hr_id if hr_is_active else "DEMO-HR",
        "property_name": "Syroce Demo Hotel",
        "environment": "live",
        "is_active": hr_is_active,
        "channels": ["booking.com", "expedia", "airbnb"],
        "auto_sync_reservations": False,
        "connected_at": now_iso,
        "last_sync_at": None,
        "created_by": "auto_seed",
        "cached_rooms": [
            {
                "inv_code": "HR:1271568",
                "name": "Standart Oda",
                "id": 1271568,
                "pms_code": "STD",
                "rate_plan_id": 220505,
                "rate_plan_name": "Ana fiyat",
                "availability_update": True,
                "restrictions_update": True,
                "price_update": True,
                "pricing_type": "guest_based",
                "sales_currency": "TRY",
                "sales_currency_symbol": "₺",
            },
            {
                "inv_code": "HR:1271569",
                "name": "Deluxe Oda",
                "id": 1271569,
                "pms_code": "DLX",
                "rate_plan_id": 220505,
                "rate_plan_name": "Ana fiyat",
                "availability_update": True,
                "restrictions_update": True,
                "price_update": True,
                "pricing_type": "guest_based",
                "sales_currency": "TRY",
                "sales_currency_symbol": "₺",
            },
            {
                "inv_code": "HR:1271567",
                "name": "Corner Süit",
                "id": 1271567,
                "pms_code": "SUI",
                "rate_plan_id": 220505,
                "rate_plan_name": "Ana fiyat",
                "availability_update": True,
                "restrictions_update": True,
                "price_update": True,
                "pricing_type": "guest_based",
                "sales_currency": "TRY",
                "sales_currency_symbol": "₺",
            },
        ],
    }
    await db.hotelrunner_connections.update_one(
        {"tenant_id": tenant_id},
        {"$set": hr_legacy},
        upsert=True,
    )

    # ── 10. Channel Manager: Room Mappings ───────────────────
    hr_room = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "pms_room_type_id": "std-001",
        "pms_room_type_name": "Standard Room",
        "provider_room_code": "STD",
        "provider_room_id": "hr-std-001",
        "occupancy_offset": 0,
        "is_active": hr_mapping_active,
        "validation_status": hr_validation,
        "created_at": now_iso,
    }
    ex_room = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "pms_room_type_id": "dlx-001",
        "pms_room_type_name": "Deluxe Room",
        "provider_room_code": "DLX",
        "provider_room_id": "ex-dlx-001",
        "occupancy_offset": 0,
        "is_active": ex_mapping_active,
        "validation_status": ex_validation,
        "created_at": now_iso,
    }
    await db.room_mappings.insert_many([hr_room, ex_room])

    # ── 11. Channel Manager: Rate Plan Mappings ──────────────
    hr_rate = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "pms_rate_plan_id": "bar-001",
        "pms_rate_plan_name": "Best Available Rate",
        "provider_rate_code": "BAR",
        "provider_rate_id": "hr-bar-001",
        "is_active": hr_mapping_active,
        "validation_status": hr_validation,
        "created_at": now_iso,
    }
    ex_rate = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "pms_rate_plan_id": "rack-001",
        "pms_rate_plan_name": "Rack Rate",
        "provider_rate_code": "RACK",
        "provider_rate_id": "ex-rack-001",
        "is_active": ex_mapping_active,
        "validation_status": ex_validation,
        "created_at": now_iso,
    }
    await db.rate_plan_mappings.insert_many([hr_rate, ex_rate])

    # ── 11b. Connector Flags (LIVE mode for both providers) ──
    for prov in ["hotelrunner", "exely"]:
        await db.connector_flags.update_one(
            {"tenant_id": tenant_id, "provider": prov},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "provider": prov,
                    "connector_enabled": hr_is_active if prov == "hotelrunner" else ex_is_active,
                    "shadow_mode": True,
                    "write_enabled": False,
                    "updated_at": now_iso,
                    "updated_by": "auto_seed",
                }
            },
            upsert=True,
        )

    # ── 11c. CM v2 Connectors + External Data + Mappings ────
    hr_connector_id = "conn-hr-001"
    ex_connector_id = "conn-ex-001"

    hr_connector = {
        "id": hr_connector_id,
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "display_name": "HotelRunner - Syroce Demo",
        "status": hr_status,
        "credentials_ref": f"secrets_manager::hotelrunner::{hr_id if hr_is_active else 'DEMO-HR'}",
        "sync_enabled": hr_sync_enabled,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    ex_connector = {
        "id": ex_connector_id,
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "display_name": "Exely - Syroce Demo",
        "status": ex_status,
        "credentials_ref": f"vault:exely:{ex_hotel if ex_is_active else 'DEMO-EXELY'}",
        "sync_enabled": ex_sync_enabled,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.cm_connectors.insert_many([hr_connector, ex_connector])

    pms_rate_defs = [
        {"id": "bar-001", "name": "Best Available Rate", "code": "BAR"},
        {"id": "rack-001", "name": "Rack Rate", "code": "RACK"},
        {"id": "promo-001", "name": "Promotional Rate", "code": "PROMO"},
    ]

    hr_ext_room_defs = [
        {"id": "std-001", "name": "Standart Oda", "code": "STD", "capacity": 2, "base_price": 4500},
        {"id": "dlx-001", "name": "Deluxe Oda", "code": "DLX", "capacity": 2, "base_price": 6800},
        {"id": "sui-001", "name": "Corner Süit", "code": "SUI", "capacity": 4, "base_price": 14000},
    ]
    ex_ext_room_defs = [
        {"id": "std-001", "name": "Standart", "code": "STD", "capacity": 2, "base_price": 4500},
        {"id": "dlx-001", "name": "Deluxe", "code": "DLX", "capacity": 2, "base_price": 6800},
        {"id": "sui-001", "name": "Suite", "code": "SUI", "capacity": 4, "base_price": 14000},
    ]

    hr_pms_to_ext = [
        ("Standard", "std-001", "Standart Oda"),
        ("Deluxe", "dlx-001", "Deluxe Oda"),
        ("Suite", "sui-001", "Corner Süit"),
    ]
    ex_pms_to_ext = [
        ("Standard", "std-001", "Standart"),
        ("Deluxe", "dlx-001", "Deluxe"),
        ("Suite", "sui-001", "Suite"),
    ]

    provider_ext_defs = {
        hr_connector_id: ("hotelrunner", hr_ext_room_defs, hr_pms_to_ext),
        ex_connector_id: ("exely", ex_ext_room_defs, ex_pms_to_ext),
    }

    for cid, (prov, ext_room_defs, pms_to_ext) in provider_ext_defs.items():
        prefix = prov[:2]
        ext_rooms = []
        for r in ext_room_defs:
            ext_rooms.append(
                {
                    "id": f"ext-room-{prefix}-{r['code'].lower()}",
                    "tenant_id": tenant_id,
                    "connector_id": cid,
                    "provider": prov,
                    "external_id": f"{prefix}-{r['code'].lower()}-001",
                    "name": r["name"],
                    "code": r["code"],
                    "max_occupancy": r["capacity"],
                    "base_price": r["base_price"],
                    "is_active": True,
                    "created_at": now_iso,
                }
            )
        if ext_rooms:
            await db.cm_external_room_types.insert_many(ext_rooms)

        ext_rates = []
        for rp in pms_rate_defs:
            ext_rates.append(
                {
                    "id": f"ext-rate-{prefix}-{rp['code'].lower()}",
                    "tenant_id": tenant_id,
                    "connector_id": cid,
                    "provider": prov,
                    "external_id": f"{prefix}-{rp['code'].lower()}-001",
                    "name": rp["name"],
                    "code": rp["code"],
                    "is_active": True,
                    "created_at": now_iso,
                }
            )
        if ext_rates:
            await db.cm_external_rate_plans.insert_many(ext_rates)

        room_mappings_v2 = []
        for pms_name, ext_id, ext_name in pms_to_ext:
            room_mappings_v2.append(
                {
                    "id": f"map-room-{prefix}-{ext_id}",
                    "tenant_id": tenant_id,
                    "connector_id": cid,
                    "entity_type": "room_type",
                    "pms_entity_id": pms_name,
                    "pms_entity_name": pms_name,
                    "external_entity_id": f"{prefix}-{ext_id.split('-')[0]}-001",
                    "external_entity_name": ext_name,
                    "status": "active",
                    "validation_status": "valid",
                    "confidence_score": 100,
                    "created_by": "auto_seed",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            )
        if room_mappings_v2:
            await db.cm_mappings.insert_many(room_mappings_v2)

        rate_mappings_v2 = []
        for rp in pms_rate_defs:
            rate_mappings_v2.append(
                {
                    "id": f"map-rate-{prefix}-{rp['code'].lower()}",
                    "tenant_id": tenant_id,
                    "connector_id": cid,
                    "entity_type": "rate_plan",
                    "pms_entity_id": rp["id"],
                    "pms_entity_name": rp["name"],
                    "external_entity_id": f"{prefix}-{rp['code'].lower()}-001",
                    "external_entity_name": rp["name"],
                    "status": "active",
                    "validation_status": "valid",
                    "confidence_score": 100,
                    "created_by": "auto_seed",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            )
        if rate_mappings_v2:
            await db.cm_mappings.insert_many(rate_mappings_v2)
