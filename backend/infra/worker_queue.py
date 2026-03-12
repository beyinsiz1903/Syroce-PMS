"""
Worker Queue Manager — Celery task routing, queue monitoring, and worker health.
Provides named queues, retry policies, dead letter handling, and status APIs.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger("infra.worker_queue")


# ── Queue Definitions ──────────────────────────────────────────────
QUEUE_DEFINITIONS = {
    "default": {
        "description": "General purpose tasks",
        "max_retries": 3,
        "retry_backoff": True,
        "task_time_limit": 600,
        "priority": "normal",
    },
    "ml": {
        "description": "ML training and prediction tasks",
        "max_retries": 2,
        "retry_backoff": True,
        "task_time_limit": 3600,
        "priority": "low",
    },
    "analytics": {
        "description": "Analytics export and report generation",
        "max_retries": 3,
        "retry_backoff": True,
        "task_time_limit": 1800,
        "priority": "normal",
    },
    "messaging": {
        "description": "Messaging delivery and retries",
        "max_retries": 5,
        "retry_backoff": True,
        "task_time_limit": 120,
        "priority": "high",
    },
    "pipeline": {
        "description": "Data pipeline orchestration",
        "max_retries": 2,
        "retry_backoff": True,
        "task_time_limit": 1800,
        "priority": "normal",
    },
    "backup": {
        "description": "Backup and maintenance tasks",
        "max_retries": 1,
        "retry_backoff": False,
        "task_time_limit": 7200,
        "priority": "low",
    },
}

# ── Task Routing ──────────────────────────────────────────────────
TASK_ROUTES = {
    # ML tasks
    "celery_tasks.ml_training_task": {"queue": "ml"},
    "celery_tasks.ml_scheduled_run_task": {"queue": "ml"},
    "celery_tasks.ml_prediction_task": {"queue": "ml"},
    "celery_tasks.update_occupancy_forecast_task": {"queue": "ml"},
    # Analytics tasks
    "celery_tasks.analytics_export_task": {"queue": "analytics"},
    "celery_tasks.generate_daily_reports_task": {"queue": "analytics"},
    "celery_tasks.report_generation_task": {"queue": "analytics"},
    # Messaging tasks
    "celery_tasks.messaging_retry_task": {"queue": "messaging"},
    "celery_tasks.messaging_batch_send_task": {"queue": "messaging"},
    "celery_tasks.process_pending_efaturas_task": {"queue": "messaging"},
    # Pipeline tasks
    "celery_tasks.pipeline_orchestration_task": {"queue": "pipeline"},
    "celery_tasks.data_sync_task": {"queue": "pipeline"},
    # Backup tasks
    "celery_tasks.backup_mongodb_task": {"queue": "backup"},
    "celery_tasks.archive_old_data_task": {"queue": "backup"},
    "celery_tasks.snapshot_cleanup_task": {"queue": "backup"},
}


class WorkerQueueManager:
    """Monitors worker health, queue sizes, and task execution."""

    def __init__(self):
        self._task_history: List[Dict[str, Any]] = []
        self._failure_archive: List[Dict[str, Any]] = []
        self._max_history = 1000
        self._max_failures = 500
        self._metrics = defaultdict(lambda: {
            "submitted": 0, "completed": 0, "failed": 0,
            "retried": 0, "timed_out": 0,
        })

    def record_task_start(self, task_name: str, task_id: str, queue: str):
        self._task_history.append({
            "task_id": task_id,
            "task_name": task_name,
            "queue": queue,
            "status": "started",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        self._metrics[queue]["submitted"] += 1
        if len(self._task_history) > self._max_history:
            self._task_history = self._task_history[-self._max_history:]

    def record_task_complete(self, task_name: str, task_id: str,
                              queue: str, duration_sec: float):
        self._metrics[queue]["completed"] += 1
        for entry in reversed(self._task_history):
            if entry["task_id"] == task_id:
                entry["status"] = "completed"
                entry["duration_sec"] = round(duration_sec, 3)
                entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                break

    def record_task_failure(self, task_name: str, task_id: str,
                             queue: str, error: str, retries: int = 0):
        self._metrics[queue]["failed"] += 1
        failure = {
            "task_id": task_id,
            "task_name": task_name,
            "queue": queue,
            "error": error[:500],
            "retries": retries,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._failure_archive.append(failure)
        if len(self._failure_archive) > self._max_failures:
            self._failure_archive = self._failure_archive[-self._max_failures:]

    def record_task_retry(self, task_name: str, task_id: str, queue: str):
        self._metrics[queue]["retried"] += 1

    def get_queue_status(self) -> Dict[str, Any]:
        """Get status of all queues with metrics."""
        result = {}
        for queue_name, definition in QUEUE_DEFINITIONS.items():
            metrics = self._metrics.get(queue_name, {
                "submitted": 0, "completed": 0, "failed": 0,
                "retried": 0, "timed_out": 0,
            })
            result[queue_name] = {
                **definition,
                "metrics": dict(metrics),
                "pending": max(0, metrics.get("submitted", 0) - metrics.get("completed", 0) - metrics.get("failed", 0)),
            }
        return result

    def get_failure_archive(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._failure_archive[-limit:]

    def get_stuck_task_candidates(self, timeout_sec: float = 300) -> List[Dict[str, Any]]:
        """Find tasks that might be stuck."""
        now = datetime.now(timezone.utc)
        stuck = []
        for entry in self._task_history:
            if entry["status"] == "started":
                started = datetime.fromisoformat(entry["started_at"])
                if (now - started).total_seconds() > timeout_sec:
                    stuck.append(entry)
        return stuck

    def get_worker_summary(self) -> Dict[str, Any]:
        total_submitted = sum(m.get("submitted", 0) for m in self._metrics.values())
        total_completed = sum(m.get("completed", 0) for m in self._metrics.values())
        total_failed = sum(m.get("failed", 0) for m in self._metrics.values())
        return {
            "queues": list(QUEUE_DEFINITIONS.keys()),
            "total_submitted": total_submitted,
            "total_completed": total_completed,
            "total_failed": total_failed,
            "total_pending": max(0, total_submitted - total_completed - total_failed),
            "failure_archive_size": len(self._failure_archive),
            "stuck_candidates": len(self.get_stuck_task_candidates()),
            "queue_details": self.get_queue_status(),
        }


# Singleton
worker_queue_manager = WorkerQueueManager()
