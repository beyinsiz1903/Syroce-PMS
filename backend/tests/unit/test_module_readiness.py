"""Module readiness from the hotel's own data (core.module_readiness)."""

from datetime import UTC, datetime, timedelta

import pytest

from core import module_readiness as mr

NOW = datetime.now(UTC)
MISSING = object()


def _field(doc, key):
    value = doc
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value


def _matches(doc, query):
    for key, cond in query.items():
        if key == "$and":
            if not all(_matches(doc, part) for part in cond):
                return False
            continue
        if key == "$or":
            if not any(_matches(doc, part) for part in cond):
                return False
            continue
        value = _field(doc, key)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op in ("$gt", "$gte", "$lte"):
                    if not ((type(value) is type(arg)) or (type(value) in (int, float) and type(arg) in (int, float))):
                        return False
                    if (op == "$gt" and value <= arg) or (op == "$gte" and value < arg) or (op == "$lte" and value > arg):
                        return False
                if op == "$type" and not (arg == "string" and isinstance(value, str)):
                    return False
                if op == "$exists" and (value is not MISSING) != arg:
                    return False
                if op == "$ne" and value == arg:
                    return False
                if op == "$nin" and value in arg:
                    return False
        elif value != cond:
            return False
    return True


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    async def count_documents(self, query, limit=0, **_options):
        hits = sum(1 for doc in self.docs if _matches(doc, query))
        return min(hits, limit) if limit else hits


class _DB:
    def __init__(self, **collections):
        self.collections = collections

    def __getitem__(self, name):
        return _Coll(self.collections.get(name, []))


def _recent(days=1, as_datetime=False):
    moment = NOW - timedelta(days=days)
    return moment if as_datetime else moment.isoformat()


@pytest.mark.asyncio
async def test_statuses_off_view_unknown():
    db = _DB()
    assert (await mr.module_readiness(db, "t1", "spa", enabled=False))["status"] == "off"
    assert (await mr.module_readiness(db, "t1", "dashboard", enabled=True))["status"] == "ready"
    assert (await mr.module_readiness(db, "t1", "no_such_module", enabled=True))["status"] == "unknown"


@pytest.mark.asyncio
async def test_incomplete_lists_the_missing_setup_with_its_screen():
    db = _DB(spa_services=[{"tenant_id": "t1", "active": True}], spa_rooms=[{"tenant_id": "t1", "active": True}])
    row = await mr.module_readiness(db, "t1", "spa", enabled=True)
    assert row["status"] == "incomplete"
    missing = [item for item in row["setup"] if not item["ok"]]
    assert [(item["key"], item["path"]) for item in missing] == [("spa_therapists", "/spa-wellness")]


@pytest.mark.asyncio
async def test_idle_until_recent_use_then_active_with_iso_or_datetime_dates():
    setup = {"spa_services": [{"tenant_id": "t1"}], "spa_rooms": [{"tenant_id": "t1", "active": True}], "spa_therapists": [{"tenant_id": "t1", "active": True}]}
    old = _DB(**setup, spa_appointments=[{"tenant_id": "t1", "created_at": _recent(days=90)}])
    assert (await mr.module_readiness(old, "t1", "spa", enabled=True))["status"] == "idle"
    fresh = _DB(**setup, spa_appointments=[{"tenant_id": "t1", "created_at": _recent()}])
    assert (await mr.module_readiness(fresh, "t1", "spa", enabled=True))["status"] == "active"
    # Contact-center calls store datetimes, not strings.
    calls = _DB(contact_center_voice_numbers=[{"tenant_id": "t1"}],
                contact_center_calls=[{"tenant_id": "t1", "started_at": _recent(as_datetime=True)}])
    assert (await mr.module_readiness(calls, "t1", "contact_center", enabled=True))["status"] == "active"


@pytest.mark.asyncio
async def test_inventory_and_posted_stay_charges_are_not_price_configuration():
    db = _DB(rooms=[{"tenant_id": "t1", "room_type": "Suite"}],
             room_type_inventory=[{"tenant_id": "t1", "physical_total": 10}],
             daily_rates=[{"tenant_id": "t1", "booking_id": "old", "rate": 1500}])
    row = await mr.module_readiness(db, "t1", "pms", True)
    assert [item["key"] for item in row["setup"] if not item["ok"]] == ["rates"]


