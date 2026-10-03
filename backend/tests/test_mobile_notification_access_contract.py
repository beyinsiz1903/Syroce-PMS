import inspect

from domains.pms.mobile_router import notifications


def test_mobile_department_notifications_require_their_department_module():
    expected_permissions = {
        notifications.get_frontdesk_notifications_mobile: 'require_module("frontdesk")',
        notifications.get_housekeeping_notifications_mobile: 'require_module("housekeeping")',
        notifications.get_maintenance_notifications_mobile: 'require_module("maintenance")',
        notifications.get_fnb_notifications_mobile: 'require_module("pos")',
    }

    for handler, permission in expected_permissions.items():
        assert permission in inspect.getsource(handler)
