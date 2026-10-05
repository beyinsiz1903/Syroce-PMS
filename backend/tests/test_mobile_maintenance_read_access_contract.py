import inspect

from domains.pms.mobile_router import maintenance


def test_mobile_maintenance_reads_require_maintenance_access():
    """Asset history, inventory cost and task images must not be login-only."""
    handlers = (
        maintenance.get_pm_schedule_mobile,
        maintenance.get_sla_configurations,
        maintenance.get_task_photos_mobile,
        maintenance.get_spare_parts_mobile,
        maintenance.get_asset_history_mobile,
        maintenance.get_planned_maintenance_mobile,
        maintenance.get_filtered_tasks_mobile,
    )

    for handler in handlers:
        assert 'require_module("maintenance")' in inspect.getsource(handler)