@pytest.mark.asyncio
@pytest.mark.parametrize("collection,price", [("rooms", {"base_price": 1000}), ("room_types", {"base_rate": 500}), ("rate_calendar", {"rate": 700})])
async def test_actual_positive_room_or_calendar_rates_are_evidence(collection, price):
    assert await mr._met(_DB(**{collection: [{"tenant_id": "t1", **price}]}), "t1", mr.RATES)
    assert not await mr._met(_DB(**{collection: [{"tenant_id": "other", **price}]}), "t1", mr.RATES)


@pytest.mark.asyncio
@pytest.mark.parametrize("nilvera,expected", [
    ({"enabled": True, "api_key_enc": "encrypted-test-only"}, True),
    ({"enabled": False, "api_key_enc": "encrypted-test-only"}, False),
    ({"enabled": True, "api_key_enc": ""}, False),
    ({"enabled": True}, False),
])
async def test_invoice_setup_uses_the_provider_not_gl_mappings(nilvera, expected):
    db = _DB(tenant_settings=[{"tenant_id": "t1", "nilvera": nilvera}],
             gl_nilvera_settings=[{"tenant_id": "t1"}], integration_credentials=[{"tenant_id": "t1", "key": "OTHER"}])
    row = await mr.module_readiness(db, "t1", "invoices", True)
    assert row["setup"][0]["ok"] is expected
    assert "encrypted-test-only" not in str(row)
    assert not await mr._met(_DB(gl_nilvera_settings=[{"tenant_id": "t1"}]), "t1", mr.EINVOICE)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,enabled,expected", [("smtp_email", True, False), ("whatsapp", False, False), ("whatsapp", True, True)])
async def test_whatsapp_does_not_inherit_smtp_configuration(provider, enabled, expected):
    row = await mr.module_readiness(_DB(messaging_provider_configs=[{
        "tenant_id": "t1", "provider_type": provider, "enabled": enabled,
        "credentials_encrypted": {"access_token": "test-cipher", "phone_number_id": "test-phone"},
    }]), "t1", "ai_whatsapp", True)
    assert row["setup"][0]["ok"] is expected


@pytest.mark.asyncio
async def test_enabled_but_empty_whatsapp_settings_are_not_ready():
    row = await mr.module_readiness(_DB(messaging_provider_configs=[{
        "tenant_id": "t1", "provider_type": "whatsapp", "enabled": True, "credentials_encrypted": {},
    }]), "t1", "ai_whatsapp", True)
    assert row["status"] == "incomplete"


@pytest.mark.asyncio
async def test_mailing_uses_platform_transport_and_its_own_campaigns(monkeypatch):
    import core.email

    monkeypatch.setattr(core.email, "DEFAULT_FROM", "Syroce <test@example.com>")
    monkeypatch.setenv("MAIL_PROVIDER", "resend")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    db = _DB(messaging_provider_configs=[{"tenant_id": "t1", "provider_type": "smtp_email", "enabled": True}],
             mailing_campaigns=[{"tenant_id": "t1", "sent_count": 1, "created_at": _recent()}])
    assert (await mr.module_readiness(db, "t1", "mailing", True))["status"] == "incomplete"
    monkeypatch.setenv("RESEND_API_KEY", "test-platform-key-not-returned")
    row = await mr.module_readiness(db, "t1", "mailing", True)
    assert row["status"] == "active"
    assert "test-platform-key-not-returned" not in str(row)
    db.collections["mailing_campaigns"][0]["is_test"] = True
    assert (await mr.module_readiness(db, "t1", "mailing", True))["status"] == "idle"
    monkeypatch.setattr(core.email, "DEFAULT_FROM", "Invalid sender")
    assert (await mr.module_readiness(db, "t1", "mailing", True))["status"] == "incomplete"


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run,status,expected", [(True, "completed", "idle"), (False, "failed", "idle"), (False, "completed", "active")])
async def test_only_completed_live_audits_count_as_day_closes(dry_run, status, expected):
    db = _DB(rooms=[{"tenant_id": "t1"}], night_audit_runs=[{"tenant_id": "t1", "dry_run": dry_run, "status": status, "completed_at": _recent()}])
    assert (await mr.module_readiness(db, "t1", "night_audit", True))["status"] == expected


@pytest.mark.asyncio
async def test_web_usage_does_not_count_front_desk_bookings():
    db = _DB(rooms=[{"tenant_id": "t1", "base_price": 1000}], bookings=[{"tenant_id": "t1", "created_at": _recent(), "channel": "direct"}])
    assert (await mr.module_readiness(db, "t1", "booking_engine", True))["status"] == "idle"
    db.collections["bookings"][0]["source_channel"] = "web_booking_engine"
    assert (await mr.module_readiness(db, "t1", "booking_engine", True))["status"] == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("as_datetime", [False, True])
