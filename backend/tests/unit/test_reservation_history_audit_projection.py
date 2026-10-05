from routers.reservation_detail import (
    _audit_log_to_reservation_history_entry,
    _history_correlation_ids,
)


def test_audit_change_is_projected_with_operator_facing_details():
    entry = _audit_log_to_reservation_history_entry(
        {
            "id": "audit-1",
            "action": "reservation_modified",
            "correlation_id": "corr-1",
            "timestamp": "2026-09-06T09:00:00+00:00",
            "metadata": {
                "activity_action": "stay_dates_updated",
                "actor_name": "Resepsiyon",
                "source": "PMS",
                "changes": {
                    "check_out": {"from": "2026-09-06T12:00:00+03:00", "to": "2026-09-07T12:00:00+03:00"},
                },
            },
        }
    )

    assert entry["id"] == "audit:audit-1"
    assert entry["action"] == "stay_dates_updated"
    assert entry["actor"] == "Resepsiyon"
    assert entry["details"]["changes"]["check_out"]["from"].startswith("2026-09-06")
    assert entry["details"]["changes"]["check_out"]["to"].startswith("2026-09-07")
    assert entry["created_at"] == "2026-09-06T09:00:00+00:00"


def test_activity_correlations_prevent_audit_timeline_duplicates():
    correlations = _history_correlation_ids(
        [
            {"correlation_id": "corr-top-level"},
            {"details": {"correlation_id": "corr-in-details"}},
        ]
    )

    assert correlations == {"corr-top-level", "corr-in-details"}
