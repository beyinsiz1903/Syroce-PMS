"""Offline safety contract for the manual HotelRunner ARI pilot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
import yaml

from domains.channel_manager.providers.hotelrunner import endpoints as ep
from tests.integration import test_hotelrunner_ari_pilot as pilot

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "hotelrunner-ari-pilot.yml"


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
        "HOTELRUNNER_PILOT_ACCOUNT_CONFIRMED": "true",
        "HOTELRUNNER_PILOT_APPROVED_HEAD": "a" * 40,
        "HOTELRUNNER_PILOT_AVAILABILITY": "2",
        "HOTELRUNNER_PILOT_BASE_URL": "https://app.hotelrunner.com",
        "HOTELRUNNER_PILOT_CHANNEL_CODE": "synthetic-channel",
        "HOTELRUNNER_PILOT_HMAC_KEY": "synthetic-hmac-key-with-at-least-32-chars",
        "HOTELRUNNER_PILOT_HR_ID": "synthetic-hotel",
        "HOTELRUNNER_PILOT_INV_CODE": "synthetic-room",
        "HOTELRUNNER_PILOT_MIN_STAY": "2",
        "HOTELRUNNER_PILOT_OPERATION": operation,
        "HOTELRUNNER_PILOT_RATE": "100.00",
        "HOTELRUNNER_PILOT_RUN_ID": "123456",
        "HOTELRUNNER_PILOT_STOP_SELL": "0",
        "HOTELRUNNER_PILOT_TEST_DATE": future_date,
        "HOTELRUNNER_PILOT_TOKEN": "synthetic-token",
        "HOTELRUNNER_PILOT_WRITE_APPROVED": "true" if write else "false",
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
        "restriction",
    ]
    assert inputs["confirm_provider_write"]["default"] == "false"
    assert inputs["approved_head_sha"]["required"] == "true"
    assert list(workflow["on"]) == ["workflow_dispatch"]

    job = workflow["jobs"]["hotelrunner-ari-pilot"]
    gate = next(step for step in job["steps"] if step.get("name") == "Validate exact-head approval and operation gate")
    assert "BLOCKED_READONLY_WRITE_CONFLICT" in gate["run"]
    assert "BLOCKED_PROVIDER_WRITE_NOT_APPROVED" in gate["run"]


def test_workflow_uses_protected_pilot_environment_and_exact_targets():
    workflow = _workflow()
    job = workflow["jobs"]["hotelrunner-ari-pilot"]
    run_step = next(step for step in job["steps"] if step.get("name") == "Run one gated HotelRunner pilot target")
    script = run_step["run"]

    assert job["environment"] == "hotelrunner-pilot"
    assert job["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert "test_hotelrunner_pilot_readonly_discovery" in script
    assert "test_hotelrunner_pilot_readonly_reservation" in script
    assert "test_hotelrunner_pilot_single_ari_write" in script
    assert "pytest -m" not in script


def test_workflow_requires_both_normal_exact_head_workflows():
    workflow = _workflow()
    job = workflow["jobs"]["hotelrunner-ari-pilot"]
    gate = next(step for step in job["steps"] if step.get("name") == "Require successful exact-head normal workflows")
    script = gate["run"]

    assert "ci-cd.yml" in script
    assert "frontend-quality.yml" in script
    assert "databaseId,headSha,event" in script
    assert '.event == \\"push\\"' in script
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
    assert "deploy-production" not in script
    assert ".headSha" in script
    assert "${GITHUB_SHA}" in script
    assert '.conclusion == \\"success\\"' in script
    assert "BLOCKED_EXACT_HEAD_REQUIRED_JOB_NOT_GREEN" in script


def test_workflow_passes_secrets_only_to_the_selected_test_step():
    workflow = _workflow()
    job = workflow["jobs"]["hotelrunner-ari-pilot"]
    secret_names = {
        "HOTELRUNNER_PILOT_TOKEN",
        "HOTELRUNNER_PILOT_HR_ID",
        "HOTELRUNNER_PILOT_INV_CODE",
        "HOTELRUNNER_PILOT_CHANNEL_CODE",
        "HOTELRUNNER_PILOT_HMAC_KEY",
    }
    for step in job["steps"]:
        env = step.get("env", {})
        if step.get("name") == "Run one gated HotelRunner pilot target":
            assert secret_names <= set(env)
        else:
            assert secret_names.isdisjoint(env)


def test_workflow_pins_the_official_documented_host():
    workflow = _workflow()
    job = workflow["jobs"]["hotelrunner-ari-pilot"]
    run_step = next(step for step in job["steps"] if step.get("name") == "Run one gated HotelRunner pilot target")

    assert run_step["env"]["HOTELRUNNER_PILOT_BASE_URL"] == "https://app.hotelrunner.com"


def test_settings_fail_closed_for_unapproved_host(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("HOTELRUNNER_PILOT_BASE_URL", "https://example.invalid")

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_UNAPPROVED_PROVIDER_HOST"):
        pilot._load_settings()


def test_settings_fail_closed_for_exact_head_mismatch(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_EXACT_HEAD_MISMATCH"):
        pilot._load_settings()


def test_settings_fail_closed_without_write_approval(monkeypatch):
    _base_env(monkeypatch, operation="availability", write=False)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_PROVIDER_WRITE_NOT_APPROVED"):
        pilot._load_settings()


def test_reservation_read_is_readonly(monkeypatch):
    _base_env(monkeypatch, operation="reservation_read", write=False)

    settings = pilot._load_settings()

    assert settings.operation == "reservation_read"


def test_reservation_read_rejects_write_approval(monkeypatch):
    _base_env(monkeypatch, operation="reservation_read", write=True)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_READONLY_WRITE_CONFLICT"):
        pilot._load_settings()


def test_settings_repr_never_contains_credentials_or_provider_identifiers(monkeypatch):
    _base_env(monkeypatch)
    settings_repr = repr(pilot._load_settings())

    for sensitive in (
        "synthetic-token",
        "synthetic-hotel",
        "synthetic-room",
        "synthetic-channel",
        "synthetic-hmac-key-with-at-least-32-chars",
    ):
        assert sensitive not in settings_repr


def test_safe_metadata_drops_payload_and_identifier_fields(caplog):
    recorded: list[tuple[str, object]] = []
    sensitive = "synthetic-sensitive-value"

    with caplog.at_level("INFO", logger="hotelrunner.ari_pilot"):
        pilot._record_safe_metadata(
            lambda key, value: recorded.append((key, value)),
            {
                "correlation_label": "abcdef123456",
                "provider_write_count": 0,
                "token": sensitive,
                "hr_id": sensitive,
                "inv_code": sensitive,
                "channel_code": sensitive,
                "payload": {"value": sensitive},
            },
        )

    assert recorded == [
        ("correlation_label", "abcdef123456"),
        ("provider_write_count", 0),
    ]
    assert sensitive not in caplog.text


def test_mutation_contains_exactly_one_operation_field(monkeypatch):
    mutation_fields = {"availability", "price", "stop_sale", "min_stay"}
    expected = {
        "availability": "availability",
        "rate": "price",
        "stop_sell": "stop_sale",
        "restriction": "min_stay",
    }

    for operation, field_name in expected.items():
        _base_env(monkeypatch, operation=operation, write=True)
        settings = pilot._load_settings()
        mutation = pilot._build_single_mutation(settings)
        assert set(mutation) & mutation_fields == {field_name}
        assert mutation["inv_code"] == "synthetic-room"
        assert mutation["channel_codes"] == ["synthetic-channel"]


@pytest.mark.asyncio
async def test_http_guard_allows_get_and_at_most_one_expected_put():
    original = AsyncMock(return_value=SimpleNamespace(status_code=200))
    provider = SimpleNamespace(_client=SimpleNamespace(_request=original))
    guard = pilot.PilotHttpGuard(provider, allow_write=True)

    await provider._client._request("GET", ep.ROOMS)
    await provider._client._request("PUT", ep.ROOMS_DATERANGE)
    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_SECOND_PROVIDER_WRITE_ATTEMPT"):
        await provider._client._request("PUT", ep.ROOMS_DATERANGE)

    assert guard.get_count == 1
    assert guard.write_count == 1
    assert original.await_count == 2


@pytest.mark.asyncio
async def test_http_guard_rejects_post_before_provider_call():
    original = AsyncMock(return_value=SimpleNamespace(status_code=200))
    provider = SimpleNamespace(_client=SimpleNamespace(_request=original))
    pilot.PilotHttpGuard(provider, allow_write=True)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_UNEXPECTED_PROVIDER_HTTP_METHOD"):
        await provider._client._request("POST", ep.ROOMS_DATERANGE)

    original.assert_not_awaited()


@pytest.mark.asyncio
async def test_readonly_guard_rejects_put_before_provider_call():
    original = AsyncMock(return_value=SimpleNamespace(status_code=200))
    provider = SimpleNamespace(_client=SimpleNamespace(_request=original))
    pilot.PilotHttpGuard(provider, allow_write=False)

    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_PROVIDER_WRITE_IN_READONLY_MODE"):
        await provider._client._request("PUT", ep.ROOMS_DATERANGE)

    original.assert_not_awaited()


@pytest.mark.asyncio
async def test_readonly_guard_allows_reservation_get_but_rejects_ack():
    original = AsyncMock(return_value=SimpleNamespace(status_code=200))
    provider = SimpleNamespace(_client=SimpleNamespace(_request=original))
    guard = pilot.PilotHttpGuard(provider, allow_write=False)

    await provider._client._request("GET", ep.RESERVATIONS)
    with pytest.raises(pilot.PilotSafetyError, match="BLOCKED_PROVIDER_WRITE_IN_READONLY_MODE"):
        await provider._client._request("PUT", ep.RESERVATIONS_ACK)

    assert guard.get_count == 1
    assert guard.write_count == 0
    original.assert_awaited_once_with("GET", ep.RESERVATIONS)


@pytest.mark.asyncio
async def test_reservation_read_target_uses_two_gets_and_no_ack(
    monkeypatch,
    caplog,
):
    _base_env(monkeypatch, operation="reservation_read", write=False)
    provider_call = AsyncMock(return_value=SimpleNamespace(status_code=200))
    client = SimpleNamespace(_request=provider_call, close=AsyncMock())
    synthetic_identifier = "synthetic-reservation-identifier"

    class FakeProvider:
        def __init__(self):
            self._client = client

        async def test_connection(self):
            await self._client._request("GET", ep.TRANSACTION_DETAILS)
            return SimpleNamespace(success=True)

        async def fetch_reservations(self, **_kwargs):
            await self._client._request("GET", ep.RESERVATIONS)
            return SimpleNamespace(
                success=True,
                data={
                    "raw_reservations": [
                        {
                            "hr_number": synthetic_identifier,
                            "message_uid": "synthetic-message-uid",
                            "rooms": [{"room_code": "synthetic-room"}],
                        }
                    ]
                },
            )

    monkeypatch.setattr(pilot, "_build_provider", lambda _settings: FakeProvider())
    recorded: list[tuple[str, object]] = []

    with caplog.at_level("INFO", logger="hotelrunner.ari_pilot"):
        await pilot.test_hotelrunner_pilot_readonly_reservation(lambda key, value: recorded.append((key, value)))

    assert ("match_count_class", "ONE") in recorded
    assert ("provider_write_count", 0) in recorded
    assert ("get_count", 2) in recorded
    assert ("result", "PASS") in recorded
    assert provider_call.await_args_list == [
        call("GET", ep.TRANSACTION_DETAILS),
        call("GET", ep.RESERVATIONS),
    ]
    assert synthetic_identifier not in caplog.text
