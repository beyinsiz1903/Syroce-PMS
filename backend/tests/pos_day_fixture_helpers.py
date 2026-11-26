"""Open-day stores for unit tests that isolate stock/table/refund behavior.

Closed-day and concurrent admission are covered against a real local replica
set in test_pos_closed_day_write_guard.py.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock


def open_pos_day_collections():
    return {
        "pos_closure_locks": SimpleNamespace(create_index=AsyncMock(), update_one=AsyncMock()),
        "pos_closures": SimpleNamespace(find_one=AsyncMock(return_value=None)),
    }
