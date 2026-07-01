import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


def parse_args():
    parser = argparse.ArgumentParser(description="Smoke Test Script for Pilot Demo Flow")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="Base URL of the backend")
    parser.add_argument("--email", type=str, default="demo@syroce.com", help="Admin email")
    parser.add_argument("--hotel-id", type=str, help="Optional hotel ID for login")
    parser.add_argument("--username", type=str, help="Optional username for login")
    parser.add_argument("--password", type=str, help="Admin password (required unless SMOKE_PASSWORD env is set)")
    parser.add_argument("--allow-mutations", action="store_true", help="Allow state-changing (destructive) operations")
    parser.add_argument("--force-local-mutations", action="store_true", help="Force mutations on local environment even if tenant name cannot be resolved safely")
    parser.add_argument("--read-only", action="store_true", help="Explicitly mark read-only mode (default if --allow-mutations is omitted)")
    parser.add_argument("--origin", type=str, help="Origin header for CSRF (defaults to base-url)")

    args = parser.parse_args()
    if not args.password:
        args.password = os.environ.get("SMOKE_PASSWORD")
    if not args.password:
        print("ERROR: Password must be provided via --password or SMOKE_PASSWORD environment variable.")
        sys.exit(1)

    return args


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


def log_success(msg):
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {msg}")


def log_error(msg):
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {msg}")


def log_warn(msg):
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {msg}")


def log_info(msg):
    print(f"{Colors.CYAN}[INFO]{Colors.RESET} {msg}")


def log_skipped(msg):
    print(f"{Colors.CYAN}[SKIPPED]{Colors.RESET} {msg}")


