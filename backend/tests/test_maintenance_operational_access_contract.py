import inspect

from domains.pms import maintenance_router


def test_sensitive_maintenance_reads_are_not_login_only():
    """Costs, staff activity and asset health must use their write-side permission."""
    expected_permissions = {
        maintenance_router.get_maintenance_work_orders: 'require_module_v99("housekeeping")',
        maintenance_router.get_repeat_issues: 'require_module_v99("housekeeping")',
        maintenance_router.get_maintenance_sla: 'require_module_v99("housekeeping")',
        maintenance_router.get_maintenance_tasks: 'require_module_v99("housekeeping")',
        maintenance_router.get_maintenance_parts_inventory: 'require_op("manage_sales")',
        maintenance_router.list_maintenance_assets: 'require_op("view_system_diagnostics")',
        maintenance_router.list_preventive_plans: 'require_op("view_system_diagnostics")',
        maintenance_router.get_room_devices: 'require_op("view_system_diagnostics")',
        maintenance_router.get_energy_consumption: 'require_op("view_system_diagnostics")',
    }

    for handler, permission in expected_permissions.items():
        assert permission in inspect.getsource(handler)


def test_work_order_reporting_allows_front_desk_without_exposing_the_board():
    source = inspect.getsource(maintenance_router.create_maintenance_work_order)

    assert 'require_any_module("housekeeping", "frontdesk")' in source


def test_iot_commands_are_tenant_owned_and_traceable():
    source = inspect.getsource(maintenance_router.control_smart_device)

    assert '"tenant_id": current_user.tenant_id' in source
    assert '"executed_by": current_user.id' in source
    assert '"id": device_id, "tenant_id": current_user.tenant_id' in source
