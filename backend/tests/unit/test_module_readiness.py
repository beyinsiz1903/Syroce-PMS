"""Module readiness from the hotel's own data (core.module_readiness)."""

from datetime import UTC, datetime, timedelta

import pytest

from core import module_readiness as mr

NOW = datetime.now(UTC)


def _matches(doc, query):
    if "$and" in query:
        return all(_matches(doc, part) for part in query["$and"])
    if "$or" in query:
        return any(_matches(doc, part) for part in query["$or"])
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op == "$gte" and (value is None or type(value) is not type(arg) or value < arg):
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

    async def count_documents(self, query, limit=0):
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
    db = _DB(spa_services=[{"tenant_id": "t1", "active": True}], spa_rooms=[{"tenant_id": "t1"}])
    row = await mr.module_readiness(db, "t1", "spa", enabled=True)
    assert row["status"] == "incomplete"
    missing = [item for item in row["setup"] if not item["ok"]]
    assert [(item["key"], item["path"]) for item in missing] == [("spa_therapists", "/spa-wellness")]


@pytest.mark.asyncio
async def test_idle_until_recent_use_then_active_with_iso_or_datetime_dates():
    setup = {"spa_services": [{"tenant_id": "t1"}], "spa_rooms": [{"tenant_id": "t1"}], "spa_therapists": [{"tenant_id": "t1"}]}
    old = _DB(**setup, spa_appointments=[{"tenant_id": "t1", "created_at": _recent(days=90)}])
    assert (await mr.module_readiness(old, "t1", "spa", enabled=True))["status"] == "idle"
    fresh = _DB(**setup, spa_appointments=[{"tenant_id": "t1", "created_at": _recent()}])
    assert (await mr.module_readiness(fresh, "t1", "spa", enabled=True))["status"] == "active"
    # Contact-center calls store datetimes, not strings.
    calls = _DB(contact_center_voice_numbers=[{"tenant_id": "t1"}],
                contact_center_calls=[{"tenant_id": "t1", "started_at": _recent(as_datetime=True)}])
    assert (await mr.module_readiness(calls, "t1", "contact_center", enabled=True))["status"] == "active"


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
            assert item["collections"] and item["label"] and item["min_count"] >= 1, (module, item["key"])


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
