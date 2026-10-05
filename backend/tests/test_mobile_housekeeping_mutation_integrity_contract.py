import inspect

from domains.pms.mobile_router import housekeeping


def test_mobile_housekeeping_room_mutations_resolve_the_canonical_tenant_room():
    for handler in (
        housekeeping.create_room_inspection,
        housekeeping.start_cleaning_timer,
        housekeeping.report_maintenance_from_hk,
    ):
        assert "_get_tenant_room_or_404(current_user.tenant_id, room_id)" in inspect.getsource(handler)
        assert "canonical_room_number" in inspect.getsource(handler)


def test_mobile_cleaning_timer_can_only_be_stopped_by_its_owner():
    assert '"staff_id": current_user.id' in inspect.getsource(housekeeping.stop_cleaning_timer)


def test_mobile_room_assignment_uses_tenant_staff_and_real_rooms():
    source = inspect.getsource(housekeeping.assign_hk_tasks)

    assert '"id": staff_id' in source
    assert '"tenant_id": current_user.tenant_id' in source
    assert "canonical_staff_name" in source
    assert "unique_room_ids" in source
    assert "One or more rooms were not found" in source