async def test_future_records_are_not_recent_usage(as_datetime):
    future = NOW + timedelta(days=1)
    db = _DB(guests=[{"tenant_id": "t1", "created_at": future if as_datetime else future.isoformat()}])
    assert (await mr.module_readiness(db, "t1", "guests", True))["status"] == "idle"


@pytest.mark.asyncio
async def test_revenue_usage_uses_generation_time_not_the_forecast_target():
    db = _DB(pricing_settings=[{"tenant_id": "t1"}], rms_pricing_recommendations=[{
        "tenant_id": "t1", "date": (NOW + timedelta(days=60)).date().isoformat(), "generated_at": _recent(60),
    }])
    assert (await mr.module_readiness(db, "t1", "revenue_management", True))["status"] == "idle"
    db.collections["rms_pricing_recommendations"][0]["generated_at"] = _recent()
    assert (await mr.module_readiness(db, "t1", "revenue_management", True))["status"] == "active"


@pytest.mark.asyncio
async def test_inactive_resources_cannot_complete_setup():
    db = _DB(rooms=[{"tenant_id": "t1", "is_active": False}],
             spa_services=[{"tenant_id": "t1", "active": True}], spa_rooms=[{"tenant_id": "t1", "active": False}],
             spa_therapists=[{"tenant_id": "t1", "active": False}],
             pos_outlets=[{"tenant_id": "t1", "status": "active"}], pos_menu_items=[{"tenant_id": "t1", "available": False}])
    assert (await mr.module_readiness(db, "t1", "reservation_calendar", True))["status"] == "incomplete"
    assert (await mr.module_readiness(db, "t1", "spa", True))["status"] == "incomplete"
    assert (await mr.module_readiness(db, "t1", "pos_fnb", True))["status"] == "incomplete"


@pytest.mark.asyncio
async def test_connection_or_queries_with_other_tenants_do_not_pass():
    db = _DB(exely_connections=[{"tenant_id": "other", "is_active": True}], cm_mappings=[{"tenant_id": "t1", "entity_type": "rate_plan"}])
    row = await mr.module_readiness(db, "t1", "channel_manager", True)
    assert all(item["ok"] is False for item in row["setup"])


@pytest.mark.asyncio
async def test_expired_contract_or_unpriced_calendar_is_not_extranet_setup():
    db = _DB(marketplace_listings=[{"tenant_id": "t1", "is_listed": True}],
             agency_contracts=[{"tenant_id": "t1", "status": "approved", "valid_to": "2020-01-01"}],
             agency_rate_calendar=[{"tenant_id": "t1", "date": "2099-01-01", "availability": 5}])
    row = await mr.module_readiness(db, "t1", "agency_extranet", True)
    assert {item["key"] for item in row["setup"] if item["ok"] is False} == {"contract", "agency_rates"}
    db.collections["agency_contracts"][0]["valid_to"] = "2099-01-01"
    db.collections["agency_rate_calendar"][0]["rate"] = 1000
    assert (await mr.module_readiness(db, "t1", "agency_extranet", True))["status"] == "idle"


@pytest.mark.asyncio
async def test_api_setup_uses_an_active_tenant_key_not_platform_credentials():
    db = _DB(integration_credentials=[{"tenant_id": "t1", "key": "UNRELATED"}],
             agency_api_keys=[{"tenant_id": "other", "is_active": True}, {"tenant_id": "t1", "is_active": False}])
    assert (await mr.module_readiness(db, "t1", "api_access", True))["status"] == "incomplete"
    db.collections["agency_api_keys"].append({"tenant_id": "t1", "is_active": True})
    assert (await mr.module_readiness(db, "t1", "api_access", True))["status"] == "ready"


@pytest.mark.asyncio
async def test_failed_check_is_unknown_and_does_not_hide_other_modules():
    class Broken(_DB):
        def __getitem__(self, name):
            if name == "rooms":
                raise RuntimeError("simulated collection failure")
            return super().__getitem__(name)

    rows = await mr.tenant_readiness(Broken(), "t1", {"pms": True, "guests": True, "dashboard": True})
    assert rows["pms"]["status"] == "unknown"
    assert rows["pms"]["setup"][0]["ok"] is None
    assert rows["guests"]["status"] == "idle"
    assert rows["dashboard"]["status"] == "ready"


