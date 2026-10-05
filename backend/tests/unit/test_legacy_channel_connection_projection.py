from domains.channel_manager.operations_router import _legacy_hotelrunner_connection_projection


def test_projects_active_legacy_hotelrunner_without_credentials():
    projected = _legacy_hotelrunner_connection_projection(
        {
            "id": "legacy-id",
            "is_active": True,
            "property_name": "The Canyon",
            "hr_id": "hotel-123",
            "token": "must-not-leak",
            "auto_sync_reservations": True,
        }
    )

    assert projected == {
        "id": "legacy-hotelrunner-legacy-id",
        "channel_type": "hotelrunner",
        "channel_name": "The Canyon",
        "property_id": "hotel-123",
        "status": "active",
        "is_legacy_connection": True,
        "is_read_only": True,
        "sync_reservations": True,
        "sync_rate_availability": False,
    }
    assert "token" not in projected


def test_does_not_project_inactive_legacy_connection():
    assert _legacy_hotelrunner_connection_projection({"is_active": False}) is None
    assert _legacy_hotelrunner_connection_projection(None) is None
