import inspect

from domains.pms.mobile_router import frontdesk


def test_mobile_frontdesk_request_lists_require_frontdesk_access():
    for handler in (
        frontdesk.get_early_checkin_requests_mobile,
        frontdesk.get_late_checkout_requests_mobile,
    ):
        assert 'require_module_v92("frontdesk")' in inspect.getsource(handler)


def test_mobile_no_show_is_compare_and_set_before_financial_side_effects():
    source = inspect.getsource(frontdesk.process_no_show_mobile)

    assert "_NO_SHOW_ELIGIBLE_STATUSES" in source
    assert '"status": {"$in": list(_NO_SHOW_ELIGIBLE_STATUSES)}' in source
    assert "update_result.modified_count != 1" in source
    assert '"action": "NO_SHOW_PROCESSED"' in source


def test_mobile_room_change_audit_has_a_safe_user_identifier_fallback():
    assert 'getattr(current_user, "user_id", None) or current_user.id' in inspect.getsource(
        frontdesk.change_room_mobile
    )
