import inspect

from domains.pms.mobile_router import housekeeping


def test_mobile_housekeeping_operational_reads_require_housekeeping_access():
    """Task ownership, room state and lost-property data are not login-only."""
    handlers = (
        housekeeping.get_sla_delayed_rooms_mobile,
        housekeeping.get_team_assignments_mobile,
        housekeeping.get_inspection_checklist_template,
        housekeeping.get_lost_found_items,
        housekeeping.get_staff_assignments,
        housekeeping.get_hk_daily_report,
    )

    for handler in handlers:
        assert 'require_module("housekeeping")' in inspect.getsource(handler)