@pytest.mark.asyncio
async def test_check_timeout_is_not_missing_configuration(monkeypatch):
    import asyncio

    async def slow(*_args, **_kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(mr, "_met", slow)
    monkeypatch.setattr(mr, "CHECK_TIMEOUT_SECONDS", 0.01)
    row = await mr.module_readiness(_DB(), "t1", "pms", True)
    assert row["status"] == "unknown"
    assert all(item["ok"] is None for item in [*row["setup"], *row["usage"]])


@pytest.mark.asyncio
async def test_shared_checks_are_memoized_only_within_one_bounded_request(monkeypatch):
    import asyncio
    from collections import Counter

    seen = Counter()
    active = peak = 0

    async def observe(_db, _tenant, item, **_kwargs):
        nonlocal active, peak
        seen[item["key"]] += 1
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return True

    monkeypatch.setattr(mr, "_met", observe)
    flags = dict.fromkeys(mr.MODULE_CHECKS, True)
    await mr.tenant_readiness(_DB(), "t1", flags)
    assert seen["rooms"] == 1 and seen["bookings_30d"] == 1
    assert peak <= mr.MAX_CONCURRENT_CHECKS
    await mr.tenant_readiness(_DB(), "t1", flags)
    assert seen["rooms"] == 2  # No cross-request / cross-hotel cache.


@pytest.mark.asyncio
async def test_other_hotels_data_and_filters_do_not_count():
    db = _DB(rooms=[{"tenant_id": "other"}], pos_outlets=[{"tenant_id": "t1", "status": "deleted"}],
             pos_menu_items=[{"tenant_id": "t1"}])
    pms = await mr.module_readiness(db, "t1", "reservation_calendar", enabled=True)
    assert pms["status"] == "incomplete"
    pos = await mr.module_readiness(db, "t1", "pos_basic", enabled=True)
    assert [i["key"] for i in pos["setup"] if not i["ok"]] == ["pos_outlet"]


@pytest.mark.asyncio
async def test_any_listed_collection_satisfies_a_check():
    db = _DB(hotelrunner_connections=[{"tenant_id": "t1", "is_active": True}],
             cm_mappings=[{"tenant_id": "t1"}], exely_ari_deliveries=[{"tenant_id": "t1", "created_at": _recent()}])
    row = await mr.module_readiness(db, "t1", "channel_manager", enabled=True)
    assert row["status"] == "active"
    inactive = _DB(exely_connections=[{"tenant_id": "t1", "is_active": False}], cm_mappings=[{"tenant_id": "t1"}])
    assert (await mr.module_readiness(inactive, "t1", "channel_manager", enabled=True))["status"] == "incomplete"


@pytest.mark.asyncio
async def test_tenant_readiness_covers_every_rule_and_skips_disabled_ones():
    rows = await mr.tenant_readiness(_DB(), "t1", {"pms": True})
    assert set(rows) == set(mr.MODULE_CHECKS)
    assert rows["pms"]["status"] == "incomplete" and rows["spa"]["status"] == "off"


def test_every_rule_names_existing_fields_only_in_known_shapes():
    for module, spec in mr.MODULE_CHECKS.items():
        assert set(spec) <= {"setup", "usage", "view"}, module
        for item in [*spec.get("setup", []), *spec.get("usage", [])]:
            assert (item["collections"] or item.get("platform")) and item["label"] and item["min_count"] >= 1, (module, item["key"])


@pytest.mark.asyncio
async def test_endpoints_scope_to_the_hotel(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from routers import module_readiness as router

    class Tenants:
        async def find_one(self, query, *_a, **_k):
            return {"id": "t1", "subscription_tier": "basic", "modules": {"spa": False}} if query["id"] == "t1" else None

    db = _DB(rooms=[{"tenant_id": "t1"}])
    db.tenants = Tenants()

    async def effective(doc):
        return {"pms": True, "spa": False}

    monkeypatch.setattr(router, "get_system_db", lambda: db)
    monkeypatch.setattr(router, "effective_tenant_modules", effective)
    monkeypatch.setattr(router, "_require_hotel_admin", lambda user: user.tenant_id)

    body = await router.hotel_module_readiness(SimpleNamespace(tenant_id="t1"))
    assert body["tenant_id"] == "t1" and body["modules"]["spa"]["status"] == "off"
    assert body["modules"]["pms"]["status"] == "incomplete"     # rooms yes, rates no
    with pytest.raises(HTTPException) as missing:
        await router.admin_module_readiness("nope", SimpleNamespace())
    assert missing.value.status_code == 404
