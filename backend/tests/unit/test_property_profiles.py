from domains.admin.property_profiles import (
    get_all_property_types,
    get_hidden_nav_config,
    get_modules_for_property_type,
    get_property_profile,
)


def test_sapanca_kartepe_basic_is_a_selectable_ready_setup():
    profiles = {item["key"]: item for item in get_all_property_types()}
    preset = profiles["sapanca_kartepe_basic"]

    assert preset["setup_preset"] is True
    assert preset["recommended_tier"] == "basic"
    assert preset["modules"]["pms"] is True
    assert preset["modules"]["night_audit"] is True
    assert preset["modules"]["channel_manager"] is True
    modules = get_modules_for_property_type("sapanca_kartepe_basic", "basic")
    assert modules["night_audit"] is True
    assert modules["revenue_management"] is True


def test_sapanca_kartepe_navigation_is_fail_closed_to_requested_workspaces():
    profile = get_property_profile("sapanca_kartepe_basic")
    nav = get_hidden_nav_config("sapanca_kartepe_basic")

    assert profile is not None
    assert nav["nav_group_labels"]["system"] == "Kanallar"
    assert nav["nav_item_labels"]["settings"] == "Yönetim"
    assert set(nav["visible_nav_items"]) == {
        "dashboard",
        "reservation_calendar",
        "agency_requests",
        "pms",
        "night_audit",
        "revenue_hub",
        "city_ledger",
        "cashier_workspace",
        "reports_basic",
        "unified_rate_manager",
        "wbe_settings",
        "settings",
    }
