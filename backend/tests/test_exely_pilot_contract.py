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
INTEGRATIONS_REQUIREMENTS = ROOT / "backend" / "requirements" / "integrations.txt"
POST_INSTALL = ROOT / "backend" / "scripts" / "post_install.sh"


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
        "EXELY_PILOT_PMS_ROOM_TYPE": "Synthetic Standard",
        "EXELY_PILOT_RUN_ATTEMPT": "1",
        "EXELY_PILOT_RUN_ID": "123456",
        "EXELY_PILOT_STOP_SELL": "false",
        "EXELY_PILOT_TEST_DATE": future_date,
        "EXELY_PILOT_USERNAME": "synthetic-user",
        "EXELY_PILOT_WRITE_APPROVED": "true" if write else "false",
        "EXELY_PILOT_ACK_DURABLE_PMS_ATTESTED": "true",
    }
    if operation in {"reservation_import", "reservation_ack"}:
        values.update(
            {
                "MONGO_URL": "mongodb+srv://user:password@pilot-test.invalid/",
                "DB_NAME": "syroce_exely_pilot_test",
                "EXELY_PILOT_DB_SCOPE": "test",
                "EXELY_PILOT_PERSISTENT_DB_ATTESTED": "true",
            }
        )
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_workflow_is_manual_single_mode_and_exact_head_gated():
    workflow = _workflow()
    dispatch = workflow["on"]["workflow_dispatch"]
    inputs = dispatch["inputs"]

    assert inputs["operation"]["options"] == [
        "discovery",
        "reservation_read",
        "reservation_import",
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
    assert 'if [ "${GITHUB_RUN_ATTEMPT}" != "1" ]' in gate["run"]
    assert "BLOCKED_MUTATION_RERUN" in gate["run"]


def test_workflow_uses_protected_environment_and_exact_targets():
    workflow = _workflow()
    job = workflow["jobs"]["exely-pilot"]
    run_steps = [step for step in job["steps"] if step.get("name", "").startswith("Run one gated Exely")]
    scripts = "\n".join(step["run"] for step in run_steps)

    assert job["environment"] == "exely-pilot"
    assert job["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert len(run_steps) == 3
    assert "test_exely_pilot_readonly" in scripts
    assert "test_exely_pilot_reservation_import" in scripts
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


def test_litellm_security_override_declares_and_verifies_settings_dependency():
    requirements = INTEGRATIONS_REQUIREMENTS.read_text().splitlines()
    post_install = POST_INSTALL.read_text()

    assert "pydantic-settings==2.14.2" in requirements
    assert "import litellm, openai, pydantic_settings" in post_install


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
    persistent_secrets = {"MONGO_URL"}
    ari_step = next(step for step in job["steps"] if step.get("name") == "Run one gated Exely discovery or ARI target")
    import_step = next(step for step in job["steps"] if step.get("name") == "Run one gated Exely durable reservation import target")
    ack_step = next(step for step in job["steps"] if step.get("name") == "Run one gated Exely acknowledgement target")

    assert ari_step["if"] == "inputs.operation != 'reservation_ack' && inputs.operation != 'reservation_import'"
    assert import_step["if"] == "inputs.operation == 'reservation_import'"
    assert ack_step["if"] == "inputs.operation == 'reservation_ack'"
    assert common_secrets | ari_secrets <= set(ari_step["env"])
    assert persistent_secrets.isdisjoint(ari_step["env"])
    assert common_secrets | ari_secrets | persistent_secrets <= set(import_step["env"])
    assert common_secrets | ari_secrets | persistent_secrets <= set(ack_step["env"])
    assert import_step["env"]["MONGO_URL"] == "${{ secrets.EXELY_PILOT_PERSISTENT_MONGO_URL }}"
    assert import_step["env"]["DB_NAME"] == "${{ vars.EXELY_PILOT_PERSISTENT_DB_NAME }}"
    assert "test_exely_pilot_reservation_import" in import_step["run"]
    assert "test_exely_pilot_single_write" not in import_step["run"]
    for step in job["steps"]:
        if step.get("name") not in {ari_step["name"], import_step["name"], ack_step["name"]}:
            assert (common_secrets | ari_secrets | persistent_secrets).isdisjoint(step.get("env", {}))


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


@pytest.mark.parametrize(
    "operation",
    ["availability", "rate", "stop_sell", "min_los", "min_los_arrival", "reservation_ack"],
)
def test_mutations_fail_closed_on_workflow_rerun(monkeypatch, operation):
    _base_env(monkeypatch, operation=operation, write=True)
    monkeypatch.setenv("EXELY_PILOT_RUN_ATTEMPT", "2")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_MUTATION_RERUN"):
        pilot._load_settings()


@pytest.mark.parametrize("operation", ["discovery", "reservation_read", "reservation_import"])
def test_readonly_operations_allow_workflow_rerun(monkeypatch, operation):
    _base_env(monkeypatch, operation=operation)
    monkeypatch.setenv("EXELY_PILOT_RUN_ATTEMPT", "2")

    assert pilot._load_settings().operation == operation


def test_discovery_allows_mapping_secrets_to_be_absent(monkeypatch):
    _base_env(monkeypatch, operation="discovery")
    monkeypatch.delenv("EXELY_PILOT_ROOM_TYPE_CODE")
    monkeypatch.delenv("EXELY_PILOT_RATE_PLAN_CODE")

    settings = pilot._load_settings()

    assert settings.room_type_code == ""
    assert settings.rate_plan_code == ""


def test_ari_write_still_requires_mapping_secrets(monkeypatch):
    _base_env(monkeypatch, operation="availability", write=True)
    monkeypatch.delenv("EXELY_PILOT_ROOM_TYPE_CODE")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_MISSING_CONFIGURATION:EXELY_PILOT_ROOM_TYPE_CODE"):
        pilot._load_settings()


@pytest.mark.asyncio
async def test_discovery_without_target_mapping_reports_safe_capability_metadata(monkeypatch):
    _base_env(monkeypatch, operation="discovery")
    monkeypatch.delenv("EXELY_PILOT_ROOM_TYPE_CODE")
    monkeypatch.delenv("EXELY_PILOT_RATE_PLAN_CODE")
    settings = pilot._load_settings()
    provider = SimpleNamespace(
        discover_rooms=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                data={
                    "room_types": [{"code": "synthetic-room-a"}, {"code": "synthetic-room-b"}],
                    "rate_plans": [{"code": "synthetic-rate"}],
                },
                metadata={"provider_status_class": "SUCCESS"},
            )
        )
    )
    recorded: list[tuple[str, object]] = []

    metadata = await pilot._discover_mapping(provider, settings, lambda key, value: recorded.append((key, value)))

    assert metadata["capability_match"] is True
    assert metadata["room_match"] is True
    assert metadata["rate_plan_match"] is True
    assert metadata["match_count_class"] == "MULTIPLE"
    assert "synthetic-room" not in str(metadata)
    assert "synthetic-rate" not in str(metadata)
    assert recorded == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reservations", "failure_code"),
    [
        ([], "BLOCKED_NO_UNDELIVERED_RESERVATION"),
        ([{"last_modify": "version"}, {"last_modify": "version"}], "BLOCKED_MULTIPLE_UNDELIVERED_RESERVATIONS"),
    ],
)
async def test_exactly_one_reservation_gate_fails_closed(monkeypatch, reservations, failure_code):
    _base_env(monkeypatch, operation="reservation_import")
    settings = pilot._load_settings()
    provider = SimpleNamespace(
        pull_reservations=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                data={"reservations": reservations},
                metadata={"provider_status_class": "SUCCESS"},
            )
        )
    )

    with pytest.raises(pytest.fail.Exception, match=failure_code):
        await pilot._read_reservations(
            provider,
            settings,
            lambda *_: None,
            require_exactly_one=True,
        )


