from backend.core.helpers import get_tenant_modules
from backend.domains.admin.subscription_models import get_plan_default_modules


def test_pms_lite_defaults_are_explicit_and_narrow():
    modules = get_plan_default_modules("pms_lite")

    assert modules["pms"] is True
    assert modules["reservation_calendar"] is True
    assert modules["housekeeping"] is True
    assert modules["invoices_basic"] is False
    assert modules["channel_manager_lite"] is False
    assert modules["ai_chatbot"] is False
    assert modules["pms.frontdesk"] is True
    assert modules["channels.connections"] is False


def test_pms_lite_plan_wins_over_a_legacy_basic_tier():
    modules = get_tenant_modules({
        "subscription_plan": "pms_lite",
        "subscription_tier": "basic",
    })

    assert modules["pms"] is True
    assert modules["reports"] is False
    assert modules["marketplace"] is False
    assert modules["pms.cashier"] is False
    assert modules["quick_id"] is True


def test_explicit_tenant_choice_still_overrides_pms_lite_default():
    modules = get_tenant_modules({
        "subscription_plan": "pms_lite",
        "modules": {"quick_id": True},
    })

    assert modules["quick_id"] is True
