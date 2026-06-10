"""Tests for Sentry workflow-restart port-bind noise filter.

Context: `.replit` previously tagged the local Replit workspace as
``SENTRY_ENVIRONMENT=pilot``, so transient ``OSError: [Errno 98] address
already in use`` raised during workflow restart (uvicorn SIGTERM → new
bind race on port 8000) paged the pilot on-call channel.

Fix layers:
  1. Env split — local Replit dev → ``replit-dev``; deploy → ``pilot``
     (handled by Replit env-vars, not asserted here).
  2. ``_sentry_before_send`` drops the specific restart-race pattern
     before it leaves the process. Other bind failures (different port,
     different errno) still flow through.
"""
import time

import pytest

from infra import cloud_observability as obs
from infra.cloud_observability import (
    _is_graphql_introspection_denied,
    _is_hotelrunner_pull_rate_limited,
    _is_nonprod_sustained_transient_db,
    _is_static_client_disconnect,
    _is_workflow_restart_port_bind,
    _sentry_before_send,
    get_sentry_filter_stats,
)

_INTROSPECTION_MSG = (
    "GraphQL introspection has been disabled, but the requested query "
    "contained the field '__schema'."
)

_SUSTAINED_MSG = (
    "[outbox-worker] loop tick sustained transient db error "
    "(key=__loop__ streak=5): ServerSelectionTimeoutError"
)


def _hint(exc: Exception) -> dict:
    return {"exc_info": (type(exc), exc, None)}


@pytest.fixture(autouse=True)
def _reset_boot_window(monkeypatch):
    """Anchor boot timestamp to 'now' so each test runs inside the
    drop window unless it explicitly advances the clock."""
    monkeypatch.setattr(obs, "_PROCESS_BOOT_TS", time.monotonic())


class TestPortBindDetection:
    def test_port_8000_errno_98_detected(self):
        exc = OSError(98, "[Errno 98] error while attempting to bind on "
                          "address ('0.0.0.0', 8000): address already in use")
        exc.errno = 98
        assert _is_workflow_restart_port_bind({}, _hint(exc)) is True

    def test_port_5000_deploy_detected(self):
        exc = OSError(98, "bind ('0.0.0.0', 5000): address already in use")
        exc.errno = 98
        assert _is_workflow_restart_port_bind({}, _hint(exc)) is True

    def test_non_managed_port_passes_through(self):
        """Port 9999 (mock_server) bind failures must reach Sentry."""
        exc = OSError(98, "bind ('0.0.0.0', 9999): address already in use")
        exc.errno = 98
        assert _is_workflow_restart_port_bind({}, _hint(exc)) is False

    def test_unrelated_exception_passes_through(self):
        exc = ValueError("totally unrelated mentions 8000")
        assert _is_workflow_restart_port_bind({}, _hint(exc)) is False

    def test_different_errno_passes_through(self):
        """EACCES (13) on port 8000 is a real privilege error, not noise."""
        exc = OSError(13, "Permission denied: ('0.0.0.0', 8000)")
        exc.errno = 13
        assert _is_workflow_restart_port_bind({}, _hint(exc)) is False

    def test_message_only_event_no_longer_drops(self):
        """We refuse to drop solely on event-message text — exc_info required."""
        event = {"exception": {"values": [
            {"value": "address already in use ('0.0.0.0', 8000)"}
        ]}}
        assert _is_workflow_restart_port_bind(event, {}) is False

    def test_empty_inputs_safe(self):
        assert _is_workflow_restart_port_bind({}, {}) is False
        assert _is_workflow_restart_port_bind({}, None) is False

    def test_after_boot_window_passes_through(self, monkeypatch):
        """Persistent bind conflicts past the boot window must reach Sentry."""
        monkeypatch.setattr(
            obs, "_PROCESS_BOOT_TS",
            time.monotonic() - (obs._RESTART_DROP_WINDOW_SECONDS + 1),
        )
        exc = OSError(98, "bind ('0.0.0.0', 8000): address already in use")
        exc.errno = 98
        assert _is_workflow_restart_port_bind({}, _hint(exc)) is False


class TestBeforeSendIntegration:
    def test_restart_noise_dropped_and_counted(self):
        before = get_sentry_filter_stats()["restart_bind_drops"]
        exc = OSError(98, "bind ('0.0.0.0', 8000): address already in use")
        exc.errno = 98
        assert _sentry_before_send({"message": "x"}, _hint(exc)) is None
        after = get_sentry_filter_stats()["restart_bind_drops"]
        assert after == before + 1

    def test_real_error_passes_through_with_scrub(self):
        """Real errors keep flowing; PII scrub still runs."""
        exc = RuntimeError("boom: token=eyJabcdefg.aaaaaaa.bbbbbbb")
        event = {"exception": {"values": [{"value": str(exc)}]}}
        out = _sentry_before_send(event, _hint(exc))
        assert out is not None
        rendered = out["exception"]["values"][0]["value"]
        assert "<JWT>" in rendered or "eyJ" not in rendered

    def test_persistent_bind_after_window_reaches_scrub_path(self, monkeypatch):
        monkeypatch.setattr(
            obs, "_PROCESS_BOOT_TS",
            time.monotonic() - (obs._RESTART_DROP_WINDOW_SECONDS + 1),
        )
        exc = OSError(98, "bind ('0.0.0.0', 8000): address already in use")
        exc.errno = 98
        out = _sentry_before_send(
            {"exception": {"values": [{"value": str(exc)}]}}, _hint(exc)
        )
        assert out is not None