@pytest.mark.asyncio
async def test_provider_5xx_is_never_a_success(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import")
    settings = pilot._load_settings()
    provider = SimpleNamespace(
        pull_reservations=AsyncMock(
            return_value=SimpleNamespace(
                success=False,
                data=None,
                error_type="HTTP_5XX",
                metadata={},
            )
        )
    )

    with pytest.raises(pytest.fail.Exception, match="BLOCKED_RESERVATION_READ_FAILED"):
        await pilot._read_reservations(
            provider,
            settings,
            lambda *_: None,
            require_exactly_one=True,
        )


@pytest.mark.asyncio
async def test_malformed_provider_response_is_never_a_success(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import")
    settings = pilot._load_settings()
    provider = SimpleNamespace(
        pull_reservations=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                data={"reservations": "malformed"},
                metadata={"provider_status_class": "SUCCESS"},
            )
        )
    )

    with pytest.raises(pytest.fail.Exception, match="BLOCKED_RESERVATION_READ_RESPONSE_INVALID"):
        await pilot._read_reservations(
            provider,
            settings,
            lambda *_: None,
            require_exactly_one=True,
        )


def test_ack_requires_separate_durable_pms_attestation(monkeypatch):
    _base_env(monkeypatch, operation="reservation_ack", write=True)
    monkeypatch.setenv("EXELY_PILOT_ACK_DURABLE_PMS_ATTESTED", "false")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_DURABLE_PMS_RESULT_NOT_ATTESTED"):
        pilot._load_settings()


