#!/usr/bin/env python3
"""Start HotelRunner Mock Server on port 9999."""
import sys  # noqa: I001

sys.path.insert(0, "/app/backend")

from domains.channel_manager.providers.hotelrunner.mock_server import run_mock_server_sync  # noqa: E402

run_mock_server_sync(port=9999)
