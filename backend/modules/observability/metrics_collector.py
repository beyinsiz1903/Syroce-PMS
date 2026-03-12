"""
Metrics Collector — production-grade application metrics with histogram support.
Collects counters, gauges, histograms. Supports flush to MongoDB.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List
from collections import defaultdict

logger = logging.getLogger("observability.metrics")


class MetricsCollector:
    """Application-level metrics collector with persistent flush support."""

    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._max_histogram_size = 1000

        # Specific business metrics
        self._event_throughput = 0
        self._websocket_latencies: List[float] = []
        self._ml_execution_times: List[float] = []
        self._autopricing_results = {"success": 0, "failure": 0}
        self._messaging_delivery = {"success": 0, "failure": 0}
        self._reservation_sync_lags: List[float] = []

    def increment(self, name: str, value: float = 1, tags: dict = None):
        key = self._make_key(name, tags)
        self._counters[key] += value

    def gauge(self, name: str, value: float, tags: dict = None):
        key = self._make_key(name, tags)
        self._gauges[key] = value

    def histogram(self, name: str, value: float, tags: dict = None):
        key = self._make_key(name, tags)
        self._histograms[key].append(value)
        if len(self._histograms[key]) > self._max_histogram_size:
            self._histograms[key] = self._histograms[key][-500:]

    def _make_key(self, name: str, tags: dict = None) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}|{tag_str}"

    # ── Business metric recorders ──

    def record_event_throughput(self, count: int = 1):
        self._event_throughput += count

    def record_websocket_latency(self, latency_ms: float):
        self._websocket_latencies.append(latency_ms)
        if len(self._websocket_latencies) > 500:
            self._websocket_latencies = self._websocket_latencies[-250:]

    def record_ml_execution(self, duration_sec: float):
        self._ml_execution_times.append(duration_sec)
        if len(self._ml_execution_times) > 100:
            self._ml_execution_times = self._ml_execution_times[-50:]

    def record_autopricing_result(self, success: bool):
        key = "success" if success else "failure"
        self._autopricing_results[key] += 1

    def record_messaging_delivery(self, provider_type: str, success: bool):
        key = "success" if success else "failure"
        self._messaging_delivery[key] += 1
        self.increment("messaging_delivery_total", tags={"provider": provider_type, "result": key})

    def record_reservation_sync_lag(self, lag_ms: float):
        self._reservation_sync_lags.append(lag_ms)
        if len(self._reservation_sync_lags) > 500:
            self._reservation_sync_lags = self._reservation_sync_lags[-250:]

    # ── Stat helpers ──

    def _summarize_list(self, values: List[float]) -> dict:
        if not values:
            return {"count": 0, "avg": 0, "p95": 0, "max": 0}
        sorted_v = sorted(values)
        n = len(sorted_v)
        return {
            "count": n,
            "avg": round(sum(sorted_v) / n, 2),
            "p95": round(sorted_v[min(int(n * 0.95), n - 1)], 2),
            "max": round(sorted_v[-1], 2),
        }

    # ── Dashboard metrics ──

    def get_dashboard_metrics(self) -> dict:
        msg_total = self._messaging_delivery["success"] + self._messaging_delivery["failure"]
        return {
            "event_throughput": self._event_throughput,
            "websocket_latency": self._summarize_list(self._websocket_latencies),
            "ml_execution_time": self._summarize_list(self._ml_execution_times),
            "autopricing": {
                **self._autopricing_results,
                "success_rate": (
                    self._autopricing_results["success"] /
                    max(self._autopricing_results["success"] + self._autopricing_results["failure"], 1)
                ),
            },
            "messaging_delivery": {
                **self._messaging_delivery,
                "delivery_rate": (
                    self._messaging_delivery["success"] / max(msg_total, 1)
                ),
                "success_count": self._messaging_delivery["success"],
                "failure_count": self._messaging_delivery["failure"],
            },
            "reservation_sync_lag": self._summarize_list(self._reservation_sync_lags),
        }

    def get_all_metrics(self) -> dict:
        hist_summaries = {}
        for key, values in self._histograms.items():
            hist_summaries[key] = self._summarize_list(values)
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": hist_summaries,
        }

    async def flush_to_db(self) -> int:
        """Flush current metrics snapshot to MongoDB."""
        try:
            from core.database import db
            snapshot = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "dashboard": self.get_dashboard_metrics(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await db.observability_metrics.insert_one(snapshot)
            return 1
        except Exception as e:
            logger.error(f"Metrics flush failed: {e}")
            return 0


# Singleton
metrics = MetricsCollector()
