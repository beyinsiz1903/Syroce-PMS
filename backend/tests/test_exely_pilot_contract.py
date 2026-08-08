"""Offline safety contract for the manual Exely PMSConnect pilot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from domains.channel_manager.providers.exely.soap_builder import get_soap_action_uri
from tests.integration import test_exely_pilot as pilot

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "exely-pilot.yml"


def _workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def _base_env(monkeypatch, *, operation: str = "discovery", write: bool = False):
    future_date = (datetime.now(UTC).date() + timedelta(days=60)).isoformat()
    values = {
        "APP_ENV": "test",
        "TESTING": "1",
        "MONGO_URL": "mongodb://localhost:27017/hotel_pms_test",
        "DB_NAME": "hotel_pms_test",
        "GITHUB_SHA": "a" * 40,
        "EXELY_PILOT_ACCOUNT_CONFIRMED": "true",
        "EXELY_PILOT_APPROVED_HEAD": "a" * 40,
        "EXELY_PILOT_AVAILABILITY": "2",
        "EXELY_PILOT_CREDENTIAL_SCOPE": "test",
        "EXELY_PILOT_CURRENCY": "USD",
        "EXELY_PILOT_ENDPOINT_URL": "https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc",
        "EXELY_PILOT_HMAC_KEY": "synthetic-hmac-key-with-at-least-32-chars",
        "EXELY_PILOT_HOTEL_CODE": "synthetic-property",
        "EXELY_PILOT_MIN_LOS": "2",
        "EXELY_PILOT_MIN_LOS_ARRIVAL": "2",
        "EXELY_PILOT_OPERATION": operation,
        "EXELY_PILOT_PASSWORD": "synthetic-password",
        "EXELY_PILOT_RATE": "100.00",
        "EXELY_PILOT_RATE_PLAN_CODE": "synthetic-rate",
        "EXELY_PILOT_ROOM_TYPE_CODE": "synthetic-room",
        "EXELY_PILOT_RUN_ID": "123456",
        "EXELY_PILOT_STOP_SELL": "false",
        "EXELY_PILOT_TEST_DATE": future_date,
        "EXELY_PILOT_USERNAME": "synthetic-user",
        "EXELY_PILOT_WRITE_APPROVED": "true" if write else "false",
        "EXELY_PILOT_ACK_DURABLE_PMS_ATTESTED": "true",
        "EXELY_PILOT_ACK_RESERVATION_ID": "synthetic-reservation",
        "EXELY_PILOT_ACK_CONFIRMATION_ID": "synthetic-confirmation",
        "EXELY_PILOT_ACK_CREATE_DATETIME": "2030-01-01T09:00:00Z",
        "EXELY_PILOT_ACK_LAST_MODIFY_DATETIME": "2030-01-01T10:00:00Z",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_workflow_is_manual_single_mode_and_exact_head_gated():
    workflow = _workflow()
    dispatch = workflow["on"]["workflow_dispatch"]
    inputs = dispatch["inputs"]

    assert inputs["operation"]["options"] == [
        "discovery",
        "reservation_read",
        "availability",
        "rate",
        "stop_sell",
        "min_los",
        "min_los_arrival",
        "reservation_ack",
    ]
    assert inputs["confirm_provider_write"]["default"] == "false"
    assert inputs["approved_head_sha"]["required"] == "true"
    assert list(workflow["on"]) == ["workflow_dispatch"]

    job = workflow["jobs"]["exely-pilot"]
    gate = next(step for step in job["steps"] if step.get("name") == "Validate exact-head approval and single-operation gate")
    assert "BLOCKED_READONLY_WRITE_CONFLICT" in gate["run"]
    assert "BLOCKED_PROVIDER_WRITE_NOT_APPROVED" in gate["run"]
    assert "BLOCKED_EXACT_HEAD_MISMATCH" in gate["run"]


def test_workflow_uses_protected_environment_and_exact_targets():
    workflow = _workflow()
    job = workflow["jobs"]["exely-pilot"]
    run_steps = [step for step in job["steps"] if step.get("name", "").startswith("Run one gated Exely")]
    scripts = "\n".join(step["run"] for step in run_steps)

    assert job["environment"] == "exely-pilot"
    assert job["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert len(run_steps) == 2
    assert "test_exely_pilot_readonly" in scripts
    assert "test_exely_pilot_single_write" in scripts
    assert "pytest -m" not in scripts


def test_workflow_requires_both_normal_exact_head_workflows():
    workflow = _workflow()
    gate = next(step for step in workflow["jobs"]["exely-pilot"]["steps"] if step.get("name") == "Require successful exact-head normal workflows")
    script = gate["run"]

    assert "ci-cd.yml" in script
    assert "frontend-quality.yml" in script
    assert ".headSha" in script
    assert "${GITHUB_SHA}" in script
    assert '.event == \\"push\\"' in script
    assert '.conclusion == \\"success\\"' in script


def test_workflow_requires_exact_head_backend_quality_jobs_without_deploy():
    workflow = _workflow()
    gate = next(step for step in workflow["jobs"]["exely-pilot"]["steps"] if step.get("name") == "Require successful exact-head normal workflows")
    script = gate["run"]

    for job_name in (
        "lockfile-guard",
        "backend-lint",
        "frontend-lint",
        "backend-test",
        "battle-e2e",
        "load-test",
        "frontend-build",
        "security-scan",
    ):
        assert f'"{job_name}"' in script
    assert "BLOCKED_EXACT_HEAD_REQUIRED_JOB_NOT_GREEN" in script
    assert "verify_required_jobs \\" in script
    assert '"ci-cd.yml" \\' in script
    assert 'verify_completed_workflow "frontend-quality.yml"' in script
    assert 'verify_completed_workflow "ci-cd.yml"' not in script
    assert '"deploy-production"' not in script
    assert '"deploy-staging"' not in script


def test_workflow_scopes_ari_and_ack_secrets_to_mutually_exclusive_steps():
    workflow = _workflow()
    job = workflow["jobs"]["exely-pilot"]
    common_secrets = {
        "EXELY_PILOT_USERNAME",
        "EXELY_PILOT_PASSWORD",
        "EXELY_PILOT_HOTEL_CODE",
        "EXELY_PILOT_HMAC_KEY",
    }
    ari_secrets = {
        "EXELY_PILOT_ROOM_TYPE_CODE",
        "EXELY_PILOT_RATE_PLAN_CODE",
    }
    ack_secrets = {
        "EXELY_PILOT_ACK_RESERVATION_ID",
        "EXELY_PILOT_ACK_CONFIRMATION_ID",
        "EXELY_PILOT_ACK_CREATE_DATETIME",
        "EXELY_PILOT_ACK_LAST_MODIFY_DATETIME",
    }
    ari_step = next(step for step in job["steps"] if step.get("name") == "Run one gated Exely discovery or ARI target")
    ack_step = next(step for step in job["steps"] if step.get("name") == "Run one gated Exely acknowledgement target")

    assert ari_step["if"] == "inputs.operation != 'reservation_ack'"
    assert ack_step["if"] == "inputs.operation == 'reservation_ack'"
    assert common_secrets | ari_secrets <= set(ari_step["env"])
    assert ack_secrets.isdisjoint(ari_step["env"])
    assert common_secrets | ack_secrets <= set(ack_step["env"])
    assert ari_secrets.isdisjoint(ack_step["env"])
    for step in job["steps"]:
        if step.get("name") not in {ari_step["name"], ack_step["name"]}:
            assert (common_secrets | ari_secrets | ack_secrets).isdisjoint(step.get("env", {}))


def test_workflow_pins_official_test_host_and_test_scope():
    workflow = _workflow()
    run_steps = [step for step in workflow["jobs"]["exely-pilot"]["steps"] if step.get("name", "").startswith("Run one gated Exely")]

    assert all(step["env"]["EXELY_PILOT_ENDPOINT_URL"] == "https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc" for step in run_steps)
    assert all("EXELY_PILOT_CREDENTIAL_SCOPE" in step["env"] for step in run_steps)


def test_settings_fail_closed_for_unapproved_host(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("EXELY_PILOT_ENDPOINT_URL", "https://example.invalid")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_UNAPPROVED_PROVIDER_HOST"):
        pilot._load_settings()


def test_settings_fail_closed_for_exact_head_mismatch(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_EXACT_HEAD_MISMATCH"):
        pilot._load_settings()


def test_settings_fail_closed_for_non_test_credential_scope(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("EXELY_PILOT_CREDENTIAL_SCOPE", "production")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_NON_TEST_CREDENTIAL_SCOPE"):
        pilot._load_settings()


def test_settings_fail_closed_without_write_approval(monkeypatch):
    _base_env(monkeypatch, operation="availability", write=False)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_PROVIDER_WRITE_NOT_APPROVED"):
        pilot._load_settings()


def test_ack_requires_separate_durable_pms_attestation(monkeypatch):
    _base_env(monkeypatch, operation="reservation_ack", write=True)
    monkeypatch.setenv("EXELY_PILOT_ACK_DURABLE_PMS_ATTESTED", "false")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_DURABLE_PMS_RESULT_NOT_ATTESTED"):
        pilot._load_settings()


def test_settings_repr_never_contains_credentials_or_provider_identifiers(monkeypatch):
    _base_env(monkeypatch, operation="reservation_ack", write=True)
    settings_repr = repr(pilot._load_settings())

    for sensitive in (
        "synthetic-user",
        "synthetic-password",
        "synthetic-property",
        "synthetic-reservation",
        "synthetic-confirmation",
        "synthetic-hmac-key-with-at-least-32-chars",
    ):
        assert sensitive not in settings_repr


def test_safe_metadata_drops_payload_and_identifier_fields(caplog):
    recorded: list[tuple[str, object]] = []
    sensitive = "synthetic-sensitive-value"

    with caplog.at_level("INFO", logger="exely.pilot"):
        pilot._record_safe_metadata(
            lambda key, value: recorded.append((key, value)),
            {
                "correlation_label": "abcdef123456",
                "provider_write_count": 0,
                "username": sensitive,
                "password": sensitive,
                "hotel_code": sensitive,
                "reservation_id": sensitive,
                "payload": {"value": sensitive},
            },
        )

    assert recorded == [("correlation_label", "abcdef123456"), ("provider_write_count", 0)]
    assert sensitive not in caplog.text


def test_each_ari_operation_builds_one_value(monkeypatch):
    expected = {
        "availability": 2,
        "rate": pilot.Decimal("100.00"),
        "stop_sell": False,
        "min_los": 2,
        "min_los_arrival": 2,
    }

    for operation, expected_value in expected.items():
        _base_env(monkeypatch, operation=operation, write=True)
        settings = pilot._load_settings()
        assert pilot._ari_value(settings) == expected_value


@pytest.mark.asyncio
async def test_transport_guard_allows_one_read_and_at_most_one_write():
    original = AsyncMock(return_value=b"synthetic-response")
    provider = SimpleNamespace(_transport=SimpleNamespace(send_soap=original))
    settings = SimpleNamespace(operation="availability")
    guard = pilot.PilotTransportGuard(provider, settings)

    await provider._transport.send_soap("synthetic", get_soap_action_uri("OTA_HotelAvailRQ"))
    await provider._transport.send_soap("synthetic", get_soap_action_uri("OTA_HotelAvailNotifRQ"))
    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_SECOND_PROVIDER_WRITE_ATTEMPT"):
        await provider._transport.send_soap("synthetic", get_soap_action_uri("OTA_HotelAvailNotifRQ"))

    assert guard.read_count == 1
    assert guard.write_count == 1
    assert original.await_count == 2


@pytest.mark.asyncio
async def test_transport_guard_blocks_unexpected_action_before_provider_call():
    original = AsyncMock(return_value=b"synthetic-response")
    provider = SimpleNamespace(_transport=SimpleNamespace(send_soap=original))
    guard = pilot.PilotTransportGuard(provider, SimpleNamespace(operation="rate"))

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_UNEXPECTED_SOAP_ACTION"):
        await provider._transport.send_soap("synthetic", get_soap_action_uri("OTA_NotifReportRQ"))

    assert guard.write_count == 0
    original.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_consumes_single_write_and_never_retries():
    original = AsyncMock(side_effect=TimeoutError)
    provider = SimpleNamespace(_transport=SimpleNamespace(send_soap=original))
    guard = pilot.PilotTransportGuard(provider, SimpleNamespace(operation="rate"))
    action = get_soap_action_uri("OTA_HotelRateAmountNotifRQ")

    with pytest.raises(TimeoutError):
        await provider._transport.send_soap("synthetic", action)
    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_SECOND_PROVIDER_WRITE_ATTEMPT"):
        await provider._transport.send_soap("synthetic", action)

    assert guard.write_count == 1
    assert original.await_count == 1
