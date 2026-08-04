import asyncio
import logging
from datetime import UTC, datetime

from core.integrations.nilvera.config import get_nilvera_config
from models.schemas.nilvera_worker_health import NilveraWorkerHealth, NilveraWorkerStatus

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NilveraBaseWorker:
    """Base class for Nilvera background workers standardizing health and lifecycle."""

    def __init__(self, worker_name: str, worker_id: str):
        self.worker_name = worker_name
        self.worker_id = worker_id

        cfg = get_nilvera_config()
        self._health = NilveraWorkerHealth(
            worker_name=self.worker_name,
            enabled=cfg.enabled,
            status=NilveraWorkerStatus.DISABLED if not cfg.enabled else NilveraWorkerStatus.STOPPED,
        )

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def metrics(self) -> dict:
        """Alias for health property to maintain backwards compatibility where needed."""
        return self.health.model_dump(mode="json")

    @property
    def health(self) -> NilveraWorkerHealth:
        """Returns the sanitized worker health state."""
        return self._health

    async def start(self) -> None:
        """Start the worker if enabled and not already running."""
        if not self._health.enabled:
            logger.info(f"{self.worker_name} ({self.worker_id}) is disabled. Will not start.")
            return

        if self._task and not self._task.done():
            logger.warning(f"{self.worker_name} ({self.worker_id}) is already running.")
            return

        self._health.status = NilveraWorkerStatus.STARTING
        self._health.started_at = _utc_now()
        self._health.degraded_reason = None

        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_wrapper(), name=self.worker_name)

        self._health.status = NilveraWorkerStatus.RUNNING
        logger.info(f"{self.worker_name} ({self.worker_id}) started.")

    async def stop(self) -> None:
        """Idempotent, graceful shutdown."""
        if not self._task:
            return

        self._health.status = NilveraWorkerStatus.STOPPING
        logger.info(f"{self.worker_name} ({self.worker_id}) stopping...")
        self._stop_event.set()

        try:
            # Wait up to 10 seconds for graceful drain
            await asyncio.wait_for(asyncio.shield(self._task), timeout=10.0)
        except TimeoutError:
            logger.warning(f"{self.worker_name} ({self.worker_id}) drain timeout exceeded. Forcing cancellation.")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"{self.worker_name} ({self.worker_id}) error during force cancel: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"{self.worker_name} ({self.worker_id}) error during stop: {e}")
        finally:
            self._task = None
            if self._health.status != NilveraWorkerStatus.FAILED:
                self._health.status = NilveraWorkerStatus.STOPPED
            logger.info(f"{self.worker_name} ({self.worker_id}) stopped.")

    def _record_heartbeat(self) -> None:
        """Record a heartbeat on every tick regardless of queue depth."""
        self._health.last_heartbeat_at = _utc_now()

    def _record_success(self, jobs_processed: int = 1) -> None:
        """Record successful processing."""
        self._health.last_success_at = _utc_now()
        self._health.processed_total += jobs_processed

    def _record_error(self, code: str, reason: str = "") -> None:
        """Record a controlled, sanitized error."""
        self._health.last_error_at = _utc_now()
        self._health.last_error_code = code
        self._health.failed_total += 1
        if reason:
            logger.error(f"{self.worker_name} error: {code} - {reason}")

    async def _run_wrapper(self) -> None:
        """Wraps the actual implementation to catch fatal outer-loop errors."""
        try:
            await self._run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"{self.worker_name} ({self.worker_id}) fatal outer loop error: {type(e).__name__}", exc_info=True)
            self._health.status = NilveraWorkerStatus.FAILED
            self._record_error("FATAL_LOOP_ERROR")
            self._health.degraded_reason = "Worker loop crashed"

    async def _run(self) -> None:
        """Implementation must be provided by subclass."""
        raise NotImplementedError("Subclasses must implement _run()")
