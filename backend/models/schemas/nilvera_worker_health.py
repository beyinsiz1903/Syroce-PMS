from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class NilveraWorkerStatus(str, Enum):
    DISABLED = "DISABLED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class NilveraWorkerHealth(BaseModel):
    """Standardized health reporting model for all Nilvera background workers."""
    worker_name: str
    enabled: bool
    status: NilveraWorkerStatus
    task_alive: bool = False
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_code: str | None = None
    processed_total: int = 0
    job_failed_total: int = 0
    loop_error_total: int = 0
    active_jobs: int = 0
    degraded_reason: str | None = None
