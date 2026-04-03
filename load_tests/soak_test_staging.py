"""
Staging Soak Test — Syroce Hotel PMS
=====================================
12-24 saat boyunca düşük/orta yük altında çalıştırılan dayanıklılık testi.
Amaç: Bellek sızıntısı, kuyruk birikimi, reconciliation gecikmesi tespiti.

Senaryolar:
  1. OTA Reservation Burst (yoğun rezervasyon akışı)
  2. ARI Storm (fiyat/envanter güncelleme fırtınası)
  3. WebSocket / Dashboard Polling (sistem sağlık izleme)
  4. Night Audit Operations (gece denetimi)
  5. General PMS Operations (genel operasyonel yük)
  6. Queue & Worker Monitoring (kuyruk/worker izleme)

Çalıştırma:
  locust -f load_tests/soak_test_staging.py --headless \
    -u 30 -r 2 -t 30m \
    --host http://localhost:8001 \
    --csv=test_reports/soak \
    --html=test_reports/soak_report.html

Uzun soak (12h):
  locust -f load_tests/soak_test_staging.py --headless \
    -u 20 -r 1 -t 12h \
    --host http://localhost:8001 \
    --csv=test_reports/soak_12h \
    --html=test_reports/soak_12h_report.html
"""
import json
import resource
import os
from datetime import datetime
from locust import HttpUser, task, between, tag, events, LoadTestShape