class TestNonProdSustainedTransientDb:
    """The transient_db_guard escalates a SUSTAINED Atlas outage to ERROR.
    In non-prod that escalation is noise (the workflow console already shows
    the streak); in production/pilot it is a real incident and must page."""

    def test_dropped_in_replit_dev(self, monkeypatch):
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "replit-dev")
        assert _is_nonprod_sustained_transient_db(
            {"logentry": {"message": _SUSTAINED_MSG}}
        ) is True

    def test_dropped_when_env_unset_defaults_dev(self, monkeypatch):
        monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
        assert _is_nonprod_sustained_transient_db(
            {"message": _SUSTAINED_MSG}
        ) is True

    def test_kept_in_production(self, monkeypatch):
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
        assert _is_nonprod_sustained_transient_db(
            {"logentry": {"message": _SUSTAINED_MSG}}
        ) is False

    def test_kept_in_pilot(self, monkeypatch):
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "pilot")
        assert _is_nonprod_sustained_transient_db(
            {"logentry": {"message": _SUSTAINED_MSG}}
        ) is False

    def test_unrelated_error_in_dev_passes_through(self, monkeypatch):
        """Only the sustained-transient template is dropped; real errors flow."""
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "replit-dev")
        assert _is_nonprod_sustained_transient_db(
            {"logentry": {"message": "KeyError: tenant_id missing"}}
        ) is False

    def test_before_send_drops_and_counts_in_dev(self, monkeypatch):
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "replit-dev")
        before = get_sentry_filter_stats()["nonprod_transient_db_drops"]
        assert _sentry_before_send({"logentry": {"message": _SUSTAINED_MSG}}, {}) is None
        after = get_sentry_filter_stats()["nonprod_transient_db_drops"]
        assert after == before + 1

    def test_before_send_keeps_sustained_in_production(self, monkeypatch):
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
        out = _sentry_before_send({"logentry": {"message": _SUSTAINED_MSG}}, {})
        assert out is not None


class TestGraphQLIntrospectionDenied:
    """The introspection-disabled validation rejection is an EXPECTED client
    denial (the security control working), logged at ERROR by Strawberry. It is
    never an actionable server incident, so it must be dropped in every
    environment — while genuine GraphQL errors keep flowing."""

    def test_detected_from_logentry(self):
        assert _is_graphql_introspection_denied(
            {"logentry": {"message": _INTROSPECTION_MSG}}
        ) is True

    def test_detected_from_exception_value(self):
        assert _is_graphql_introspection_denied(
            {"exception": {"values": [{"value": _INTROSPECTION_MSG}]}}
        ) is True

    def test_detected_for_other_introspection_fields(self):
        for field in ("queryType", "mutationType", "types", "kind"):
            msg = (
                "GraphQL introspection has been disabled, but the requested "
                f"query contained the field '{field}'."
            )
            assert _is_graphql_introspection_denied(
                {"logentry": {"message": msg}}
            ) is True

    def test_unrelated_graphql_error_passes_through(self):
        assert _is_graphql_introspection_denied(
            {"logentry": {"message": "GraphQLError: tenant_id resolver failed"}}
        ) is False

    def test_near_miss_phrase_not_dropped(self):
        """A genuine error that merely mentions the phrase (without the full
        graphql-core template) must still page — we anchor on the template."""
        near = (
            "RuntimeError: our middleware reports introspection has been "
            "disabled for this tenant; aborting startup"
        )
        assert _is_graphql_introspection_denied(
            {"exception": {"values": [{"value": near}]}}
        ) is False

    def test_logger_prefixed_denial_still_dropped(self):
        """A logger prefix before the template must not defeat the match."""
        prefixed = "strawberry.execution ERROR " + _INTROSPECTION_MSG
        assert _is_graphql_introspection_denied(
            {"logentry": {"formatted": prefixed}}
        ) is True

    def test_empty_event_safe(self):
        assert _is_graphql_introspection_denied({}) is False

    def test_before_send_drops_in_any_env_and_counts(self, monkeypatch):
        # Even in production this is an expected denial, not an incident.
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
        before = get_sentry_filter_stats()["graphql_introspection_denied_drops"]
        assert _sentry_before_send(
            {"logentry": {"message": _INTROSPECTION_MSG}}, {}
        ) is None
        after = get_sentry_filter_stats()["graphql_introspection_denied_drops"]
        assert after == before + 1

    def test_before_send_keeps_real_graphql_error(self):
        out = _sentry_before_send(
            {"exception": {"values": [
                {"value": "GraphQLError: tenant_id resolver failed"}
            ]}}, {}
        )
        assert out is not None


