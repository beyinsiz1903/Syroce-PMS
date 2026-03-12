"""
Metrics Collector - Centralized application metrics collection.
Collects: websocket latency, ML execution time, autopricing success rate,
messaging delivery rate, reservation sync lag, event throughput, etc.
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from core.database import db

logger = logging.getLogger("observability.metrics")


class MetricType:
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class MetricsCollector:
    """In-process metrics collection with MongoDB persistence."""

    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._last_flush = datetime.now(timezone.utc)

    # -- Recording --

    def increment(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None):
        key = self._key(name, tags)
        self._counters[key] += value

    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        key = self._key(name, tags)
        self._gauges[key] = value

    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        key = self._key(name, tags)
        self._histograms[key].append(value)
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-500:]

    def timer_start(self, name: str) -> float:
        return time.time()

    def timer_end(self, name: str, start: float, tags: Optional[Dict[str, str]] = None):
        elapsed_ms = (time.time() - start) * 1000
        key = self._key(name, tags)
        self._timers[key].append(elapsed_ms)
        if len(self._timers[key]) > 1000:
            self._timers[key] = self._timers[key][-500:]

    # -- Predefined Metrics --

    def record_websocket_latency(self, latency_ms: float, tenant_id: str = ""):
        self.histogram("websocket_latency_ms", latency_ms, {"tenant": tenant_id})

    def record_ml_execution(self, model_type: str, duration_sec: float, success: bool):
        self.histogram("ml_execution_time_sec", duration_sec, {"model": model_type})
        self.increment(f"ml_execution_{'success' if success else 'failure'}", tags={"model": model_type})

    def record_autopricing(self, success: bool, confidence: float = 0.0):
        self.increment(f"autopricing_{'success' if success else 'failure'}")
        if success:
            self.histogram("autopricing_confidence", confidence)

    def record_messaging_delivery(self, provider: str, success: bool):
        self.increment(f"messaging_delivery_{'success' if success else 'failure'}", tags={"provider": provider})

    def record_reservation_sync(self, lag_ms: float, channel: str = ""):
        self.histogram("reservation_sync_lag_ms", lag_ms, {"channel": channel})

    def record_event_throughput(self, count: int = 1):
        self.increment("event_throughput", count)

    # -- Query --

    def get_all_metrics(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "collected_at": now,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: self._summarize_histogram(v)
                for k, v in self._histograms.items()
            },
            "timers": {
                k: self._summarize_histogram(v)
                for k, v in self._timers.items()
            },
        }

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Get metrics formatted for the observability dashboard."""
        ws_lat = self._histograms.get("websocket_latency_ms", [])
        ml_time = self._histograms.get("ml_execution_time_sec", [])
        ap_conf = self._histograms.get("autopricing_confidence", [])
        sync_lag = self._histograms.get("reservation_sync_lag_ms", [])

        ap_success = sum(v for k, v in self._counters.items() if "autopricing_success" in k)
        ap_failure = sum(v for k, v in self._counters.items() if "autopricing_failure" in k)
        msg_success = sum(v for k, v in self._counters.items() if "messaging_delivery_success" in k)
        msg_failure = sum(v for k, v in self._counters.items() if "messaging_delivery_failure" in k)

        return {
            "websocket_latency": self._summarize_histogram(ws_lat),
            "ml_execution_time": self._summarize_histogram(ml_time),
            "autopricing": {
                "success_count": int(ap_success),
                "failure_count": int(ap_failure),
                "success_rate": round(ap_success / max(ap_success + ap_failure, 1), 4),
                "avg_confidence": self._summarize_histogram(ap_conf).get("avg", 0),
            },
            "messaging_delivery": {
                "success_count": int(msg_success),
                "failure_count": int(msg_failure),
                "delivery_rate": round(msg_success / max(msg_success + msg_failure, 1), 4),
            },
            "reservation_sync_lag": self._summarize_histogram(sync_lag),
            "event_throughput": int(self._counters.get("event_throughput", 0)),
        }

    async def flush_to_db(self):
        """Persist current metrics snapshot to MongoDB."""
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": self.get_all_metrics(),
            "dashboard": self.get_dashboard_metrics(),
        }
        await db.observability_metrics.insert_one(snapshot)
        self._last_flush = datetime.now(timezone.utc)
        return {"flushed_at": snapshot["timestamp"]}

    async def get_historical_metrics(self, hours: int = 24, limit: int = 100) -> List[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return await db.observability_metrics.find(
            {"timestamp": {"$gte": cutoff}}, {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)

    # -- Helpers --

    def _key(self, name: str, tags: Optional[Dict[str, str]] = None) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"

    def _summarize_histogram(self, values: List[float]) -> dict:
        if not values:
            return {"count": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}
        sorted_v = sorted(values)
        n = len(sorted_v)
        return {
            "count": n,
            "avg": round(sum(sorted_v) / n, 4),
            "min": round(sorted_v[0], 4),
            "max": round(sorted_v[-1], 4),
            "p50": round(sorted_v[int(n * 0.5)], 4),
            "p95": round(sorted_v[min(int(n * 0.95), n - 1)], 4),
            "p99": round(sorted_v[min(int(n * 0.99), n - 1)], 4),
        }


# Singleton
metrics = MetricsCollector()
