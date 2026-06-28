"""
Smoke Test Runner — Post-Deploy Critical Path Validation
=========================================================
Executes real HTTP requests against critical endpoints.
Used as the final gate in the deploy pipeline and after canary promotion.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from common.result import ServiceResult

logger = logging.getLogger("ops.smoke_test_runner")

SMOKE_TESTS = [
    {
        "id": "health_liveness",
        "name": "Health: Liveness",
        "method": "GET",
        "path": "/health/liveness",
        "expected_status": 200,
        "critical": True,
        "auth_required": False,
    },
    {
        "id": "health_basic",
        "name": "Health: Basic",
        "method": "GET",
        "path": "/health/",
        "expected_status": 200,
        "critical": True,
        "auth_required": False,
    },
    {
        "id": "health_db",
        "name": "Health: DB Connectivity",
        "method": "GET",
        "path": "/health/db",
        "expected_status": 200,
        "critical": True,
        "auth_required": False,
    },
    {
        "id": "auth_login",
        "name": "Auth: Login Flow",
        "method": "POST",
        "path": "/api/auth/login",
        "body": {"email": "demo@hotel.com", "password": "demo123"},
        "expected_status": 200,
        "critical": True,
        "auth_required": False,
        "extract_token": True,
    },
    {
        "id": "rooms_list",
        "name": "Rooms: List",
        "method": "GET",
        "path": "/api/pms/rooms",
        "expected_status": 200,
        "critical": True,
        "auth_required": True,
    },
    {
        "id": "bookings_list",
        "name": "Bookings: List",
        "method": "GET",
        "path": "/api/pms/bookings",
        "expected_status": 200,
        "critical": False,
        "auth_required": True,
    },
    {
        "id": "guests_list",
        "name": "Guests: List",
        "method": "GET",
        "path": "/api/pms/guests",
        "expected_status": 200,
        "critical": False,
        "auth_required": True,
    },
    {
        "id": "settings",
        "name": "Settings: Hotel",
        "method": "GET",
        "path": "/api/pms/hotel-settings",
        "expected_status": 200,
        "critical": False,
        "auth_required": True,
    },
]


class SmokeTestRunner:
    """Executes smoke tests against the running application."""

    def __init__(self):
        self._base_url = "http://localhost:8001"

    async def run_all(self) -> ServiceResult:
        """Run all smoke tests sequentially."""
        now = datetime.now(UTC).isoformat()
        results: list[dict[str, Any]] = []
        token = None
        total_passed = 0

        async with httpx.AsyncClient(base_url=self._base_url, timeout=15.0) as client:
            for test in SMOKE_TESTS:
                t0 = time.time()
                test_result = await self._run_single(client, test, token)
                duration_ms = int((time.time() - t0) * 1000)

                test_result["duration_ms"] = duration_ms
                results.append(test_result)

                if test_result["passed"]:
                    total_passed += 1

                # Extract token for subsequent auth tests
                if test.get("extract_token") and test_result["passed"] and test_result.get("token"):
                    token = test_result["token"]

        return ServiceResult.success(
            {
                "ran_at": now,
                "total": len(SMOKE_TESTS),
                "passed": total_passed,
                "failed": len(SMOKE_TESTS) - total_passed,
                "results": results,
                "critical_failures": [r for r in results if not r["passed"] and r.get("critical")],
                "verdict": "PASS" if total_passed == len(SMOKE_TESTS) else "FAIL",
            }
        )

    async def _run_single(self, client: httpx.AsyncClient, test: dict, token: str = None) -> dict:
        result = {
            "id": test["id"],
            "name": test["name"],
            "path": test["path"],
            "critical": test.get("critical", False),
            "passed": False,
            "status_code": None,
            "error": None,
        }

        headers = {}
        if test.get("auth_required") and token:
            headers["Authorization"] = f"Bearer {token}"
        elif test.get("auth_required") and not token:
            result["error"] = "No auth token available (login test must pass first)"
            return result

        try:
            if test["method"] == "GET":
                resp = await client.get(test["path"], headers=headers)
            elif test["method"] == "POST":
                resp = await client.post(test["path"], json=test.get("body", {}), headers=headers)
            else:
                result["error"] = f"Unsupported method: {test['method']}"
                return result

            result["status_code"] = resp.status_code

            if resp.status_code == test["expected_status"]:
                result["passed"] = True

                # Extract token if needed
                if test.get("extract_token"):
                    try:
                        data = resp.json()
                        token_val = data.get("access_token") or data.get("token")
                        if token_val:
                            result["token"] = token_val
                    except Exception:
                        pass
            else:
                result["error"] = f"Expected {test['expected_status']}, got {resp.status_code}"

        except httpx.ConnectError:
            result["error"] = "Connection refused — service not running"
        except httpx.TimeoutException:
            result["error"] = "Request timed out"
        except Exception as e:
            result["error"] = str(e)[:200]

        return result


smoke_test_runner = SmokeTestRunner()
