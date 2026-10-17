"""Agency Extranet is its own module, separate from the OTA channel manager."""

from types import SimpleNamespace

import pytest

from core import entitlement
from core.helpers import get_tenant_modules


@pytest.mark.parametrize("modules,expected", [
    ({"channel_manager": True}, True),             # existing hotels keep access
    ({"channel_manager": False}, False),
    ({"channel_manager": False, "agency_extranet": True}, True),   # agency extranet without OTA
    ({"channel_manager": True, "agency_extranet": False}, False),  # OTA without agency extranet
])
def test_agency_extranet_follows_the_channel_manager_until_set(modules, expected):
    assert get_tenant_modules({"subscription_tier": "basic", "modules": modules})["agency_extranet"] is expected


def test_without_explicit_modules_it_follows_the_plan_channel_manager():
    for tier in ("mini", "basic", "professional", "enterprise"):
        merged = get_tenant_modules({"subscription_tier": tier})
        assert merged["agency_extranet"] == merged.get("channel_manager", False)


@pytest.mark.parametrize("path,module", [
    ("/api/marketplace/v1/extranet/profile", "agency_extranet"),
    ("/api/marketplace/hotel/statements/s1", "agency_extranet"),
    ("/api/marketplace/hotel/agency-readiness", "agency_extranet"),
    ("/api/marketplace/incoming-requests/c1/approve", "agency_extranet"),
    ("/api/marketplace/products", "channel_manager"),  # hotel supplies market: unchanged here
    ("/api/channel-manager/unified-rate-manager/agency-rates", ("channel_manager", "agency_extranet")),
    ("/api/channel-manager/connections", "channel_manager"),
])
def test_route_modules(path, module):
    assert entitlement._match_route_module(path) == module


