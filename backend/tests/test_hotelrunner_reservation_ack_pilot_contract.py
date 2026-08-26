"""Offline safety contract for the single HotelRunner reservation ACK pilot."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from domains.channel_manager.providers.hotelrunner import endpoints as ep
from tests.integration import test_hotelrunner_reservation_ack_pilot as ack_pilot

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "hotelrunner-reservation-ack-pilot.yml"


def _workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def _base_env(monkeypatch, *, write: bool = True):
    values = {
        "APP_ENV": "test",
        "TESTING": "1",
        "MONGO_URL": "mongodb://localhost:27017/hotel_pms_test",
        "DB_NAME": "hotel_pms_test",
        "GITHUB_SHA": "a" * 40,
        "HOTELRUNNER_PILOT_ACCOUNT_CONFIRMED": "true",
        "HOTELRUNNER_PILOT_APPROVED_HEAD": "a" * 40,
        "HOTELRUNNER_PILOT_BASE_URL": "https://app.hotelrunner.com",
        "HOTELRUNNER_PILOT_HMAC_KEY": "synthetic-hmac-key-with-at-least-32-chars",
        "HOTELRUNNER_PILOT_HR_ID": "synthetic-hotel",
        "HOTELRUNNER_PILOT_OPERATION": "reservation_ack",
        "HOTELRUNNER_PILOT_RUN_ID": "123456",
        "HOTELRUNNER_PILOT_RUN_ATTEMPT": "1",
        "HOTELRUNNER_PILOT_SOURCE_RUN_ID": "123455",
        "HOTELRUNNER_PILOT_TARGET_GUEST_NAME": "Synthetic Target Guest",
        "HOTELRUNNER_PILOT_TARGET_WAIT_SECONDS": "90",
        "HOTELRUNNER_PILOT_TOKEN": "synthetic-token",
        "HOTELRUNNER_PILOT_WRITE_APPROVED": "true" if write else "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_workflow_is_manual_exact_head_and_single_write_gated():
    workflow = _workflow()
    assert list(workflow["on"]) == ["workflow_dispatch"]
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["confirm_provider_write"]["default"] == "false"
    assert inputs["approved_head_sha"]["required"] == "true"
    assert inputs["source_run_id"]["required"] == "true"

    job = workflow["jobs"]["hotelrunner-reservation-ack-pilot"]
    assert job["environment"] == "hotelrunner-pilot"
    assert job["concurrency"]["cancel-in-progress"] == "false"
    gate = next(step for step in job["steps"] if step.get("name") == "Validate exact-head approval and single ACK write gate")
    assert "BLOCKED_EXACT_HEAD_MISMATCH" in gate["run"]
    assert "BLOCKED_PROVIDER_WRITE_NOT_APPROVED" in gate["run"]
    assert "BLOCKED_MUTATION_RERUN" in gate["run"]
    assert "BLOCKED_INVALID_SOURCE_RUN_ID" in gate["run"]


def test_workflow_targets_exact_ack_test_and_no_deploy():
    workflow = _workflow()
    job = workflow["jobs"]["hotelrunner-reservation-ack-pilot"]
    run_step = next(step for step in job["steps"] if step.get("name") == "Run exactly one gated HotelRunner reservation ACK")
    assert run_step["env"]["HOTELRUNNER_PILOT_OPERATION"] == "reservation_ack"
    assert run_step["env"]["HOTELRUNNER_PILOT_RUN_ATTEMPT"] == "${{ github.run_attempt }}"
    assert run_step["env"]["HOTELRUNNER_PILOT_TARGET_GUEST_NAME"] == "${{ secrets.HOTELRUNNER_PILOT_TARGET_GUEST_NAME }}"
    assert run_step["env"]["HOTELRUNNER_PILOT_TARGET_WAIT_SECONDS"] == "90"
    assert "test_hotelrunner_single_reservation_ack" in run_step["run"]
    assert "deploy" not in run_step["run"].lower()
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}


def test_workflow_requires_exact_head_normal_ci_without_deploy_job():
    workflow = _workflow()
    job = workflow["jobs"]["hotelrunner-reservation-ack-pilot"]
    gate = next(step for step in job["steps"] if step.get("name") == "Require successful exact-head normal workflows")
    script = gate["run"]
    for required in (
        "lockfile-guard",
        "backend-lint",
        "frontend-lint",
        "backend-test",
        "battle-e2e",
        "load-test",
        "frontend-build",
        "security-scan",
    ):
        assert f'"{required}"' in script
    assert "frontend-quality.yml" in script
    assert '.event == \\"push\\" or .event == \\"pull_request\\"' in script
    assert "deploy-production" not in script


def test_settings_require_explicit_write_approval(monkeypatch):
    _base_env(monkeypatch, write=False)
    with pytest.raises(ack_pilot.ReservationPilotError, match="BLOCKED_PROVIDER_WRITE_NOT_APPROVED"):
        ack_pilot._load_ack_settings()


def test_settings_require_exact_head(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    with pytest.raises(ack_pilot.ReservationPilotError, match="BLOCKED_EXACT_HEAD_MISMATCH"):
        ack_pilot._load_ack_settings()


def test_settings_block_workflow_rerun(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("HOTELRUNNER_PILOT_RUN_ATTEMPT", "2")
    with pytest.raises(ack_pilot.ReservationPilotError, match="BLOCKED_MUTATION_RERUN"):
        ack_pilot._load_ack_settings()


def test_settings_repr_hides_credentials(monkeypatch):
    _base_env(monkeypatch)
    settings = ack_pilot._load_ack_settings()
    text = repr(settings)
    assert "synthetic-token" not in text
    assert "synthetic-hotel" not in text
    assert "Synthetic Target Guest" not in text


def test_ack_target_selection_uses_hmac_identity(monkeypatch):
    _base_env(monkeypatch)
    settings = ack_pilot._load_ack_settings()
    selected = ack_pilot._select_target_reservation(
        settings,
        [
            {"guest": "Different Guest", "message_uid": "other"},
            {"guest": "  SYNTHETIC   target guest ", "message_uid": "target"},
        ],
    )
    assert selected["message_uid"] == "target"


def test_ack_target_selection_fails_closed_on_multiple_matches(monkeypatch):
    _base_env(monkeypatch)
    settings = ack_pilot._load_ack_settings()
    with pytest.raises(
        ack_pilot.ReservationPilotError,
        match="CONFLICT_MULTIPLE_TARGET_UNDELIVERED_RESERVATIONS",
    ):
        ack_pilot._select_target_reservation(
            settings,
            [
                {"guest": "Synthetic Target Guest"},
                {"guest": "synthetic target guest"},
            ],
        )


@pytest.mark.asyncio
async def test_ack_target_wait_is_get_only_until_exact_target(monkeypatch):
    _base_env(monkeypatch)
    settings = ack_pilot._load_ack_settings()
    provider = SimpleNamespace(
        fetch_reservations=AsyncMock(
            side_effect=[
                SimpleNamespace(success=True, data={"raw_reservations": []}),
                SimpleNamespace(
                    success=True,
                    data={"raw_reservations": [{"guest": "Synthetic Target Guest", "message_uid": "target"}]},
                ),
            ]
        )
    )
    monkeypatch.setattr(ack_pilot, "_sleep", AsyncMock())

    selected = await ack_pilot._wait_for_target_reservation(
        provider,
        settings,
        wait_seconds=30,
    )

    assert selected["message_uid"] == "target"
    assert provider.fetch_reservations.await_count == 2
    ack_pilot._sleep.assert_awaited_once_with(10)


@pytest.mark.asyncio
async def test_ack_target_wait_fails_immediately_on_provider_read_error(monkeypatch):
    _base_env(monkeypatch)
    settings = ack_pilot._load_ack_settings()
    provider = SimpleNamespace(fetch_reservations=AsyncMock(return_value=SimpleNamespace(success=False, data=None)))

    with pytest.raises(
        ack_pilot.ReservationPilotError,
        match="BLOCKED_RESERVATION_READ_FAILED",
    ):
        await ack_pilot._wait_for_target_reservation(
            provider,
            settings,
            wait_seconds=30,
        )
    assert provider.fetch_reservations.await_count == 1


def test_post_ack_history_requires_exact_pms_number_match():
    ack_pilot._verify_history_pms_number(
        [{"message_uid": "target-message", "pms_number": "pms-booking"}],
        "target-message",
        "pms-booking",
    )

    with pytest.raises(
        ack_pilot.ReservationPilotError,
        match="BLOCKED_POST_ACK_PMS_NUMBER_MISMATCH",
    ):
        ack_pilot._verify_history_pms_number(
            [{"message_uid": "target-message", "pms_number": "different"}],
            "target-message",
            "pms-booking",
        )


def test_post_ack_history_rejects_duplicate_message_match():
    with pytest.raises(
        ack_pilot.ReservationPilotError,
        match="BLOCKED_POST_ACK_HISTORY_MATCH_INVALID",
    ):
        ack_pilot._verify_history_pms_number(
            [
                {"message_uid": "target-message", "pms_number": "pms-booking"},
                {"message_uid": "target-message", "pms_number": "pms-booking"},
            ],
            "target-message",
            "pms-booking",
        )


@pytest.mark.asyncio
async def test_ack_guard_allows_reads_and_exactly_one_ack_put():
    original = AsyncMock(return_value=SimpleNamespace(status_code=200))
    provider = SimpleNamespace(_client=SimpleNamespace(_request=original))
    guard = ack_pilot.AckPilotHttpGuard(provider)

    await provider._client._request("GET", ep.CHANNELS)
    await provider._client._request("GET", ep.RESERVATIONS)
    await provider._client._request("PUT", ep.RESERVATIONS_ACK)
    with pytest.raises(ack_pilot.ReservationPilotError, match="BLOCKED_SECOND_PROVIDER_WRITE_ATTEMPT"):
        await provider._client._request("PUT", ep.RESERVATIONS_ACK)

    assert guard.get_count == 2
    assert guard.write_count == 1
    assert original.await_count == 3


@pytest.mark.asyncio
async def test_ack_guard_rejects_other_provider_writes_before_call():
    original = AsyncMock(return_value=SimpleNamespace(status_code=200))
    provider = SimpleNamespace(_client=SimpleNamespace(_request=original))
    ack_pilot.AckPilotHttpGuard(provider)

    with pytest.raises(ack_pilot.ReservationPilotError, match="BLOCKED_UNEXPECTED_PROVIDER_WRITE_PATH"):
        await provider._client._request("PUT", ep.ROOMS_DATERANGE)
    original.assert_not_awaited()