def redact_tokens(data):
    """Recursively redact sensitive token fields in JSON structures."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if k.lower() in ["access_token", "refresh_token", "token", "authorization"]:
                redacted[k] = "***REDACTED***"
            else:
                redacted[k] = redact_tokens(v)
        return redacted
    elif isinstance(data, list):
        return [redact_tokens(item) for item in data]
    return data


def extract_items(data, keys=("items", "bookings", "data", "results", "rooms", "tasks")):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        return []
    return []


class DemoSmokeTest:
    def __init__(self, base_url, email, password, allow_mutations, origin=None, hotel_id=None, username=None, force_local_mutations=False):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.hotel_id = hotel_id
        self.username = username
        self.password = password
        self.mutations_requested = allow_mutations or force_local_mutations
        self.allow_mutations = self.mutations_requested
        self.force_local_mutations = force_local_mutations
        self.origin = origin.rstrip("/") if origin else self.base_url

        self.session = requests.Session()
        self.token = None
        self.tenant_id = None
        self.tenant_name = None

        # Test state
        self.ts_id = datetime.now().strftime("%Y%m%d%H%M%S")
        self.booking_id = None
        self.room_id = None
        self.target_room_id = None
        self.folio_id = None
        self.report_data = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "email": self.email,
            "mutations_requested": self.mutations_requested,
            "mutations_enabled": self.allow_mutations,
            "tenant_safety_reason": "",
            "mode": "mutating" if self.allow_mutations else "read-only",
            "steps": [],
        }

    def _req(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"

        headers = kwargs.get("headers", {})
        headers["Origin"] = self.origin
        headers["Referer"] = f"{self.origin}/"

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        kwargs["headers"] = headers

        try:
            start = time.time()
            resp = self.session.request(method, url, timeout=10, **kwargs)
            latency = int((time.time() - start) * 1000)
            return resp, latency, None
        except Exception as e:
            return None, 0, str(e)

    def _log_step(self, step_name, method, endpoint, resp, lat, err, expected_status=[200]):
        status_code = resp.status_code if resp is not None else "ERROR"

        resp_summary = ""
        if resp is not None:
            try:
                resp_json = resp.json()
                safe_json = redact_tokens(resp_json)
                dumped = json.dumps(safe_json)
                resp_summary = dumped[:150] + "..." if len(dumped) > 150 else dumped
            except:
                resp_summary = resp.text[:150] + "..." if len(resp.text) > 150 else resp.text

        is_success = resp is not None and resp.status_code in expected_status

        step_result = {
            "step": step_name,
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": lat,
            "success": bool(is_success),
            "response_summary": resp_summary,
            "error_reason": err if err else (f"Unexpected Status {status_code}" if not is_success else None),
        }
        self.report_data["steps"].append(step_result)

        if is_success:
            log_success(f"{step_name} | {method} {endpoint} | Status: {status_code} | {lat}ms")
        else:
            reason = err if err else f"Status {status_code}. Resp: {resp_summary}"
            log_error(f"{step_name} | {method} {endpoint} | FAIL: {reason} | {lat}ms")

        return is_success, resp

    def _skip_step(self, step_name, reason):
        log_skipped(f"{step_name} | Reason: {reason}")
        self.report_data["steps"].append({"step": step_name, "success": False, "status_code": "SKIPPED", "error_reason": reason})

    def save_report(self):
        reports_dir = Path(__file__).resolve().parent.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        filename = reports_dir / f"smoke_demo_flow_{self.ts_id}.json"
        with open(filename, "w") as f:
            json.dump(self.report_data, f, indent=2, default=str)
        log_info(f"JSON Report saved to {filename}")

    def _resolve_tenant_name(self, login_data):
        tenant_obj = login_data.get("tenant") or login_data.get("user", {}).get("tenant")

        if not tenant_obj:
            resp, lat, err = self._req("GET", "/api/auth/me")
            if resp and resp.status_code == 200:
                me_data = resp.json()
                tenant_obj = me_data.get("tenant") or me_data.get("user", {}).get("tenant")

        if tenant_obj and isinstance(tenant_obj, dict):
            for field in ["name", "property_name", "hotel_name", "display_name", "slug", "code"]:
                if field in tenant_obj and tenant_obj[field]:
                    return str(tenant_obj[field])

        return login_data.get("tenant_name") or login_data.get("tenant_id") or login_data.get("user", {}).get("tenant_id")

    def check_tenant_safety(self, login_data):
        if not self.mutations_requested:
            self.report_data["mutations_enabled"] = False
            self.report_data["tenant_safety_reason"] = "Mutations not requested"
            return True

        self.tenant_name = self._resolve_tenant_name(login_data)

        if not self.tenant_name:
            if self.force_local_mutations and ("localhost" in self.base_url or "127.0.0.1" in self.base_url):
                log_warn("Tenant name missing. Forcing local mutations via --force-local-mutations flag.")
                self.allow_mutations = True
                self.report_data["mutations_enabled"] = True
                self.report_data["tenant_safety_reason"] = "Forced local mutations (tenant name missing)"
                return True

            reason = "Tenant name missing and not local force. Mutations disabled."
            log_warn(reason)
            self.allow_mutations = False
            self.report_data["mutations_enabled"] = False
            self.report_data["tenant_safety_reason"] = reason
            return False

        safe_keywords = ["test", "demo", "pilot", "sandbox", "local"]
        if any(kw in self.tenant_name.lower() for kw in safe_keywords):
            reason = f"Safe tenant detected: {self.tenant_name}"
            log_info(f"Tenant safety label: {self.tenant_name}")
            self.allow_mutations = True
            self.report_data["mutations_enabled"] = True
            self.report_data["tenant_safety_reason"] = reason
            return True

        if self.force_local_mutations and ("localhost" in self.base_url or "127.0.0.1" in self.base_url):
            reason = f"Unsafe tenant '{self.tenant_name}' overridden by --force-local-mutations"
            log_warn(reason)
            self.allow_mutations = True
            self.report_data["mutations_enabled"] = True
            self.report_data["tenant_safety_reason"] = reason
            return True

        reason = f"Tenant '{self.tenant_name}' does not appear to be a test/demo tenant. Mutations disabled."
        log_warn(reason)
        self.allow_mutations = False
        self.report_data["mutations_enabled"] = False
        self.report_data["tenant_safety_reason"] = reason
        return False

    def get_booking_id(self, data):
        """Robustly extract booking ID from various response schemas."""
        if not isinstance(data, dict):
            return None
        return data.get("id") or data.get("booking_id") or data.get("_id") or data.get("booking", {}).get("id") or data.get("data", {}).get("id")

    def run(self):
        log_info(f"=== Starting Demo Flow Smoke Test ===")
        log_info(f"Base URL: {self.base_url}")
        log_info(f"Email: {self.email}")
        log_info(f"Mode: {'MUTATING' if self.allow_mutations else 'READ-ONLY'}")

        # Step 1: Login
        method, ep = "POST", "/api/auth/login"
        login_payload = {"email": self.email, "password": self.password}
        if self.hotel_id:
            login_payload["hotel_id"] = self.hotel_id
        if self.username:
            login_payload["username"] = self.username

        resp, lat, err = self._req(method, ep, json=login_payload)

        success, resp = self._log_step("1. Login", method, ep, resp, lat, err, expected_status=[200, 201])
        if success:
            data = resp.json()
            self.token = data.get("access_token")
            self.tenant_id = data.get("tenant_id")
            self.check_tenant_safety(data)
            self.report_data["mode"] = "mutating" if self.allow_mutations else "read-only"
        else:
            log_error("Login failed. Cannot proceed.")
            self.save_report()
            sys.exit(1)

        # Step 2: Dashboard
        method, ep = "GET", "/api/rms/dashboard-kpis"
        resp, lat, err = self._req(method, ep)
        self._log_step("2. Dashboard KPIs", method, ep, resp, lat, err)

        # Step 3: Arrival list
        method, ep = "GET", "/api/pms/bookings?status=arrival"
        resp, lat, err = self._req(method, ep)
        success, resp = self._log_step("3. Arrival List", method, ep, resp, lat, err)

        # Read-only fallback for Booking details
        if success and not self.allow_mutations:
            try:
                bookings = extract_items(resp.json())
                if bookings and len(bookings) > 0:
                    self.booking_id = self.get_booking_id(bookings[0])
            except Exception:
                pass

        if not self.allow_mutations:
            log_info("Read-only mode active. Mutating steps will be SKIPPED.")
            self._skip_step("4. Create Booking", "Read-only mode")

            # Step 5: Booking Details (Read-only execution if booking found)
            if self.booking_id:
                method, ep = "GET", f"/api/pms/bookings/{self.booking_id}"
                resp, lat, err = self._req(method, ep)
                self._log_step("5. Booking Details", method, ep, resp, lat, err)
            else:
                self._skip_step("5. Booking Details", "No booking available from arrival list")

            self._skip_step("6. Check-in", "Read-only mode")
            self._skip_step("7. Room Status Update", "Read-only mode")
            self._skip_step("8. Folio Charge", "Read-only mode")
            self._skip_step("9. Folio Payment", "Read-only mode")
            self._skip_step("10. Room Move", "Read-only mode")
            self._skip_step("11. Housekeeping Task", "Read-only mode")
            self._skip_step("12. Check-out", "Read-only mode")
        else:
            # Pre-requisite: Find a room to use for booking and status
            resp, lat, err = self._req("GET", "/api/pms/rooms?limit=5")
            if resp and resp.status_code == 200:
                try:
                    rooms = extract_items(resp.json())
                    if len(rooms) > 0:
                        self.room_id = rooms[0].get("id")
                    if len(rooms) > 1:
                        self.target_room_id = rooms[1].get("id")
                except Exception:
                    pass

            # Step 4: Create booking
            if not self.room_id:
                self._skip_step("4. Create Booking", "Missing room_id from prerequisite")
            else:
                method, ep = "POST", "/api/pms/quick-booking"
                booking_data = {
                    "guest_name": f"SMOKE_DEMO_{self.ts_id}",
                    "check_in": "2026-07-01T14:00:00Z",
                    "check_out": "2026-07-05T12:00:00Z",
                    "room_id": self.room_id,
                    "total_amount": 100.0,
                    "adults": 1,
                    "children": 0,
                }
                resp, lat, err = self._req(method, ep, json=booking_data)
                success, resp = self._log_step("4. Create Booking", method, ep, resp, lat, err, expected_status=[200, 201])
                if success:
                    self.booking_id = self.get_booking_id(resp.json())

            # Step 5: Booking details
            if self.booking_id:
                method, ep = "GET", f"/api/pms/bookings/{self.booking_id}"
                resp, lat, err = self._req(method, ep)
                success, resp = self._log_step("5. Booking Details", method, ep, resp, lat, err)
                if success:
                    self.folio_id = resp.json().get("folio_id") or self.booking_id
            else:
                self._skip_step("5. Booking Details", "Missing booking_id from previous step")

            # Step 6: Check-in
            if self.booking_id:
                method, ep = "POST", f"/api/pms/bookings/{self.booking_id}/check-in"
                resp, lat, err = self._req(method, ep)
                self._log_step("6. Check-in", method, ep, resp, lat, err)
            else:
                self._skip_step("6. Check-in", "Missing booking_id")

            # Step 7: Update room status
            if self.room_id:
                method, ep = "POST", f"/api/housekeeping/rooms/{self.room_id}/status"
                resp, lat, err = self._req(method, ep, json={"status": "CLEAN"})
                self._log_step("7. Room Status Update", method, ep, resp, lat, err)
            else:
                self._skip_step("7. Room Status Update", "Missing room_id")

            # Step 8: Folio charge
            if self.folio_id:
                method, ep = "POST", f"/api/folio/{self.folio_id}/charges"
                resp, lat, err = self._req(method, ep, json={"amount": 50, "description": "Minibar"})
                self._log_step("8. Folio Charge", method, ep, resp, lat, err, expected_status=[200, 201])
            else:
                self._skip_step("8. Folio Charge", "Missing folio_id")

            # Step 9: Payment
            if self.folio_id:
                method, ep = "POST", f"/api/folio/{self.folio_id}/payments"
                resp, lat, err = self._req(method, ep, json={"amount": 50, "method": "CREDIT_CARD"})
                self._log_step("9. Folio Payment", method, ep, resp, lat, err, expected_status=[200, 201])
            else:
                self._skip_step("9. Folio Payment", "Missing folio_id")

            # Step 10: Room move
            if self.booking_id and self.room_id and self.target_room_id:
                method, ep = "POST", f"/api/pms/bookings/{self.booking_id}/room-move"
                resp, lat, err = self._req(method, ep, json={"new_room_id": self.target_room_id})
                self._log_step("10. Room Move", method, ep, resp, lat, err)
            else:
                self._skip_step("10. Room Move", "Missing booking_id or target_room_id")

            # Step 11: Housekeeping task
            if self.room_id:
                method, ep = "POST", "/api/housekeeping/tasks"
                resp, lat, err = self._req(method, ep, json={"room_id": self.room_id, "task_type": "CLEANING"})
                self._log_step("11. Housekeeping Task", method, ep, resp, lat, err, expected_status=[200, 201])
            else:
                self._skip_step("11. Housekeeping Task", "Missing room_id")

            # Step 12: Check-out
            if self.booking_id:
                method, ep = "POST", f"/api/pms/bookings/{self.booking_id}/check-out"
                resp, lat, err = self._req(method, ep)
                self._log_step("12. Check-out", method, ep, resp, lat, err)
            else:
                self._skip_step("12. Check-out", "Missing booking_id")

        # Step 13: Night Audit / Daily Resume (Read-only)
        method, ep = "GET", "/api/trial-balance"
        resp, lat, err = self._req(method, ep)
        if resp and resp.status_code != 404:
            self._log_step("13. Night Audit / Daily Resume", method, ep, resp, lat, err)
        else:
            # Fallback
            ep_fallback = "/api/logs/night-audit?limit=1"
            resp2, lat2, err2 = self._req(method, ep_fallback)
            if resp2 and resp2.status_code != 404:
                self._log_step("13. Night Audit / Daily Resume", method, ep_fallback, resp2, lat2, err2)
            else:
                self._skip_step("13. Night Audit / Daily Resume", "Neither /api/trial-balance nor /api/logs/night-audit endpoints found (404).")

        log_info("=== Demo Flow Test Complete ===")
        self.save_report()


if __name__ == "__main__":
    args = parse_args()
    test = DemoSmokeTest(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        allow_mutations=args.allow_mutations,
        origin=args.origin,
        hotel_id=args.hotel_id,
        username=args.username,
        force_local_mutations=args.force_local_mutations,
    )
    test.run()
