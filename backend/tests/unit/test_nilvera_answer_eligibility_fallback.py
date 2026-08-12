from types import SimpleNamespace

import pytest

from tests.nilvera_sandbox_fixture import evaluate_incoming_answer_candidate


PROVIDER_UUID = "11111111-1111-4111-8111-111111111111"


def _summary():
    return SimpleNamespace(provider_uuid=PROVIDER_UUID)


def _detail(answer_code):
    return SimpleNamespace(
        provider_uuid=PROVIDER_UUID,
        invoice_profile="TICARIFATURA",
        invoice_type="SATIS",
        answer_code=answer_code,
    )


def _status(answer_code, status_code="SUCCEED"):
    return SimpleNamespace(
        answer_code=answer_code,
        status_code=status_code,
    )


def test_status_missing_falls_back_to_detail_waiting():
    result = evaluate_incoming_answer_candidate(
        _summary(),
        _detail("waitingForApproval"),
        _status(None),
        target_provider_uuid=PROVIDER_UUID,
    )

    assert result.eligible is True
    assert result.answer_waiting is True
    assert result.provider_ready is True


def test_matching_status_and_detail_waiting_is_eligible():
    result = evaluate_incoming_answer_candidate(
        _summary(),
        _detail("waitingForApproval"),
        _status("waitingForApproval"),
        target_provider_uuid=PROVIDER_UUID,
    )

    assert result.eligible is True


@pytest.mark.parametrize(
    ("status_answer", "detail_answer"),
    [
        ("approved", "waitingForApproval"),
        ("rejected", "waitingForApproval"),
        ("waitingForApproval", "approved"),
    ],
)
def test_conflicting_nonempty_answer_states_fail_closed(status_answer, detail_answer):
    result = evaluate_incoming_answer_candidate(
        _summary(),
        _detail(detail_answer),
        _status(status_answer),
        target_provider_uuid=PROVIDER_UUID,
    )

    assert result.eligible is False
    assert result.answer_waiting is False


@pytest.mark.parametrize("detail_answer", ["approved", "rejected", "documentAnsweredAutomatically", None])
def test_status_missing_does_not_make_nonwaiting_detail_eligible(detail_answer):
    result = evaluate_incoming_answer_candidate(
        _summary(),
        _detail(detail_answer),
        _status(None),
        target_provider_uuid=PROVIDER_UUID,
    )

    assert result.eligible is False


def test_provider_not_ready_still_fails_closed_with_detail_fallback():
    result = evaluate_incoming_answer_candidate(
        _summary(),
        _detail("waitingForApproval"),
        _status(None, status_code="waiting"),
        target_provider_uuid=PROVIDER_UUID,
    )

    assert result.answer_waiting is True
    assert result.provider_ready is False
    assert result.eligible is False
