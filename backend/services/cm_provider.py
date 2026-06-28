from core.database import db

async def _tenant_configured_provider(tenant_id: str) -> str | None:
    """Otelin super_admin tarafindan secilmis kanal yoneticisi altyapisi.

    Yalnizca gecerli bir deger ("exely"/"hotelrunner") dondurur; alan yoksa
    veya tanimsizsa None doner (=> otomatik tespit korunur, pilot_drift=0).
    """
    tdoc = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "channel_manager_provider": 1})
    val = (tdoc or {}).get("channel_manager_provider")
    return val if val in ("exely", "hotelrunner") else None


async def _detect_active_provider(tenant_id: str, prefer: str | None = None) -> dict:
    """Otelde aktif olan kanal saglayiciyi tespit et.

    Otel icin super_admin bir altyapi sectiyse (channel_manager_provider) bu
    secim OTORITERDIR ve istemci girdisi (`prefer`) bunu ASLA ezemez:
    - secilenin aktif baglantisi yoksa FAIL-CLOSED (provider=None,
      configuration_error="connection_missing", digerine DUSULMEZ).
    - `prefer` secilenden FARKLI istenirse FAIL-CLOSED
      (configuration_error="provider_not_selected"); seciliyle AYNI ise o kullanilir.

    Secim YOKSA (alan null/tanimsiz): eski davranis korunur (pilot_drift=0) —
    `prefer` yumusak tercih (varsa o, yoksa varsayilan sira HR > Exely).
    """
    hr_conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    if not hr_conn:
        pc = await db.provider_connections.find_one({"tenant_id": tenant_id, "provider": "hotelrunner", "status": "active"})
        if pc:
            legacy = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id}, {"_id": 0, "cached_rooms": 1})
            hr_conn = {
                "tenant_id": tenant_id,
                "is_active": True,
                "hr_id": pc.get("credentials", {}).get("hr_id", ""),
                "environment": pc.get("environment", "live"),
                "cached_rooms": (legacy or {}).get("cached_rooms", []),
            }

    exely_conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})

    # Per-tenant secili altyapi (super_admin) OTORITERDIR; istemci (prefer) ezemez.
    configured = await _tenant_configured_provider(tenant_id)

    if configured is not None:
        if prefer is not None and prefer != configured:
            # Istemci secilmeyen saglayiciyi istedi -> FAIL-CLOSED.
            return {"provider": None, "connection": None, "configured_provider": configured, "configuration_error": "provider_not_selected"}
        if configured == "exely":
            if exely_conn:
                return {"provider": "exely", "connection": exely_conn}
            return {"provider": None, "connection": None, "configured_provider": "exely", "configuration_error": "connection_missing"}
        # configured == "hotelrunner"
        if hr_conn:
            return {"provider": "hotelrunner", "connection": hr_conn}
        return {"provider": None, "connection": None, "configured_provider": "hotelrunner", "configuration_error": "connection_missing"}

    # Secim yok -> eski otomatik tespit (yumusak prefer + varsayilan sira HR > Exely).
    if prefer == "exely" and exely_conn:
        return {"provider": "exely", "connection": exely_conn}
    if prefer == "hotelrunner" and hr_conn:
        return {"provider": "hotelrunner", "connection": hr_conn}

    if hr_conn and exely_conn:
        return {"provider": "hotelrunner", "connection": hr_conn}

    if hr_conn:
        return {"provider": "hotelrunner", "connection": hr_conn}
    if exely_conn:
        return {"provider": "exely", "connection": exely_conn}

    return {"provider": None, "connection": None}
