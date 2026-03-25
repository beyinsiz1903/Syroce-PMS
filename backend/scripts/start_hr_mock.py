#!/usr/bin/env python3
"""Start HotelRunner Mock Server on port 9999."""
import sys
sys.path.insert(0, "/app/backend")

from domains.channel_manager.providers.hotelrunner.mock_server import run_mock_server_sync
run_mock_server_sync(port=9999)
