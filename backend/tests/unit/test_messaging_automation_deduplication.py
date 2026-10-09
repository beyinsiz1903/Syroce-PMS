from modules.messaging.automation import automation_rule_key, deduplicate_automation_rules, new_automation_rule


def test_automation_rule_key_uses_delivery_semantics():
    first = {"trigger_event": "checked_out", "template_id": "review", "channel": "whatsapp", "name": "A"}
    renamed = {**first, "name": "B"}

    assert automation_rule_key(first) == automation_rule_key(renamed)


def test_duplicate_rules_keep_oldest_rule():
    rules = [
        {
            "id": "newer",
            "trigger_event": "checked_out",
            "template_id": "review",
            "channel": "whatsapp",
            "created_at": "2026-10-09T10:00:00Z",
        },
        {
            "id": "oldest",
            "trigger_event": "checked_out",
            "template_id": "review",
            "channel": "whatsapp",
            "created_at": "2026-10-08T10:00:00Z",
        },
        {
            "id": "email",
            "trigger_event": "checked_out",
            "template_id": "review",
            "channel": "email",
            "created_at": "2026-10-08T10:00:00Z",
        },
    ]

    result = deduplicate_automation_rules(rules)

    assert [rule["id"] for rule in result] == ["email", "oldest"]


def test_new_rules_include_database_unique_semantic_key():
    rule = new_automation_rule("tenant", "checked_out", "review", "email", "Review")

    assert rule["semantic_key"] == "checked_out:review:email"
