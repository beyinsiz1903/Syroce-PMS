"""
Distributed Tracing - Request-level tracing for observability.
Tracks request lifecycle across services with correlation IDs.
"""
import logging
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from core.database import db

logger = logging.getLogger("observability.tracing")


class TracingService:
    """Lightweight distributed tracing for request lifecycle tracking."""

    def __init__(self):
        self._active_traces: Dict[str, dict] = {}
        self._trace_buffer: List[dict] = []

    def start_trace(self, request_path: str, method: str = "GET",
                    tenant_id: Optional[str] = None,
                    correlation_id: Optional[str] = None) -> str:
        """Start a new trace for a request."""
        trace_id = correlation_id or str(uuid.uuid4())
        self._active_traces[trace_id] = {
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "request_path": request_path,
            "method": method,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "start_time": time.time(),
            "spans": [],
            "status": "active",
            "error": None,
        }
        return trace_id

    def add_span(self, trace_id: str, span_name: str, metadata: Optional[dict] = None):
        """Add a span (sub-operation) to an active trace."""
        trace = self._active_traces.get(trace_id)
        if not trace:
            return
        trace["spans"].append({
            "span_id": str(uuid.uuid4()),
            "name": span_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": round((time.time() - trace["start_time"]) * 1000, 2),
            "metadata": metadata or {},
        })

    def end_trace(self, trace_id: str, status_code: int = 200,
                  error: Optional[str] = None) -> Optional[dict]:
        """Complete a trace and buffer for persistence."""
        trace = self._active_traces.pop(trace_id, None)
        if not trace:
            return None

        elapsed_ms = round((time.time() - trace["start_time"]) * 1000, 2)
        completed_trace = {
            "trace_id": trace["trace_id"],
            "tenant_id": trace["tenant_id"],
            "request_path": trace["request_path"],
            "method": trace["method"],
            "status_code": status_code,
            "duration_ms": elapsed_ms,
            "span_count": len(trace["spans"]),
            "spans": trace["spans"],
            "started_at": trace["started_at"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "is_slow": elapsed_ms > 1000,
        }
        self._trace_buffer.append(completed_trace)

        if len(self._trace_buffer) > 100:
            self._trace_buffer = self._trace_buffer[-50:]

        return completed_trace

    async def flush_traces(self):
        """Persist buffered traces to MongoDB."""
        if not self._trace_buffer:
            return {"flushed": 0}
        to_flush = self._trace_buffer[:]
        self._trace_buffer.clear()
        if to_flush:
            await db.observability_traces.insert_many(to_flush)
        return {"flushed": len(to_flush)}

    async def get_recent_traces(self, tenant_id: Optional[str] = None,
                                limit: int = 50, slow_only: bool = False) -> List[dict]:
        q: Dict[str, Any] = {}
        if tenant_id:
            q["tenant_id"] = tenant_id
        if slow_only:
            q["is_slow"] = True
        return await db.observability_traces.find(
            q, {"_id": 0}
        ).sort("started_at", -1).to_list(limit)

    async def get_trace_summary(self, hours: int = 1) -> Dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        pipeline = [
            {"$match": {"started_at": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$request_path",
                "count": {"$sum": 1},
                "avg_duration_ms": {"$avg": "$duration_ms"},
                "max_duration_ms": {"$max": "$duration_ms"},
                "error_count": {"$sum": {"$cond": [{"$ne": ["$error", None]}, 1, 0]}},
                "slow_count": {"$sum": {"$cond": ["$is_slow", 1, 0]}},
            }},
            {"$sort": {"count": -1}},
            {"$limit": 30},
        ]
        results = await db.observability_traces.aggregate(pipeline).to_list(30)
        total = sum(r["count"] for r in results)
        errors = sum(r["error_count"] for r in results)
        return {
            "period_hours": hours,
            "total_requests": total,
            "total_errors": errors,
            "error_rate": round(errors / max(total, 1), 4),
            "endpoints": [
                {
                    "path": r["_id"],
                    "count": r["count"],
                    "avg_ms": round(r["avg_duration_ms"], 2),
                    "max_ms": round(r["max_duration_ms"], 2),
                    "errors": r["error_count"],
                    "slow": r["slow_count"],
                }
                for r in results
            ],
            "active_traces": len(self._active_traces),
        }


tracing = TracingService()
