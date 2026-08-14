from domains.admin.log_normalization import normalize_audit_log


def test_system_logs_normalizes_heterogeneous_audit_rows_without_identifiers():
    rows = [
        {
            "created_at": "2026-08-14T08:30:00Z",
            "event_type": "login succeeded",
            "resource_type": "user session",
            "user_email": "sensitive@example.invalid",
            "changes": {"raw": "must-not-leak"},
        },
        {
            "id": "event-2",
            "timestamp": "2026-08-14T08:29:00+00:00",
            "action": "BOOKING_DELETE",
            "entity_type": "reservation",
            "actor_id": "actor-sensitive",
        },
    ]
    logs = [normalize_audit_log(row) for row in rows]
    rendered = repr(logs)
    assert logs[0]["user"] == "User"
    assert "sensitive@example.invalid" not in rendered
    assert "actor-sensitive" not in rendered
    assert "must-not-leak" not in rendered
    assert logs[1]["action"] == "BOOKING_DELETE"
    assert logs[1]["level"] == "WARN"


def test_system_logs_replaces_invalid_labels_and_timestamps_safely():
    entry = normalize_audit_log(
        {
            "action": "login for secret@example.invalid",
            "entity_type": "session payload/value",
            "timestamp": "not-a-date",
        }
    )

    assert "@" not in entry["action"]
    assert "/" not in entry["entity_type"]
    assert entry["timestamp"].endswith("+00:00")