def test_persistent_import_rejects_ephemeral_database(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import")
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017/hotel_pms_test")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_EPHEMERAL_PMS_DATABASE"):
        pilot._load_settings()


def test_persistent_import_rejects_non_test_database_scope(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import")
    monkeypatch.setenv("EXELY_PILOT_DB_SCOPE", "production")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_NON_TEST_PMS_DB"):
        pilot._load_settings()


def test_persistent_import_rejects_production_hostname_marker(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import")
    monkeypatch.setenv("MONGO_URL", "mongodb+srv://user:password@prod.mongodb.invalid/")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_NON_TEST_PMS_DB"):
        pilot._load_settings()


def test_persistent_import_rejects_missing_database_attestation(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import")
    monkeypatch.setenv("EXELY_PILOT_PERSISTENT_DB_ATTESTED", "false")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_PERSISTENT_TEST_DB_NOT_ATTESTED"):
        pilot._load_settings()


def test_reservation_import_conflicts_with_provider_write_approval(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import", write=True)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_READONLY_WRITE_CONFLICT"):
        pilot._load_settings()


def test_settings_repr_never_contains_credentials_or_provider_identifiers(monkeypatch):
    _base_env(monkeypatch, operation="reservation_ack", write=True)
    settings_repr = repr(pilot._load_settings())

    for sensitive in (
        "synthetic-user",
        "synthetic-password",
        "synthetic-property",
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
async def test_reservation_import_transport_allows_only_one_read_and_no_provider_write():
    original = AsyncMock(return_value=b"synthetic-response")
    provider = SimpleNamespace(_transport=SimpleNamespace(send_soap=original))
    guard = pilot.PilotTransportGuard(provider, SimpleNamespace(operation="reservation_import"))

    await provider._transport.send_soap("synthetic", get_soap_action_uri("OTA_ReadRQ"))
    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_UNEXPECTED_SOAP_ACTION"):
        await provider._transport.send_soap("synthetic", get_soap_action_uri("OTA_NotifReportRQ"))

    assert guard.read_count == 1
    assert guard.write_count == 0
    assert original.await_count == 1


@pytest.mark.asyncio
async def test_reservation_import_timeout_is_not_retried():
    original = AsyncMock(side_effect=TimeoutError)
    provider = SimpleNamespace(_transport=SimpleNamespace(send_soap=original))
    guard = pilot.PilotTransportGuard(provider, SimpleNamespace(operation="reservation_import"))

    with pytest.raises(TimeoutError):
        await provider._transport.send_soap("synthetic", get_soap_action_uri("OTA_ReadRQ"))

    assert guard.read_count == 1
    assert guard.write_count == 0
    assert original.await_count == 1


@pytest.mark.asyncio
async def test_reservation_import_db_preflight_blocks_before_provider_read(monkeypatch):
    _base_env(monkeypatch, operation="reservation_import")
    provider = SimpleNamespace(
        _transport=SimpleNamespace(send_soap=AsyncMock()),
        pull_reservations=AsyncMock(),
    )
    monkeypatch.setattr(pilot, "_build_provider", lambda settings: provider)
    monkeypatch.setattr(
        pilot,
        "prepare_pilot_persistence",
        AsyncMock(side_effect=pilot.PilotImportError("BLOCKED_PERSISTENT_TEST_DB_PREFLIGHT_FAILED")),
    )
    recorded: list[tuple[str, object]] = []

    with pytest.raises(
        pytest.fail.Exception,
        match="BLOCKED_PERSISTENT_TEST_DB_PREFLIGHT_FAILED",
    ):
        await pilot.test_exely_pilot_reservation_import(lambda key, value: recorded.append((key, value)))

    provider.pull_reservations.assert_not_awaited()
    assert ("provider_read_count", 0) in recorded
    assert ("provider_write_count", 0) in recorded


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
