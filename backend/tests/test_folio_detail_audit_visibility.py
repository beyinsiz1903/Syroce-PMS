from modules.pms_core.folio_detail_service import FolioDetailService


def test_merge_audit_trails_includes_financial_chain_records_newest_first():
    legacy = [
        {
            "id": "legacy-a",
            "action": "folio_opened",
            "entity_id": "folio-a",
            "performed_by": "user-a",
            "timestamp": "2026-08-17T09:00:00+00:00",
        }
    ]
    chained = [
        {
            "id": "chain-a",
            "operation_name": "folio_payment_voided",
            "entity_id": "payment-a",
            "actor_id": "user-b",
            "timestamp": "2026-08-17T10:00:00+00:00",
        }
    ]

    result = FolioDetailService._merge_audit_trails(legacy, chained)

    assert [entry["action"] for entry in result] == [
        "folio_payment_voided",
        "folio_opened",
    ]
    assert result[0]["performed_by"] == "user-b"


def test_merge_audit_trails_deduplicates_same_record():
    duplicate = {
        "id": "audit-a",
        "action": "payment_voided",
        "entity_id": "payment-a",
        "timestamp": "2026-08-17T10:00:00+00:00",
    }

    result = FolioDetailService._merge_audit_trails([duplicate], [duplicate.copy()])

    assert len(result) == 1


def test_merge_audit_trails_shows_domain_and_central_concession_as_one_event():
    domain = {"id": "domain-comp", "action": "concession_applied", "entity_id": "folio-a",
        "timestamp": "2026-10-24T10:00:00Z", "metadata": {"request_id": "comp-1", "reason": "İkram"}}
    central = {**domain, "id": "central-comp", "entity_id": "booking-a", "actor_id": "operator"}
    result = FolioDetailService._merge_audit_trails([domain], [central])
    assert len(result) == 1 and result[0]["id"] == "central-comp"
    assert result[0]["performed_by"] == "operator"
