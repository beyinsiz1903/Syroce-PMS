"""
Distributed Tracing Service — production-grade request tracing.
Persists trace spans to MongoDB, provides real request-level analytics,
slow endpoint detection, and correlation_id propagation.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

logger = logging.getLogger("observability.tracing")


class TracingService:
    """
    In-memory trace collection with periodic flush to MongoDB.
    Tracks request paths, latencies, error rates, and slow endpoints.
    """

    def __init__(self):
        self._active_traces: dict[str, dict] = {}
        self._completed_traces: list[dict] = []
        self._max_buffer = 2000
        # Keep a separate rolling window for the live dashboard. The flush
        # buffer is cleared after persistence, so using it for live metrics
        # made recent traces disappear immediately after a flush.
        self._recent_traces: deque[dict] = deque(maxlen=self._max_buffer)
        self._flush_lock = asyncio.Lock()
        self._total_requests = 0
        self._total_errors = 0
        self._total_slow = 0
        self._path_stats: dict[str, dict] = defaultdict(
            lambda: {
                "count": 0,
                "total_ms": 0.0,
                "errors": 0,
                "slow": 0,
                "max_ms": 0.0,
            }
        )
        self.SLOW_THRESHOLD_MS = 1000

    def start_trace(self, request_path: str, method: str = "GET", tenant_id: str | None = None, correlation_id: str | None = None) -> str:
        trace_id = str(uuid.uuid4())
        self._active_traces[trace_id] = {
            "trace_id": trace_id,
            "request_path": request_path,
            "method": method,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id or trace_id,
            "started_at": time.time(),
            "started_at_iso": datetime.now(UTC).isoformat(),
            "status_code": None,
            "error": None,
            "duration_ms": None,
            "is_slow": False,
        }
        return trace_id

    def end_trace(self, trace_id: str, status_code: int = 200, error: str | None = None):
        trace = self._active_traces.pop(trace_id, None)
        if not trace:
            return

        duration_ms = round((time.time() - trace["started_at"]) * 1000, 2)
        is_slow = duration_ms > self.SLOW_THRESHOLD_MS

        trace.update(
            {
                "status_code": status_code,
                "error": error[:500] if error else None,
                "duration_ms": duration_ms,
                "is_slow": is_slow,
                "completed_at": datetime.now(UTC).isoformat(),
                "expires_at": datetime.now(UTC) + timedelta(days=14),
            }
        )
        del trace["started_at"]  # Remove raw timestamp

        # Update path stats
        path = trace["request_path"]
        ps = self._path_stats[path]
        ps["count"] += 1
        ps["total_ms"] += duration_ms
        ps["max_ms"] = max(ps["max_ms"], duration_ms)
        if status_code >= 400:
            ps["errors"] += 1
        if is_slow:
            ps["slow"] += 1

        self._total_requests += 1
        if status_code >= 400:
            self._total_errors += 1
        if is_slow:
            self._total_slow += 1

        # Buffer completed trace
        self._completed_traces.append(trace)
        self._recent_traces.append(trace.copy())
        if len(self._completed_traces) > self._max_buffer:
            self._completed_traces = self._completed_traces[-1000:]

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        """Return a nearest-rank percentile without external dependencies."""
        if not values:
            return 0.0
        ordered = sorted(values)
        rank = max(1, int(len(ordered) * percentile + 0.999999))
        return float(ordered[min(rank - 1, len(ordered) - 1)])

    def _traces_in_window(self, hours: int) -> list[dict]:
        cutoff = datetime.now(UTC) - timedelta(hours=max(hours, 1))
        result = []
        for trace in self._recent_traces:
            timestamp = trace.get("completed_at") or trace.get("started_at_iso")
            if not timestamp:
                continue
            try:
                completed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if completed_at.tzinfo is None:
                    completed_at = completed_at.replace(tzinfo=UTC)
                if completed_at >= cutoff:
                    result.append(trace)
            except (TypeError, ValueError):
                logger.debug("Skipping trace with invalid timestamp", exc_info=True)
        return result

    async def _load_traces_in_window(self, hours: int) -> list[dict]:
        """Combine every worker's persisted traces with this worker's buffer."""
        local = self._traces_in_window(hours)
        cutoff = datetime.now(UTC) - timedelta(hours=max(hours, 1))
        try:
            from core.database import db

            persisted = await asyncio.wait_for(
                db.observability_traces.find(
                    {"completed_at": {"$gte": cutoff.isoformat()}},
                    # Summaries never need spans, attributes or request payloads.
                    {"_id": 0, "trace_id": 1, "request_path": 1,
                     "duration_ms": 1, "status_code": 1, "is_slow": 1},
                )
                .sort("completed_at", -1)
                .to_list(self._max_buffer * 5),
                timeout=0.5,
            )
        except Exception:
            persisted = []

        combined = persisted + local
        by_id = {
            trace.get("trace_id", f"legacy-{index}"): trace
            for index, trace in enumerate(combined)
        }
        return list(by_id.values())

    @classmethod
    def _aggregate_paths(cls, traces: list[dict]) -> list[dict]:
        path_stats: dict[str, dict] = defaultdict(
            lambda: {"durations": [], "errors": 0, "slow": 0}
        )
        for trace in traces:
            path = trace.get("request_path") or "unknown"
            duration = float(trace.get("duration_ms") or 0)
            stats = path_stats[path]
            stats["durations"].append(duration)
            if int(trace.get("status_code") or 0) >= 400:
                stats["errors"] += 1
            if trace.get("is_slow"):
                stats["slow"] += 1

        endpoints = []
        for path, stats in path_stats.items():
            durations = stats["durations"]
            endpoints.append(
                {
                    "path": path,
                    "count": len(durations),
                    "avg_ms": round(sum(durations) / len(durations), 2),
                    "p95_ms": round(cls._percentile(durations, 0.95), 2),
                    "max_ms": round(max(durations), 2),
                    "errors": stats["errors"],
                    "slow": stats["slow"],
                }
            )
        return sorted(endpoints, key=lambda item: (-item["count"], -item["p95_ms"]))

    async def flush_to_db(self) -> int:
        """Flush completed traces to MongoDB."""
        async with self._flush_lock:
            if not self._completed_traces:
                return 0
            to_flush = self._completed_traces[:]
            self._completed_traces.clear()
            try:
                from core.database import db

                docs = [dict(t.items()) for t in to_flush]
                await asyncio.wait_for(
                    db.observability_traces.insert_many(docs),
                    timeout=5,
                )
                logger.debug("Flushed %d traces to MongoDB", len(docs))
                return len(docs)
            except Exception as exc:
                logger.error("Trace flush failed: %s", exc)
                self._completed_traces.extend(to_flush)
                return 0

    async def run_flush_loop(self, interval_seconds: float = 30) -> None:
        """Periodically publish process-local traces for multi-worker views."""
        while True:
            await asyncio.sleep(interval_seconds)
            await self.flush_to_db()

    async def get_trace_summary(self, hours: int = 1) -> dict:
        """Get a rolling trace summary combined across backend workers."""
        recent = await self._load_traces_in_window(hours)
        total_requests = len(recent)
        total_errors = sum(1 for trace in recent if int(trace.get("status_code") or 0) >= 400)
        total_slow = sum(1 for trace in recent if trace.get("is_slow"))
        error_rate = total_errors / max(total_requests, 1)

        return {
            "window_hours": hours,
            "window_scope": "multi_worker_rolling",
            "total_requests": total_requests,
            "total_errors": total_errors,
            "total_slow": total_slow,
            "error_rate": round(error_rate, 4),
            "active_traces": len(self._active_traces),
            "buffered_traces": len(self._completed_traces),
            "endpoints": self._aggregate_paths(recent)[:30],
        }

    async def get_recent_traces(self, limit: int = 20, slow_only: bool = False) -> list[dict]:
        """Get recent traces from MongoDB."""
        try:
            from core.database import db

            q = {"is_slow": True} if slow_only else {}
            persisted = await asyncio.wait_for(
                db.observability_traces.find(q, {"_id": 0})
                .sort("started_at_iso", -1)
                .to_list(limit),
                timeout=0.5,
            )
        except Exception:
            persisted = []

        # Include traces that have not been flushed yet and traces retained in
        # memory after a flush. De-duplicate because a trace may exist in both.
        combined = list(persisted) + list(self._recent_traces)
        by_id = {trace.get("trace_id", str(index)): trace for index, trace in enumerate(combined)}
        result = list(by_id.values())
        if slow_only:
            result = [trace for trace in result if trace.get("is_slow")]
        return sorted(result, key=lambda item: item.get("started_at_iso", ""), reverse=True)[:limit]

    async def get_slow_endpoints(self, threshold_ms: float = 1000, min_count: int = 1) -> list[dict]:
        """Get endpoints with any request exceeding the latency threshold."""
        traces = await self._load_traces_in_window(1)
        endpoints = self._aggregate_paths(traces)
        slow_counts: dict[str, int] = defaultdict(int)
        for trace in traces:
            if float(trace.get("duration_ms") or 0) > threshold_ms:
                slow_counts[trace.get("request_path") or "unknown"] += 1
        slow = [
            {**endpoint, "slow_count": slow_counts[endpoint["path"]]}
            for endpoint in endpoints
            if endpoint["count"] >= min_count and endpoint["max_ms"] > threshold_ms
        ]
        return sorted(slow, key=lambda item: (-item["p95_ms"], -item["max_ms"]))

    async def get_hot_paths(self, top_n: int = 10) -> list[dict]:
        """Get most frequently accessed paths in the last hour."""
        return self._aggregate_paths(await self._load_traces_in_window(1))[:top_n]

    def get_path_stats(self) -> dict:
        return dict(self._path_stats)


tracing = TracingService()