async def _status(monkeypatch, path, granted):
    async def access(tenant_id, module):
        return module in granted

    async def not_admin(_user):
        return False

    async def no_usage(*_a, **_k):
        return None

    monkeypatch.setattr(entitlement, "_check_module_access", access)
    monkeypatch.setattr(entitlement, "_is_super_admin_user", not_admin)
    monkeypatch.setattr(entitlement, "record_usage", no_usage)
    monkeypatch.setattr(entitlement, "_get_token_from_headers", lambda _h: "t")
    monkeypatch.setattr(entitlement, "_decode_token_payload", lambda _t: {"tenant_id": "t1", "user_id": "u1"})
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    await entitlement.EntitlementMiddleware(app)({"type": "http", "path": path, "method": "GET", "headers": []}, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


@pytest.mark.asyncio
async def test_agency_only_hotel_shares_rates_but_has_no_ota(monkeypatch):
    granted = {"agency_extranet"}
    assert await _status(monkeypatch, "/api/marketplace/hotel/statements", granted) == 200
    assert await _status(monkeypatch, "/api/channel-manager/unified-rate-manager/agency-rates", granted) == 200
    assert await _status(monkeypatch, "/api/channel-manager/connections", granted) == 403


@pytest.mark.asyncio
async def test_ota_only_hotel_has_no_agency_extranet(monkeypatch):
    granted = {"channel_manager"}
    assert await _status(monkeypatch, "/api/marketplace/incoming-requests", granted) == 403
    assert await _status(monkeypatch, "/api/channel-manager/unified-rate-manager/grid", granted) == 200


# ── Each destination needs its own module, checked before any write ─────────

class _NoDB:
    """Any database access fails the test: the gate must come first."""

    def __getattr__(self, name):
        raise AssertionError(f"database touched before the module check: {name}")


async def _bulk(monkeypatch, granted, **body):
    from fastapi import HTTPException

    from domains.channel_manager import unified_rate_manager_router as rates

    async def exely(_tenant_id):
        return {"provider": "exely", "connection": {"id": "c1"}}

    async def access(_tenant_id, module):
        return module in granted

    class PassedGate(Exception):
        pass

    def stop_after_gate(_targets):
        # The next step after the module checks: nothing saved or sent yet.
        raise PassedGate

    monkeypatch.setattr(rates, "_detect_active_provider", exely)
    monkeypatch.setattr(entitlement, "_check_module_access", access)
    monkeypatch.setattr(rates, "_ari_write_block_for_targets", stop_after_gate)
    monkeypatch.setattr(rates, "db", _NoDB())
    request = rates.UnifiedBulkUpdateRequest(start_date="2026-12-01", end_date="2026-12-02", rate=100, update_fields=["rate"], **body)
    try:
        await rates.unified_bulk_grid_update(request, SimpleNamespace(tenant_id="t1", id="u1"), None)
    except HTTPException as exc:
        return exc.status_code, exc.detail
    except PassedGate:
        return "passed_gate", None
    raise AssertionError("the request neither stopped at the gate nor reached the next step")


@pytest.mark.asyncio
async def test_agency_only_hotel_cannot_push_to_an_existing_ota_connection(monkeypatch):
    status, detail = await _bulk(monkeypatch, {"agency_extranet"}, agency_ids=["a1"])
    assert status == 403 and detail["required_module"] == "channel_manager"
    assert (await _bulk(monkeypatch, {"agency_extranet"}, agency_ids=["a1"], agencies_only=True))[0] == "passed_gate"


@pytest.mark.asyncio
async def test_channel_manager_only_hotel_cannot_share_rates_with_agencies(monkeypatch):
    status, detail = await _bulk(monkeypatch, {"channel_manager"}, agency_ids=["a1"], agencies_only=True)
    assert status == 403 and detail["required_module"] == "agency_extranet"
    assert (await _bulk(monkeypatch, {"channel_manager"}))[0] == "passed_gate"


@pytest.mark.asyncio
async def test_agency_rate_overrides_need_agency_extranet(monkeypatch):
    from fastapi import HTTPException

    from domains.channel_manager import unified_rate_manager_router as rates

    async def access(_tenant_id, module):
        return module == "channel_manager"

    monkeypatch.setattr(entitlement, "_check_module_access", access)
    monkeypatch.setattr(rates, "db", _NoDB())
    user = SimpleNamespace(tenant_id="t1", id="u1")
    with pytest.raises(HTTPException) as denied:
        await rates.delete_agency_rate_overrides("a1", user, None)
    assert denied.value.status_code == 403


# ── Transition follows effective channel-manager access ─────────────────────
# Server checks, the session and /subscription/current share one decision.
# No test reaches a database: tenants and subscriptions are in memory.

def _offline(monkeypatch, tenants, subscriptions):
    """tenants: {id: modules}; subscriptions: {(tenant_id, module)}."""
    import core.subscriptions as subs

    queries = []

    class Tenants:
        async def find_one(self, query, *_a, **_k):
            tid = query.get("id")
            return {"id": tid, "subscription_tier": "basic", "modules": tenants[tid]} if tid in tenants else None

    async def subscribed(tenant_ids, module):
        queries.append(module)
        return {tid for tid in tenant_ids if (tid, module) in subscriptions}

    async def has(tenant_id, module):
        return (tenant_id, module) in subscriptions

    async def products(tenant_ids):
        queries.append("products")
        return {tid: {m for t, m in subscriptions if t == tid} for tid in tenant_ids}

    monkeypatch.setattr(entitlement, "db", SimpleNamespace(tenants=Tenants()))
    monkeypatch.setattr(subs, "subscribed_tenant_ids", subscribed)
    monkeypatch.setattr(subs, "active_products_by_tenant", products)
    monkeypatch.setattr(subs, "tenant_has_module", has)
    monkeypatch.setattr(subs, "_db", _NoDB)
    return queries


@pytest.mark.parametrize("modules,subscribed,expected", [
    ({"channel_manager": False}, {"channel_manager"}, True),     # store subscription carries over
    ({"channel_manager": False}, set(), False),
    ({"channel_manager": False, "agency_extranet": False}, {"channel_manager"}, False),  # explicit wins
    ({"channel_manager": False, "agency_extranet": False}, {"agency_extranet"}, True),   # its own subscription
])
@pytest.mark.asyncio
async def test_transition_uses_effective_channel_manager_access(monkeypatch, modules, subscribed, expected):
    _offline(monkeypatch, {"t1": modules}, {("t1", m) for m in subscribed})
    assert await entitlement._check_module_access("t1", "agency_extranet") is expected
    doc = {"id": "t1", "subscription_tier": "basic", "modules": modules}
    assert (await entitlement.effective_tenant_modules(doc))["agency_extranet"] is expected


@pytest.mark.asyncio
async def test_lists_resolve_subscriptions_in_one_query(monkeypatch):
    docs = [{"id": f"t{i}", "subscription_tier": "basic", "modules": {"channel_manager": False}} for i in range(50)]
    queries = _offline(monkeypatch, {}, {("t3", "channel_manager"), ("t7", "agency_extranet")})
    result = await entitlement.effective_tenant_modules_many(docs)
    assert [i for i, mods in enumerate(result) if mods["agency_extranet"]] == [3, 7]
    assert len(queries) == 1


@pytest.mark.asyncio
async def test_subscription_current_shows_inherited_agency_extranet(monkeypatch):
    """The reviewer's case: server allowed it, /subscription/current said false."""
    from domains.admin.router import subscription as sub_router

    tenant = {"id": "t1", "subscription_tier": "basic", "modules": {"channel_manager": False}, "property_name": "Demo"}
    _offline(monkeypatch, {"t1": tenant["modules"]}, {("t1", "channel_manager")})

    class Coll:
        def __init__(self, doc=None):
            self.doc = doc

        async def find_one(self, *_a, **_k):
            return dict(self.doc)

        async def count_documents(self, *_a, **_k):
            return 0

    async def no_entitlements(_tenant_id):
        return {}

    monkeypatch.setattr(sub_router, "db", SimpleNamespace(tenants=Coll(tenant), rooms=Coll(), users=Coll()))
    monkeypatch.setattr(sub_router, "_get_full_entitlements", no_entitlements)
    body = await sub_router.get_current_subscription(SimpleNamespace(tenant_id="t1", id="u1"))
    assert body["modules"]["agency_extranet"] is True
    assert body["tenant"]["modules"]["agency_extranet"] is True
    assert await entitlement._check_module_access("t1", "agency_extranet") is True


@pytest.mark.asyncio
async def test_session_payload_carries_the_same_decision(monkeypatch):
    from routers.auth import _with_effective_agency_extranet

    _offline(monkeypatch, {}, {("t1", "channel_manager")})
    session = await _with_effective_agency_extranet({"id": "t1", "subscription_tier": "basic", "modules": {"channel_manager": False}})
    assert session["modules"]["agency_extranet"] is True
    explicit_off = {"id": "t1", "subscription_tier": "basic", "modules": {"agency_extranet": False}}
    assert (await _with_effective_agency_extranet(explicit_off))["modules"]["agency_extranet"] is False


# ── Saving other modules must not freeze a computed Agency Extranet value ──

def _admin_patch_env(monkeypatch, stored_modules, subscriptions):
    from domains.admin.router import tenants as tenants_router

    state = {"modules": dict(stored_modules)}

    class Tenants:
        async def find_one(self, *_a, **_k):
            return {"id": "t1", "subscription_tier": "basic", "modules": dict(state["modules"])}

        async def update_one(self, _query, update):
            state["modules"] = dict(update["$set"]["modules"])
            return SimpleNamespace(matched_count=1)

    async def noop(*_a, **_k):
        return None

    _offline(monkeypatch, {}, subscriptions)
    monkeypatch.setattr(tenants_router, "get_system_db", lambda: SimpleNamespace(tenants=Tenants()))
    monkeypatch.setattr(tenants_router, "_invalidate_admin_tenants_cache", lambda *_a: None)
    monkeypatch.setattr("core.helpers.invalidate_tenant_doc_cache", lambda *_a: None)
    monkeypatch.setattr("core.audit.log_audit_event", noop)
    return tenants_router, state


async def _save(tenants_router, modules):
    from domains.admin.schemas import TenantModulesUpdate

    admin = SimpleNamespace(id="sa", name="SA", email="sa@x", tenant_id="ops")
    return await tenants_router.update_tenant_modules("t1", TenantModulesUpdate(modules=modules), admin)


@pytest.mark.asyncio
async def test_saving_another_module_keeps_inherited_agency_extranet_computed(monkeypatch):
    """The reviewer's case: inherited from a channel-manager subscription,
    the admin enables SPA only; the screen echoes agency_extranet=true."""
    subscriptions = {("t1", "channel_manager")}
    tenants_router, state = _admin_patch_env(monkeypatch, {"channel_manager": False}, subscriptions)
    await _save(tenants_router, {"channel_manager": False, "spa": True, "agency_extranet": True})
    assert "agency_extranet" not in state["modules"]          # not frozen
    assert state["modules"]["spa"] is True
    _offline(monkeypatch, {"t1": state["modules"]}, subscriptions)
    assert await entitlement._check_module_access("t1", "agency_extranet") is True
    subscriptions.clear()                                      # subscription removed
    assert await entitlement._check_module_access("t1", "agency_extranet") is False


@pytest.mark.asyncio
async def test_changing_agency_extranet_is_stored_as_a_decision(monkeypatch):
    tenants_router, state = _admin_patch_env(monkeypatch, {"channel_manager": True}, set())
    await _save(tenants_router, {"channel_manager": True, "agency_extranet": False})   # shown true → off
    assert state["modules"]["agency_extranet"] is False
    tenants_router, state = _admin_patch_env(monkeypatch, {"channel_manager": False}, set())
    await _save(tenants_router, {"channel_manager": False, "agency_extranet": True})   # shown false → on
    assert state["modules"]["agency_extranet"] is True
    tenants_router, state = _admin_patch_env(monkeypatch, {"agency_extranet": True}, set())
    await _save(tenants_router, {"agency_extranet": True, "spa": True})                # explicit stays
    assert state["modules"]["agency_extranet"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("flags,bought", [
    ({"quick_id_integration": True}, set()),        # store product flag on the hotel
    ({}, {"quick_id_integration"}),                 # active store subscription
])
async def test_store_alias_shows_as_the_canonical_module(monkeypatch, flags, bought):
    """Reviewer's case: the store enables quick_id_integration; the server
    accepts it as quick_id, so the session must say quick_id=true."""
    _offline(monkeypatch, {"t1": flags}, {("t1", key) for key in bought})
    doc = {"id": "t1", "subscription_tier": "basic", "modules": flags}
    assert (await entitlement.effective_tenant_modules(doc))["quick_id"] is True
    assert (await entitlement.effective_tenant_modules({"id": "t1", "subscription_tier": "basic", "modules": {}}))["quick_id"] is (bool(bought))


@pytest.mark.asyncio
async def test_module_screens_get_the_hotels_own_choices_apart_from_defaults(monkeypatch):
    """The effective map carries plan defaults; module_preferences carries only
    what the hotel stored, so a screen can tell "not in plan" from "disabled"."""
    tenants_router, _state = _admin_patch_env(monkeypatch, {"spa": False}, set())
    body = await _save(tenants_router, {"spa": False, "pms": True})
    assert body["module_preferences"] == {"spa": False}     # pms=true came back as shown: an echo
    assert body["modules"]["housekeeping"] is True        # plan default, not a choice
    assert "housekeeping" not in body["module_preferences"]


@pytest.mark.asyncio
async def test_publishing_one_module_does_not_turn_echoed_defaults_into_choices(monkeypatch):
    """Reviewer's case: a Mini hotel with no stored choices enables only SPA;
    the screen sends the whole map. Only spa is stored, so maintenance stays
    'not in plan' (computed), not 'disabled by the admin'."""
    tenants_router, state = _admin_patch_env(monkeypatch, {}, set())
    shown = await entitlement.effective_tenant_modules({"id": "t1", "subscription_tier": "basic", "modules": {}})
    sent = {**shown, "spa": True}
    body = await _save(tenants_router, sent)
    assert state["modules"] == {"spa": True}
    assert body["module_preferences"] == {"spa": True}
    assert "maintenance" not in body["module_preferences"]
    # A stored choice stays stored even when sent back unchanged.
    tenants_router, state = _admin_patch_env(monkeypatch, {"maintenance": False}, set())
    await _save(tenants_router, {"maintenance": False, "spa": True})
    assert state["modules"] == {"maintenance": False, "spa": True}


@pytest.mark.asyncio
async def test_plan_reset_stores_defaults_not_admin_choices(monkeypatch):
    """Reviewer's case: Basic -> Mini with "reset modules to plan defaults".
    The defaults are stored for access, but they are not choices: maintenance
    must read 'not in plan', also after reloading the list."""
    from domains.admin.router import tenants as tenants_router

    record = {"id": "t1", "subscription_tier": "basic", "modules": {"maintenance": True, "spa": True}}

    class Tenants:
        async def find_one(self, *_a, **_k):
            return dict(record)

        async def update_one(self, _query, update):
            record.update(update["$set"])
            return SimpleNamespace(matched_count=1)

    _offline(monkeypatch, {}, set())
    monkeypatch.setattr(tenants_router, "db", SimpleNamespace(tenants=Tenants()))
    monkeypatch.setattr(tenants_router, "_invalidate_admin_tenants_cache", lambda *_a: None)
    admin = SimpleNamespace(id="sa", tenant_id="ops")
    body = await tenants_router.update_tenant_tier("t1", {"tier": "mini", "reset_modules": True}, admin)

    assert record["module_choice_keys"] == []
    assert body["tenant"]["module_preferences"] == {}                 # nothing chosen
    assert tenants_router._module_preferences(record) == {}           # same after reload
    assert record["modules"]["maintenance"] is False                  # access: Mini defaults

    # A later save of the whole map keeps them defaults; only a change is a choice.
    tenants_router2, state = _admin_patch_env(monkeypatch, record["modules"], set())
    state_doc = {"subscription_tier": "mini", "modules": dict(record["modules"]), "module_choice_keys": []}
    monkeypatch.setattr(tenants_router2, "get_system_db", lambda: SimpleNamespace(tenants=_Store(state_doc)))
    shown = await entitlement.effective_tenant_modules({"id": "t1", **state_doc})
    body = await _save(tenants_router2, {**shown, "spa": True})
    assert body["module_preferences"] == {"spa": True}


class _Store:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, *_a, **_k):
        return {"id": "t1", **self.doc}

    async def update_one(self, _query, update):
        self.doc.update(update["$set"])
        return SimpleNamespace(matched_count=1)


def test_legacy_records_without_choice_keys_keep_their_stored_flags():
    from domains.admin.router.tenants import _module_preferences

    assert _module_preferences({"modules": {"spa": True, "hr": False}}) == {"spa": True, "hr": False}
    assert _module_preferences({"modules": {"spa": True, "hr": False}, "module_choice_keys": ["spa"]}) == {"spa": True}
