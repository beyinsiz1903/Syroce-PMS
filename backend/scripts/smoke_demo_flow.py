import requests
import argparse
import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Smoke Test Script for Pilot Demo Flow")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="Base URL of the backend")
    parser.add_argument("--email", type=str, default="info@syroce.com", help="Admin email")
    parser.add_argument("--password", type=str, help="Admin password (required unless SMOKE_PASSWORD env is set)")
    parser.add_argument("--allow-mutations", action="store_true", help="Allow state-changing (destructive) operations")
    parser.add_argument("--read-only", action="store_true", help="Explicitly mark read-only mode (default if --allow-mutations is omitted)")
    
    args = parser.parse_args()
    if not args.password:
        args.password = os.environ.get("SMOKE_PASSWORD")
    if not args.password:
        print("ERROR: Password must be provided via --password or SMOKE_PASSWORD environment variable.")
        sys.exit(1)
        
    return args

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

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

class DemoSmokeTest:
    def __init__(self, base_url, email, password, allow_mutations):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.allow_mutations = allow_mutations
        
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
            "mode": "mutating" if self.allow_mutations else "read-only",
            "steps": []
        }

    def _req(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        if self.token:
            headers = kwargs.get("headers", {})
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
        status_code = resp.status_code if resp else "ERROR"
        
        resp_summary = ""
        if resp:
            try:
                resp_json = resp.json()
                safe_json = redact_tokens(resp_json)
                dumped = json.dumps(safe_json)
                resp_summary = dumped[:150] + "..." if len(dumped) > 150 else dumped
            except:
                resp_summary = resp.text[:150] + "..." if len(resp.text) > 150 else resp.text

        is_success = resp and resp.status_code in expected_status
        
        step_result = {
            "step": step_name,
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": lat,
            "success": is_success,
            "response_summary": resp_summary,
            "error_reason": err if err else (f"Unexpected Status {status_code}" if not is_success else None)
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
        self.report_data["steps"].append({
            "step": step_name,
            "success": False,
            "status_code": "SKIPPED",
            "error_reason": reason
        })

    def save_report(self):
        reports_dir = Path(__file__).resolve().parent.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        filename = reports_dir / f"smoke_demo_flow_{self.ts_id}.json"
        with open(filename, "w") as f:
            json.dump(self.report_data, f, indent=2)
        log_info(f"JSON Report saved to {filename}")

    def check_tenant_safety(self):
        if not self.allow_mutations:
            return True
            
        if not self.tenant_name:
            log_warn("Tenant name missing in login response.")
            log_warn("Safety fallback triggered: Mutations disabled.")
            self.allow_mutations = False
            return False

        safe_keywords = ['test', 'demo', 'pilot', 'sandbox', 'local']
        if not any(kw in self.tenant_name.lower() for kw in safe_keywords):
            log_warn(f"Tenant '{self.tenant_name}' does not appear to be a test/demo tenant.")
            log_warn("Mutations are disabled for safety. Run against a safe environment.")
            self.allow_mutations = False
            
        return self.allow_mutations

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
        resp, lat, err = self._req(method, ep, json={"email": self.email, "password": self.password})
        
        success, resp = self._log_step("1. Login", method, ep, resp, lat, err, expected_status=[200, 201])
        if success:
            data = resp.json()
            self.token = data.get("access_token")
            self.tenant_id = data.get("tenant_id")
            self.tenant_name = data.get("tenant_name")
            self.check_tenant_safety()
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
            bookings = resp.json().get("bookings", [])
            if bookings and len(bookings) > 0:
                self.booking_id = self.get_booking_id(bookings[0])

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
                rooms = resp.json().get("rooms", [])
                if len(rooms) > 0:
                    self.room_id = rooms[0].get("id")
                if len(rooms) > 1:
                    self.target_room_id = rooms[1].get("id")

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
                    "children": 0
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

        # Step 13: Night audit status (Read-only)
        method, ep = "GET", "/api/reports/night-audit/status"
        resp, lat, err = self._req(method, ep)
        self._log_step("13. Night Audit Status", method, ep, resp, lat, err)

        log_info("=== Demo Flow Test Complete ===")
        self.save_report()

if __name__ == "__main__":
    args = parse_args()
    test = DemoSmokeTest(args.base_url, args.email, args.password, args.allow_mutations)
    test.run()