class TestHotelRunnerPullRateLimit:
    """The sync engine logs an ERROR per failed PULL page. An EXTERNAL
    HotelRunner 429 (the provider throttling our poller, retries already
    exhausted) is expected backpressure, not a server fault — it must not page.
    A genuine non-429 PULL failure still pages."""

    _PULL_429 = (
        "[PULL] Failed for tenant 5bad4a34-6ee3-4566-9053-741b7375a9cf page 1: "
        "Rate limit exceeded (429) [99ab143f-f9d]"
    )

    def test_detected_from_logentry(self):
        assert _is_hotelrunner_pull_rate_limited(
            {"logentry": {"message": self._PULL_429}}
        ) is True

    def test_detected_from_exception_value(self):
        assert _is_hotelrunner_pull_rate_limited(
            {"exception": {"values": [{"value": self._PULL_429}]}}
        ) is True

    def test_logger_prefixed_still_detected(self):
        prefixed = (
            "domains.channel_manager.providers.sync_engine ERROR " + self._PULL_429
        )
        assert _is_hotelrunner_pull_rate_limited(
            {"logentry": {"formatted": prefixed}}
        ) is True

    def test_non_429_pull_failure_passes_through(self):
        """A real PULL failure (auth / parse / 5xx) must still page."""
        msg = (
            "[PULL] Failed for tenant 5bad4a34 page 1: "
            "Invalid credentials (401) [corr]"
        )
        assert _is_hotelrunner_pull_rate_limited(
            {"logentry": {"message": msg}}
        ) is False

    def test_429_outside_pull_context_passes_through(self):
        """A 429 that is NOT the PULL backpressure template must still page."""
        msg = "worker tick: Rate limit exceeded (429) [corr]"
        assert _is_hotelrunner_pull_rate_limited(
            {"logentry": {"message": msg}}
        ) is False

    def test_empty_event_safe(self):
        assert _is_hotelrunner_pull_rate_limited({}) is False

    def test_before_send_drops_and_counts(self):
        before = get_sentry_filter_stats()["hotelrunner_pull_rate_limit_drops"]
        assert _sentry_before_send(
            {"logentry": {"message": self._PULL_429}}, {}
        ) is None
        after = get_sentry_filter_stats()["hotelrunner_pull_rate_limit_drops"]
        assert after == before + 1


class TestStaticClientDisconnect:
    """uvicorn raises ``RuntimeError('Response content shorter than
    Content-Length')`` when a client disconnects mid-download of a static asset.
    Benign client backpressure — dropped ONLY for static-asset GET/HEAD. The
    same message on an API path (a possible truncation bug) still pages."""

    _MSG = "Response content shorter than Content-Length"

    def _static_event(
        self,
        url="https://x.syroce.replit.app/js/js/NotificationContext-CoJe4oGl.js",
        method="GET",
    ):
        return {
            "request": {"method": method, "url": url},
            "exception": {"values": [{"value": self._MSG}]},
        }

    def _hint(self):
        exc = RuntimeError(self._MSG)
        return {"exc_info": (RuntimeError, exc, None)}

    def test_detected_from_exc_info_and_static_path(self):
        assert _is_static_client_disconnect(self._static_event(), self._hint()) is True

    def test_detected_from_event_value_only(self):
        assert _is_static_client_disconnect(self._static_event(), {}) is True

    def test_static_css_asset_detected(self):
        ev = self._static_event(url="https://x.syroce.replit.app/assets/index-abc.css")
        assert _is_static_client_disconnect(ev, {}) is True

    def test_api_path_passes_through(self):
        """Same message on a real API endpoint is a possible truncation bug — page it."""
        ev = self._static_event(url="https://x.syroce.replit.app/api/reservations")
        assert _is_static_client_disconnect(ev, self._hint()) is False

    def test_api_path_with_static_segment_passes_through(self):
        """Prefix-anchored, not substring: an API path that merely CONTAINS a
        static-looking segment must still page (real truncation bug)."""
        ev = self._static_event(url="https://x.syroce.replit.app/api/v2/assets/export")
        assert _is_static_client_disconnect(ev, self._hint()) is False

    def test_post_method_passes_through(self):
        assert _is_static_client_disconnect(
            self._static_event(method="POST"), self._hint()
        ) is False

    def test_unrelated_message_on_static_path_passes_through(self):
        ev = {
            "request": {"method": "GET", "url": "https://x/js/app.js"},
            "exception": {"values": [{"value": "KeyError: boom"}]},
        }
        assert _is_static_client_disconnect(ev, {}) is False

    def test_missing_request_context_passes_through(self):
        """No request url → cannot prove static → must page."""
        ev = {"exception": {"values": [{"value": self._MSG}]}}
        assert _is_static_client_disconnect(ev, self._hint()) is False

    def test_before_send_drops_and_counts(self):
        before = get_sentry_filter_stats()["static_client_disconnect_drops"]
        assert _sentry_before_send(self._static_event(), self._hint()) is None
        after = get_sentry_filter_stats()["static_client_disconnect_drops"]
        assert after == before + 1
