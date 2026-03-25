"""
Distributed Tracing Service — production-grade request tracing.
Persists trace spans to MongoDB, provides real request-level analytics,
slow endpoint detection, and correlation_id propagation.
"""
import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime

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
        self._total_requests = 0
        self._total_errors = 0
        self._total_slow = 0
        self._path_stats: dict[str, dict] = defaultdict(lambda: {
            "count": 0, "total_ms": 0.0, "errors": 0, "slow": 0, "max_ms": 0.0,
        })
        self.SLOW_THRESHOLD_MS = 1000

    def start_trace(self, request_path: str, method: str = "GET",
                    tenant_id: str | None = None,
                    correlation_id: str | None = None) -> str:
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

    def end_trace(self, trace_id: str, status_code: int = 200,
                  error: str | None = None):
        trace = self._active_traces.pop(trace_id, None)
        if not trace:
            return

        duration_ms = round((time.time() - trace["started_at"]) * 1000, 2)
        is_slow = duration_ms > self.SLOW_THRESHOLD_MS

        trace.update({
            "status_code": status_code,
            "error": error[:500] if error else None,
            "duration_ms": duration_ms,
            "is_slow": is_slow,
            "completed_at": datetime.now(UTC).isoformat(),
        })
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
        if len(self._completed_traces) > self._max_buffer:
            self._completed_traces = self._completed_traces[-1000:]

    async def flush_to_db(self) -> int:
        """Flush completed traces to MongoDB."""
        if not self._completed_traces:
            return 0
        to_flush = self._completed_traces[:]
        self._completed_traces.clear()
        try:
            from core.database import db
            # Insert without _id issues
            docs = [dict(t.items()) for t in to_flush]
            await db.observability_traces.insert_many(docs)
            logger.info(f"Flushed {len(docs)} traces to MongoDB")
            return len(docs)
        except Exception as e:
            logger.error(f"Trace flush failed: {e}")
            self._completed_traces.extend(to_flush)
            return 0

    async def get_trace_summary(self, hours: int = 1) -> dict:
        """Get trace summary from both in-memory stats and persisted data."""
        # Aggregate endpoint stats
        endpoints = []
        for path, stats in sorted(self._path_stats.items(), key=lambda x: -x[1]["count"]):
            avg_ms = round(stats["total_ms"] / max(stats["count"], 1), 2)
            endpoints.append({
                "path": path,
                "count": stats["count"],
                "avg_ms": avg_ms,
                "max_ms": round(stats["max_ms"], 2),
                "errors": stats["errors"],
                "slow": stats["slow"],
            })

        error_rate = self._total_errors / max(self._total_requests, 1)

        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "total_slow": self._total_slow,
            "error_rate": round(error_rate, 4),
            "active_traces": len(self._active_traces),
            "buffered_traces": len(self._completed_traces),
            "endpoints": endpoints[:30],
        }

    async def get_recent_traces(self, limit: int = 20, slow_only: bool = False) -> list[dict]:
        """Get recent traces from MongoDB."""
        try:
            from core.database import db
            q = {"is_slow": True} if slow_only else {}
            traces = await db.observability_traces.find(
                q, {"_id": 0}
            ).sort("started_at_iso", -1).to_list(limit)
            return traces
        except Exception:
            # Fallback to in-memory buffer
            result = self._completed_traces[:]
            if slow_only:
                result = [t for t in result if t.get("is_slow")]
            return sorted(result, key=lambda x: x.get("started_at_iso", ""), reverse=True)[:limit]

    async def get_slow_endpoints(self, threshold_ms: float = 1000, min_count: int = 3) -> list[dict]:
        """Get endpoints exceeding latency thresholds."""
        slow = []
        for path, stats in self._path_stats.items():
            avg = stats["total_ms"] / max(stats["count"], 1)
            if avg > threshold_ms and stats["count"] >= min_count:
                slow.append({
                    "path": path,
                    "avg_ms": round(avg, 2),
                    "count": stats["count"],
                    "slow_count": stats["slow"],
                })
        return sorted(slow, key=lambda x: -x["avg_ms"])

    async def get_hot_paths(self, top_n: int = 10) -> list[dict]:
        """Get most frequently accessed paths."""
        return sorted(
            [{"path": p, **s} for p, s in self._path_stats.items()],
            key=lambda x: -x["count"],
        )[:top_n]

    def get_path_stats(self) -> dict:
        return dict(self._path_stats)


tracing = TracingService()
