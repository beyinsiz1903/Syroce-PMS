import inspect

from domains.pms.mobile_router import search


def test_mobile_guest_and_reservation_search_apply_guest_visibility_policy():
    for handler in (search._search_guests, search._search_reservations):
        source = inspect.getsource(handler)
        assert "protect_guest_row" in source
        assert "current_user" in source


def test_unified_search_passes_the_authenticated_user_to_pii_serializers():
    source = inspect.getsource(search.unified_search)

    assert "_search_guests(tenant_id, q, current_user)" in source
    assert "_search_reservations(tenant_id, q, current_user)" in source
