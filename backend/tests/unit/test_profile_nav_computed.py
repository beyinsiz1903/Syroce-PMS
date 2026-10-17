"""The hotel menu follows its property profile as it is now, not a copy."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from domains.admin.property_profiles import get_hidden_nav_config, resolve_tenant_nav, with_resolved_nav

AGENCY_PAGES = {"incoming_agency_contracts", "agency_statements", "agency_readiness"}


def test_sapanca_compact_profile_lists_the_agency_extranet_pages():
    assert AGENCY_PAGES <= set(get_hidden_nav_config("sapanca_kartepe_basic")["visible_nav_items"])


def test_linked_hotel_reads_the_profile_not_its_stale_copy():
    stale = {"nav_profile": "sapanca_kartepe_basic", "visible_nav_items": ["dashboard", "pms"], "nav_item_labels": {}}
    resolved = resolve_tenant_nav(stale)
    assert AGENCY_PAGES <= set(resolved["visible_nav_items"])
    assert resolved["nav_item_labels"] == {"settings": "Yönetim"}
    assert with_resolved_nav(stale)["nav_profile"] == "sapanca_kartepe_basic"


def test_unlinked_hotel_keeps_its_stored_lists():
    legacy = {"property_type": "boutique", "hidden_nav_items": ["group_bookings"], "hidden_nav_groups": ["infrastructure"]}
    resolved = resolve_tenant_nav(legacy)
    assert resolved["hidden_nav_items"] == ["group_bookings"]
    assert resolved["hidden_nav_groups"] == ["infrastructure"]
    assert resolved["visible_nav_items"] == [] and resolved["nav_item_labels"] == {}


@pytest.mark.asyncio
async def test_session_payload_carries_the_profile_menu(monkeypatch):
    import core.subscriptions as subs
    from domains.admin.router.tenants import _tenant_session_payload

    async def none(*_a, **_k):
        return {}

    monkeypatch.setattr(subs, "active_products_by_tenant", none)
    payload = await _tenant_session_payload({
        "id": "t1", "property_name": "Sapanca", "subscription_tier": "basic", "modules": {},
        "nav_profile": "sapanca_kartepe_basic", "visible_nav_items": ["dashboard"],
    })
    assert AGENCY_PAGES <= set(payload["visible_nav_items"])


# ── Linking existing hotels (scripts/link_tenant_nav_profiles.py) ───────────

def _copy_of(profile, **extra):
    return {"id": extra.pop("id", "t1"), "property_name": "Otel", **get_hidden_nav_config(profile), **extra}


def test_links_only_untouched_copies():
    from scripts.link_tenant_nav_profiles import decide

    assert decide(_copy_of("boutique_hotel", property_type="boutique")) == ("link", "boutique_hotel")  # alias
    edited = _copy_of("boutique_hotel", property_type="boutique_hotel")
    edited["hidden_nav_items"] = [*edited["hidden_nav_items"], "spa"]
    assert decide(edited) == ("differs:hidden_nav_items", "boutique_hotel")
    assert decide({"id": "t2", "property_type": "castle"})[0] == "no_profile"
    assert decide({"id": "t3", "nav_profile": "camping"})[0] == "already_linked"


class _Tenants:
    def __init__(self, docs, before_update=None):
        self.docs = docs
        self.before_update = before_update

    def find(self, *_a, **_k):
        docs = deepcopy(self.docs)

        async def gen():
            for doc in docs:
                yield doc
        return gen()

    async def update_one(self, query, update):
        if self.before_update:
            self.before_update(self.docs)
            self.before_update = None
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(deepcopy(update["$set"]))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            if isinstance(expected, dict) and "$exists" in expected:
                if (key in doc) != expected["$exists"]:
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if doc.get("nav_profile_link_run") == query["nav_profile_link_run"]:
                for key in update["$unset"]:
                    doc.pop(key, None)
                count += 1
        return SimpleNamespace(modified_count=count)


class _Runs:
    def __init__(self):
        self.rows = []

    async def insert_one(self, row):
        self.rows.append(row)


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_apply_links_and_undo_restores():
    from scripts.link_tenant_nav_profiles import run

    copy = _copy_of("boutique_hotel", id="a", property_type="boutique")
    edited = {**_copy_of("city_hotel", id="b", property_type="hotel"), "hidden_nav_items": ["custom"]}
    db = SimpleNamespace(tenants=_Tenants([copy, edited]), nav_profile_link_runs=_Runs())

    dry = await run(db, apply=False, undo=None)
    assert dry["decisions"] == {"link": 1, "differs:hidden_nav_items": 1}
    assert "nav_profile" not in db.tenants.docs[0] and not db.nav_profile_link_runs.rows

    applied = await run(db, apply=True, undo=None)
    assert applied["linked"] == 1
    assert db.tenants.docs[0]["nav_profile"] == "boutique_hotel"
    assert "nav_profile" not in db.tenants.docs[1]
    assert db.tenants.docs[0]["hidden_nav_items"] == copy["hidden_nav_items"]   # lists untouched

    undone = await run(db, apply=False, undo=applied["run_id"])
    assert undone["unlinked"] == 1 and "nav_profile" not in db.tenants.docs[0]


@pytest.mark.parametrize("new_type", ["pension", None])
@pytest.mark.asyncio
async def test_link_skips_a_property_type_changed_after_read(new_type):
    from scripts.link_tenant_nav_profiles import run

    original = _copy_of("city_hotel", property_type="city_hotel")
    db = SimpleNamespace(
        tenants=_Tenants([deepcopy(original)], before_update=lambda docs: docs[0].update(property_type=new_type)),
        nav_profile_link_runs=_Runs(),
    )

    result = await run(db, apply=True, undo=None)

    assert result["linked"] == 0
    assert result["skipped_changed"] == 1
    assert db.tenants.docs[0] == {**original, "property_type": new_type}


@pytest.mark.asyncio
async def test_link_skips_a_property_type_removed_after_read():
    from scripts.link_tenant_nav_profiles import run

    original = _copy_of("city_hotel", property_type="city_hotel")
    db = SimpleNamespace(
        tenants=_Tenants([deepcopy(original)], before_update=lambda docs: docs[0].pop("property_type")),
        nav_profile_link_runs=_Runs(),
    )

    result = await run(db, apply=True, undo=None)

    assert result["linked"] == 0
    assert result["skipped_changed"] == 1
    assert db.tenants.docs[0] == {key: value for key, value in original.items() if key != "property_type"}


@pytest.mark.asyncio
async def test_link_still_skips_labels_changed_after_read():
    from scripts.link_tenant_nav_profiles import run

    original = _copy_of("city_hotel", property_type="city_hotel")
    changed_labels = {"settings": "Custom management"}
    db = SimpleNamespace(
        tenants=_Tenants([deepcopy(original)], before_update=lambda docs: docs[0].update(nav_item_labels=changed_labels)),
        nav_profile_link_runs=_Runs(),
    )

    result = await run(db, apply=True, undo=None)

    assert result["linked"] == 0
    assert result["skipped_changed"] == 1
    assert db.tenants.docs[0] == {**original, "nav_item_labels": changed_labels}


def test_link_filter_checks_raw_property_type_before_alias_resolution():
    from scripts.link_tenant_nav_profiles import _cas_filter, decide

    original = _copy_of("boutique_hotel", property_type="boutique")
    assert decide(original) == ("link", "boutique_hotel")
    assert _cas_filter(original)["property_type"] == "boutique"
