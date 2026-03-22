"""
Control Plane — Operational Visibility, Failure Tracking, and Reliability Layer
================================================================================
This is NOT a dashboard module. This is a SYSTEM BEHAVIOR LAYER that provides:

1. Strict failure taxonomy and structured failure events
2. Centralized failure tracking with classification
3. Retry/replay engine with idempotency guarantees
4. Secret access control and audit
5. Operational alerting (log + webhook)
6. Structured runbooks for operator guidance
7. Startup validation for critical components

All failures across the system (reservation ingest, ARI push, outbox events,
sync jobs, secret access) flow through this control plane.
"""
from .failure_model import (
    FailureType,
    Severity,
    OperationType,
    FailureStatus,
)
from .failure_tracker import FailureTracker, get_failure_tracker

__all__ = [
    "FailureType",
    "Severity",
    "OperationType",
    "FailureStatus",
    "FailureTracker",
    "get_failure_tracker",
]