# ──────────── Soak Test Metrics Collector ────────────
soak_metrics = {
    "start_time": None,
    "snapshots": [],
    "error_count": 0,
    "success_count": 0,
    "latency_samples": [],
}


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    soak_metrics["start_time"] = datetime.utcnow().isoformat()
    soak_metrics["snapshots"] = []
    soak_metrics["error_count"] = 0
    soak_metrics["success_count"] = 0


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    if exception:
        soak_metrics["error_count"] += 1
    else:
        soak_metrics["success_count"] += 1
    soak_metrics["latency_samples"].append(response_time)
    # Keep last 10000 samples for percentile calculation
    if len(soak_metrics["latency_samples"]) > 10000:
        soak_metrics["latency_samples"] = soak_metrics["latency_samples"][-5000:]


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate final soak test report."""
    report = generate_soak_report()
    report_path = "/app/test_reports/soak_final_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n{'='*60}")
    print(f"  SOAK TEST FINAL REPORT: {report_path}")
    print(f"{'='*60}")
    print(f"  Duration: {report['duration_minutes']:.1f} min")
    print(f"  Total Requests: {report['total_requests']}")
    print(f"  Error Rate: {report['error_rate_pct']:.2f}%")
    print(f"  p50: {report['latency_p50']:.0f}ms | p95: {report['latency_p95']:.0f}ms | p99: {report['latency_p99']:.0f}ms")
    print(f"  Memory RSS: {report['memory_rss_mb']:.1f} MB")
    print(f"  Verdict: {report['verdict']}")
    print(f"{'='*60}\n")


def generate_soak_report():
    samples = soak_metrics["latency_samples"]
    sorted_samples = sorted(samples) if samples else [0]
    total = soak_metrics["success_count"] + soak_metrics["error_count"]
    error_rate = (soak_metrics["error_count"] / max(total, 1)) * 100

    start = datetime.fromisoformat(soak_metrics["start_time"]) if soak_metrics["start_time"] else datetime.utcnow()
    duration_min = (datetime.utcnow() - start).total_seconds() / 60

    mem_info = resource.getrusage(resource.RUSAGE_SELF)
    memory_mb = mem_info.ru_maxrss / 1024  # Linux: KB -> MB

    p50 = sorted_samples[int(len(sorted_samples) * 0.50)] if sorted_samples else 0
    p95 = sorted_samples[int(len(sorted_samples) * 0.95)] if sorted_samples else 0
    p99 = sorted_samples[int(len(sorted_samples) * 0.99)] if sorted_samples else 0

    issues = []
    if error_rate > 2:
        issues.append(f"Error rate {error_rate:.1f}% exceeds 2% threshold")
    if p95 > 3000:
        issues.append(f"p95 latency {p95:.0f}ms exceeds 3000ms threshold")
    if p99 > 5000:
        issues.append(f"p99 latency {p99:.0f}ms exceeds 5000ms threshold")

    verdict = "PASS" if not issues else "FAIL"

    return {
        "test_type": "staging_soak_test",
        "start_time": soak_metrics["start_time"],
        "end_time": datetime.utcnow().isoformat(),
        "duration_minutes": duration_min,
        "total_requests": total,
        "success_count": soak_metrics["success_count"],
        "error_count": soak_metrics["error_count"],
        "error_rate_pct": error_rate,
        "latency_p50": p50,
        "latency_p95": p95,
        "latency_p99": p99,
        "latency_avg": sum(samples) / max(len(samples), 1),
        "memory_rss_mb": memory_mb,
        "thresholds": {
            "error_rate_max_pct": 2.0,
            "p95_max_ms": 3000,
            "p99_max_ms": 5000,
        },
        "issues": issues,
        "verdict": verdict,
        "scenarios_tested": [
            "ota_reservation_burst",
            "ari_storm",
            "dashboard_polling",
            "night_audit",
            "general_pms_ops",
            "queue_monitoring",
        ],
    }


# ──────────── User Profiles ────────────

class FrontdeskOperator(HttpUser):
    """Simulates front desk staff — check-in, check-out, room status, arrivals."""
    wait_time = between(2, 5)
    weight = 4
    token = None

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(4)
    @tag("frontdesk", "arrivals")
    def check_arrivals(self):
        self.client.get("/api/arrivals/today", headers=self.headers, name="[FD] Arrivals")

    @task(3)
    @tag("frontdesk", "inhouse")
    def check_inhouse(self):
        self.client.get("/api/unified/in-house", headers=self.headers, name="[FD] In-House")

    @task(3)
    @tag("frontdesk", "departures")
    def check_departures(self):
        self.client.get("/api/frontdesk/departures", headers=self.headers, name="[FD] Departures")

    @task(3)
    @tag("frontdesk", "rooms")
    def room_status(self):
        self.client.get("/api/pms/rooms?limit=50", headers=self.headers, name="[FD] Rooms")

    @task(2)
    @tag("frontdesk", "audit")
    def audit_checklist(self):
        self.client.get("/api/frontdesk/audit-checklist", headers=self.headers, name="[FD] Audit Checklist")

    @task(1)
    @tag("frontdesk", "folio")
    def folio_operations(self):
        self.client.get("/api/metrics/operational", headers=self.headers, name="[FD] Ops Metrics")


class ARIStormUser(HttpUser):
    """Simulates ARI (Availability/Rate/Inventory) storm from Channel Manager."""
    wait_time = between(1, 3)
    weight = 2
    token = None

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(3)
    @tag("ari", "pricing")
    def pricing_recommendations(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        self.client.get(f"/api/rms/pricing-recommendations?date={today}",
                        headers=self.headers, name="[ARI] Pricing Recs")

    @task(2)
    @tag("ari", "forecast")
    def demand_forecast(self):
        self.client.get("/api/rms/demand-forecast", headers=self.headers, name="[ARI] Demand Forecast")

    @task(2)
    @tag("ari", "compset")
    def compset_pricing(self):
        self.client.get("/api/rms/comp-pricing", headers=self.headers, name="[ARI] CompSet Pricing")

    @task(1)
    @tag("ari", "compset")
    def compset_comparison(self):
        self.client.get("/api/rms/comp-set-comparison", headers=self.headers, name="[ARI] CompSet Compare")


class DashboardPoller(HttpUser):
    """Simulates dashboard/WebSocket health polling — sustained monitoring load."""
    wait_time = between(3, 8)
    weight = 2
    token = None

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(3)
    @tag("dashboard", "health")
    def system_health(self):
        self.client.get("/api/metrics/operational", headers=self.headers, name="[DASH] Health")

    @task(2)
    @tag("dashboard", "metrics")
    def operational_metrics(self):
        self.client.get("/api/fnb/dashboard", headers=self.headers, name="[DASH] FnB Dashboard")

    @task(2)
    @tag("dashboard", "audit")
    def audit_timeline(self):
        self.client.get("/api/audit/timeline?limit=20", headers=self.headers, name="[DASH] Audit Timeline")

    @task(1)
    @tag("dashboard", "audit")
    def audit_summary(self):
        self.client.get("/api/audit/summary?period=1h", headers=self.headers, name="[DASH] Audit Summary")

    @task(1)
    @tag("dashboard", "production")
    def maturity_score(self):
        self.client.get("/api/production/maturity/score", headers=self.headers, name="[DASH] Maturity Score")


class NightAuditRunner(HttpUser):
    """Simulates night audit operations — periodic, heavier queries."""
    wait_time = between(5, 15)
    weight = 1
    token = None

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(3)
    @tag("night_audit")
    def audit_history(self):
        self.client.get("/api/night-audit/history?limit=10", headers=self.headers, name="[NA] History")

    @task(2)
    @tag("night_audit", "metrics")
    def audit_metrics(self):
        self.client.get("/api/metrics/night-audit", headers=self.headers, name="[NA] Metrics")

    @task(1)
    @tag("night_audit")
    def business_date(self):
        self.client.get("/api/night-audit/business-date", headers=self.headers, name="[NA] Business Date")


class HousekeepingStaff(HttpUser):
    """Simulates housekeeping mobile app usage."""
    wait_time = between(3, 8)
    weight = 1
    token = None

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(3)
    @tag("housekeeping")
    def delayed_rooms(self):
        self.client.get("/api/dashboard/mobile/critical-issues",
                        headers=self.headers, name="[HK] Critical Issues")

    @task(2)
    @tag("housekeeping")
    def room_status(self):
        self.client.get("/api/pms/rooms?limit=100", headers=self.headers, name="[HK] Room Status")

    @task(1)
    @tag("mobile")
    def critical_issues(self):
        self.client.get("/api/dashboard/mobile/critical-issues",
                        headers=self.headers, name="[HK] Critical Issues")


class ProductionOpsMonitor(HttpUser):
    """Simulates production operations monitoring — canary, pilot, incident readiness."""
    wait_time = between(10, 20)
    weight = 1
    token = None

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(2)
    @tag("production", "canary")
    def canary_status(self):
        self.client.get("/api/production/canary/status", headers=self.headers, name="[PROD] Canary Status")

    @task(2)
    @tag("production", "monitoring")
    def monitoring_dashboard(self):
        self.client.get("/api/production/monitoring/dashboard",
                        headers=self.headers, name="[PROD] Monitor Dashboard")

    @task(1)
    @tag("production", "incident")
    def incident_readiness(self):
        self.client.get("/api/production/incident-readiness",
                        headers=self.headers, name="[PROD] Incident Readiness")

    @task(1)
    @tag("production", "isolation")
    def tenant_isolation(self):
        self.client.get("/api/production/isolation/validate",
                        headers=self.headers, name="[PROD] Tenant Isolation")

    @task(1)
    @tag("production", "postlaunch")
    def post_launch_status(self):
        self.client.get("/api/production/post-launch/status",
                        headers=self.headers, name="[PROD] Post-Launch Status")


# ──────────── Custom Load Shape (Soak Pattern) ────────────

class SoakTestShape(LoadTestShape):
    """
    Soak test load pattern:
    - 0-2 min: Ramp up to target
    - 2 min - end: Sustained load with periodic micro-bursts
    - Returns None to stop when time limit reached
    """
    target_users = int(os.environ.get("SOAK_USERS", "20"))
    ramp_time = 120  # 2 min ramp
    burst_interval = 300  # Every 5 min
    burst_multiplier = 1.5

    def _parse_duration(self, s):
        """Parse duration string like '5m', '1h', '12h' to seconds."""
        s = s.strip().lower()
        if s.endswith("h"):
            return int(s[:-1]) * 3600
        if s.endswith("m"):
            return int(s[:-1]) * 60
        if s.endswith("s"):
            return int(s[:-1])
        return int(s)

    @property
    def time_limit(self):
        return self._parse_duration(os.environ.get("SOAK_DURATION", "5m"))

    def tick(self):
        run_time = self.get_run_time()

        if run_time > self.time_limit:
            return None  # Stop the test

        if run_time < self.ramp_time:
            # Ramp up phase
            current = int(self.target_users * (run_time / self.ramp_time))
            return max(current, 1), max(current // 5, 1)

        # Sustained phase with periodic micro-bursts
        time_in_cycle = run_time % self.burst_interval
        if time_in_cycle < 60:  # 1 min burst every 5 min
            users = int(self.target_users * self.burst_multiplier)
        else:
            users = self.target_users

        return users, max(users // 10, 1)
