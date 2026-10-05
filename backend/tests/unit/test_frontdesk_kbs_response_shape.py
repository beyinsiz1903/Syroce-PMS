"""Regression coverage for the fail-open KBS hand-off response."""

from domains.pms.frontdesk_service import _kbs_job_id


def test_kbs_job_id_accepts_single_job_document():
    assert _kbs_job_id({"id": "kbs-job-1"}) == "kbs-job-1"


def test_kbs_job_id_ignores_batch_response_without_breaking_checkin():
    # Batch KBS enqueue responses are valid integration output.  A check-in
    # already persisted before this value is included in the HTTP response.
    assert _kbs_job_id([{"id": "kbs-job-1"}]) is None


def test_kbs_job_id_ignores_missing_or_invalid_response():
    assert _kbs_job_id(None) is None
    assert _kbs_job_id("unexpected") is None
