import requests
import argparse
import sys
import time
import json
import os
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Smoke Test Script for Pilot Demo Flow")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="Base URL of the backend")
    parser.add_argument("--email", type=str, default="info@syroce.com", help="Admin email")
    parser.add_argument("--password", type=str, default="demo123", help="Admin password")
    parser.add_argument("--allow-mutations", action="store_true", help="Allow state-changing (destructive) operations")
    parser.add_argument("--read-only", action="store_true", help="Explicitly mark read-only mode (default if --allow-mutations is omitted)")
    return parser.parse_args()

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
        self.room_id = "101" # Mock room id
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
        
        # Safe response parsing
        resp_summary = ""
        if resp:
            try:
                resp_json = resp.json()
                # Summarize JSON
                resp_summary = json.dumps(resp_json)[:100] + "..." if len(json.dumps(resp_json)) > 100 else json.dumps(resp_json)
            except:
                resp_summary = resp.text[:100] + "..." if len(resp.text) > 100 else resp.text

        is_success = resp and resp.status_code in expected_status
        
        step_result = {
            "step": step_name,
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": lat,
            "success": is_success,
            "response_summary": resp_summary,
            "error_reason": err if err else ("Unexpected Status" if not is_success else None)
        }
        self.report_data["steps"].append(step_result)

        if is_success:
            log_success(f"{step_name} | {method} {endpoint} | Status: {status_code} | {lat}ms")
        else:
            reason = err if err else f"Status {status_code}. Resp: {resp_summary}"
            log_error(f"{step_name} | {method} {endpoint} | FAIL: {reason} | {lat}ms")
            
        return is_success, resp

    def save_report(self):
        os.makedirs("backend/reports", exist_ok=True)
        filename = f"backend/reports/smoke_demo_flow_{self.ts_id}.json"
        with open(filename, "w") as f:
            json.dump(self.report_data, f, indent=2)
        log_info(f"JSON Report saved to {filename}")

    def check_tenant_safety(self):
        if not self.allow_mutations:
            return True
            
        # Optional: Safety check for production data
        # If tenant name doesn't contain 'test', 'demo', or 'pilot', abort mutations
        safe_keywords = ['test', 'demo', 'pilot', 'sandbox', 'local']
        if self.tenant_name and not any(kw in self.tenant_name.lower() for kw in safe_keywords):
            log_warn(f"Tenant '{self.tenant_name}' does not appear to be a test/demo tenant.")
            log_warn("Mutations are disabled for safety. Run against a safe environment.")
            self.allow_mutations = False
        return self.allow_mutations

    def run(self):
        log_info(f"=== Starting Demo Flow Smoke Test ===")
        log_info(f"Base URL: {self.base_url}")
        log_info(f"Email: {self.email}")
        log_info(f"Mode: {'MUTATING' if self.allow_mutations else 'READ-ONLY'}")
        
        # Step 1: Login
        method, ep = "POST", "/api/auth/login"
        resp, lat, err = self._req(method, ep, json={"email": self.email, "password": self.password})
        
        # Redact password in report manually (avoiding it being printed in step summary)
        success, resp = self._log_step("1. Login", method, ep, resp, lat, err, expected_status=[200, 201])
        if success:
            data = resp.json()
            self.token = data.get("access_token")
            # Extract tenant info if present in typical Syroce auth response
            self.tenant_id = data.get("tenant_id", "demo-tenant")
            self.tenant_name = data.get("tenant_name", "Demo Hotel")
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
        self._log_step("3. Arrival List", method, ep, resp, lat, err)

        if not self.allow_mutations:
            log_info("Read-only mode active. Skipping mutating steps (4-12).")
        else:
            # Step 4: Create booking
            method, ep = "POST", "/api/pms/bookings"
            booking_data = {
                "guest_name": f"SMOKE_DEMO_{self.ts_id}",
                "check_in": "2026-07-01",
                "check_out": "2026-07-05",
                "room_type": "DELUXE"
            }
            resp, lat, err = self._req(method, ep, json=booking_data)
            success, resp = self._log_step("4. Create Booking", method, ep, resp, lat, err, expected_status=[200, 201])
            if success:
                self.booking_id = resp.json().get("_id", "mock_id")
            else:
                self.booking_id = f"test_{self.ts_id}"

            # Step 5: Booking details
            method, ep = "GET", f"/api/pms/bookings/{self.booking_id}"
            resp, lat, err = self._req(method, ep)
            success, resp = self._log_step("5. Booking Details", method, ep, resp, lat, err)
            if success:
                self.folio_id = resp.json().get("folio_id", self.booking_id)
            else:
                self.folio_id = self.booking_id

            # Step 6: Check-in
            method, ep = "POST", f"/api/pms/bookings/{self.booking_id}/check-in"
            resp, lat, err = self._req(method, ep)
            self._log_step("6. Check-in", method, ep, resp, lat, err)

            # Step 7: Update room status
            method, ep = "POST", f"/api/housekeeping/rooms/{self.room_id}/status"
            resp, lat, err = self._req(method, ep, json={"status": "CLEAN"})
            self._log_step("7. Room Status Update", method, ep, resp, lat, err)

            # Step 8: Folio charge
            method, ep = "POST", f"/api/folio/{self.folio_id}/charges"
            resp, lat, err = self._req(method, ep, json={"amount": 50, "description": "Minibar"})
            self._log_step("8. Folio Charge", method, ep, resp, lat, err, expected_status=[200, 201])

            # Step 9: Payment
            method, ep = "POST", f"/api/folio/{self.folio_id}/payments"
            resp, lat, err = self._req(method, ep, json={"amount": 50, "method": "CREDIT_CARD"})
            self._log_step("9. Folio Payment", method, ep, resp, lat, err, expected_status=[200, 201])

            # Step 10: Room move
            method, ep = "POST", f"/api/pms/bookings/{self.booking_id}/room-move"
            resp, lat, err = self._req(method, ep, json={"new_room_id": "102"})
            self._log_step("10. Room Move", method, ep, resp, lat, err)

            # Step 11: Housekeeping task
            method, ep = "POST", "/api/housekeeping/tasks"
            resp, lat, err = self._req(method, ep, json={"room_id": "102", "task_type": "CLEANING"})
            self._log_step("11. Housekeeping Task", method, ep, resp, lat, err, expected_status=[200, 201])

            # Step 12: Check-out
            method, ep = "POST", f"/api/pms/bookings/{self.booking_id}/check-out"
            resp, lat, err = self._req(method, ep)
            self._log_step("12. Check-out", method, ep, resp, lat, err)

        # Step 13: Night audit status (Read-only)
        method, ep = "GET", "/api/pms/night_audit/status"
        resp, lat, err = self._req(method, ep)
        self._log_step("13. Night Audit Status", method, ep, resp, lat, err)

        log_info("=== Demo Flow Test Complete ===")
        self.save_report()

if __name__ == "__main__":
    args = parse_args()
    # Explicit mapping for backward compatibility if user passed --read-only instead of nothing
    # By default, argparse store_true is False. 
    allow_mutations = args.allow_mutations
    
    test = DemoSmokeTest(args.base_url, args.email, args.password, allow_mutations)
    test.run()
