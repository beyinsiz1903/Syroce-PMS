import logging
from datetime import UTC, datetime

from models.schemas.nilvera_worker_health import (
    NilveraWorkerErrorCode,
    NilveraWorkerHealth,
    NilveraWorkerStatus,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NilveraWorkerHealthMixin:
    """Mixin to provide standardized health tracking for Nilvera workers."""

    def __init__(self, worker_name: str):
        self._health_state = NilveraWorkerHealth(
            worker_name=worker_name,
            enabled=True,  # Default to True until configured otherwise
            status=NilveraWorkerStatus.STOPPED,
        )

    def configure(self, *, enabled: bool) -> None:
        """Explicitly configure the worker's enabled state."""
        self._health_state.enabled = enabled
        if not enabled:
            self._mark_disabled()

    @property
    def health(self) -> NilveraWorkerHealth:
        """Returns the current sanitized worker health state."""
        return self._health_state

    @property
    def metrics(self) -> dict:
        """Alias for health property for backwards compatibility."""
        return self._health_state.model_dump(mode="json")

    def _mark_starting(self) -> None:
        self._health_state.status = NilveraWorkerStatus.STARTING
        self._health_state.started_at = _utc_now()
        self._health_state.task_alive = True
        self._health_state.degraded_reason = None

    def _mark_running(self) -> None:
        self._health_state.status = NilveraWorkerStatus.RUNNING

    def _mark_stopping(self) -> None:
        self._health_state.status = NilveraWorkerStatus.STOPPING

    def _mark_stopped(self) -> None:
        if self._health_state.status != NilveraWorkerStatus.FAILED:
            self._health_state.status = NilveraWorkerStatus.STOPPED
        self._health_state.task_alive = False

    def _mark_disabled(self) -> None:
        self._health_state.status = NilveraWorkerStatus.DISABLED
        self._health_state.enabled = False
        self._health_state.task_alive = False

    def _mark_failed(self, reason: str = "") -> None:
        self._health_state.status = NilveraWorkerStatus.FAILED
        self._health_state.task_alive = False
        if reason:
            self._health_state.degraded_reason = reason

    def _record_heartbeat(self) -> None:
        """Record a heartbeat on every tick regardless of queue depth."""
        self._health_state.last_heartbeat_at = _utc_now()
        self._health_state.task_alive = True

    def _record_success(self, jobs_processed: int = 1) -> None:
        """Mark a successful cycle/job."""
        self._health_state.processed_total += jobs_processed
        self._health_state.last_success_at = _utc_now()

        if self._health_state.status == NilveraWorkerStatus.DEGRADED:
            self._health_state.status = NilveraWorkerStatus.RUNNING
            self._health_state.degraded_reason = None

    def _record_job_error(self, code: NilveraWorkerErrorCode) -> None:
        """Record a non-fatal business logic or transient dependency error. Transitions to DEGRADED."""
        if not isinstance(code, NilveraWorkerErrorCode):
            raise ValueError(f"Error code must be a NilveraWorkerErrorCode enum, got {type(code)}")

        self._health_state.last_error_at = _utc_now()
        self._health_state.last_error_code = code
        self._health_state.job_failed_total += 1

        if self._health_state.status == NilveraWorkerStatus.RUNNING:
            self._health_state.status = NilveraWorkerStatus.DEGRADED
            self._health_state.degraded_reason = str(code.value)

    def _record_loop_error(self, code: NilveraWorkerErrorCode) -> None:
        """Record a fatal loop crash."""
        if not isinstance(code, NilveraWorkerErrorCode):
            raise ValueError(f"Error code must be a NilveraWorkerErrorCode enum, got {type(code)}")

        self._health_state.last_error_at = _utc_now()
        self._health_state.last_error_code = code
        self._health_state.loop_error_total += 1
