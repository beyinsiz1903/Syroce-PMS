import inspect

from domains.pms.mobile_router import maintenance


def test_mobile_maintenance_mutations_validate_enumerated_business_values():
    assert "_require_maintenance_priority(request.priority)" in inspect.getsource(maintenance.create_quick_issue_mobile)
    assert "_require_maintenance_priority(priority)" in inspect.getsource(maintenance.update_sla_configuration)
    assert "_MAINTENANCE_TASK_STATUSES" in inspect.getsource(maintenance.update_task_status_mobile)
    assert "_MAINTENANCE_PHOTO_TYPES" in inspect.getsource(maintenance.upload_task_photo_mobile)


def test_mobile_maintenance_rejects_invalid_sla_and_negative_inventory_usage():
    sla_source = inspect.getsource(maintenance.update_sla_configuration)
    spare_part_source = inspect.getsource(maintenance.use_spare_part_mobile)

    assert "SLA durations must be positive" in sla_source
    assert "Response SLA cannot exceed resolution SLA" in sla_source
    assert "quantity <= 0" in spare_part_source
