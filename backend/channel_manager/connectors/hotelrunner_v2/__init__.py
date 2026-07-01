"""
HotelRunner v2 Connector — Production-Grade Adapter
=====================================================

Clean-room implementation. Does NOT use legacy client.
Adapter pattern: client.py → mapper.py → service.py

Feature flags: tenant-based enable/disable.
Shadow mode:   ingest + compare only (no writes).
"""

from .service import HotelRunnerV2Service

__all__ = ["HotelRunnerV2Service"]
