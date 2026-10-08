import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from domains.quality.router import QualityRecordInput, _advance_due, validate_transition


def test_quality_record_normalizes_due_date_and_checklist():
    record = QualityRecordInput(
        kind="audit",
        title="Oda teslim denetimi",
        department="Kat Hizmetleri",
        due_at="2026-10-09T12:00:00+03:00",
        checklist=[{"label": "Banyo temizliği", "result": "pass"}],
    )
    assert record.due_at == "2026-10-09T09:00:00+00:00"
    assert record.checklist[0].required is True


def test_quality_record_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        QualityRecordInput(kind="incident", title="Geçersiz kayıt", department="Operasyon")


def test_capa_cannot_close_without_verification():
    with pytest.raises(HTTPException) as exc:
        validate_transition("pending_verification", "closed", {"_kind": "quality_capa", "checklist": []})
    assert exc.value.status_code == 422


def test_required_failed_checklist_blocks_closure():
    with pytest.raises(HTTPException) as exc:
        validate_transition(
            "pending_verification",
            "closed",
            {"_kind": "quality_audit", "checklist": [{"label": "Kontrol", "required": True, "result": "fail"}]},
        )
    assert exc.value.status_code == 422


def test_verified_capa_can_close():
    validate_transition(
        "pending_verification",
        "closed",
        {"_kind": "quality_capa", "verification_note": "Yerinde doğrulandı", "checklist": [{"required": True, "result": "pass"}]},
    )


def test_recurring_audit_dates_are_normalized_and_advanced():
    record = QualityRecordInput(
        kind="audit",
        title="Aylık havuz denetimi",
        department="Teknik",
        due_at="2026-10-09T12:00:00+03:00",
        recurrence="monthly",
        recurrence_until="2027-01-01",
    )
    assert record.recurrence_until == "2027-01-01T00:00:00+00:00"
    assert _advance_due(record.due_at, record.recurrence) == "2026-11-08T09:00:00+00:00"
