"""
Locust Load Test — Combined PMS Scenarios
Provides Python-based load testing for operational scenarios.
Run: locust -f load_tests/locust_pms.py --headless -u 50 -r 5 -t 60s --host http://localhost:8001
"""
import json
import random
from locust import HttpUser, task, between, tag, events


class PMSUser(HttpUser):
    """Simulates a PMS operator performing mixed operational tasks."""
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(3)
    @tag("frontdesk", "booking")
    def check_arrivals(self):
        self.client.get("/api/arrivals/today", headers=self.headers, name="Arrivals Today")

    @task(3)
    @tag("frontdesk", "booking")
    def check_inhouse(self):
        self.client.get("/api/unified/in-house", headers=self.headers, name="In-House Guests")

    @task(2)
    @tag("rooms")
    def room_status(self):
        self.client.get("/api/pms/rooms?limit=50", headers=self.headers, name="Room Status")

    @task(2)
    @tag("dashboard", "metrics")
    def dashboard_health(self):
        self.client.get("/api/system-health/normalized/admin", headers=self.headers, name="Dashboard Health")

    @task(1)
    @tag("night_audit")
    def night_audit_history(self):
        self.client.get("/api/night-audit/history?limit=5", headers=self.headers, name="NA History")

    @task(1)
    @tag("night_audit", "metrics")
    def night_audit_metrics(self):
        self.client.get("/api/metrics/night-audit", headers=self.headers, name="NA Metrics")

    @task(2)
    @tag("audit")
    def audit_summary(self):
        self.client.get("/api/audit/summary?period=24h", headers=self.headers, name="Audit Summary")

    @task(1)
    @tag("audit")
    def audit_timeline(self):
        self.client.get("/api/audit/timeline?limit=20", headers=self.headers, name="Audit Timeline")

    @task(2)
    @tag("metrics")
    def operational_metrics(self):
        self.client.get("/api/metrics/operational", headers=self.headers, name="Ops Metrics")

    @task(2)
    @tag("pos")
    def pos_dashboard(self):
        self.client.get("/api/fnb/dashboard", headers=self.headers, name="FnB Dashboard")

    @task(1)
    @tag("pos")
    def pos_active_orders(self):
        self.client.get("/api/pos/mobile/active-orders", headers=self.headers, name="Active Orders")

    @task(1)
    @tag("rms")
    def pricing_recs(self):
        self.client.get("/api/rms/demand-forecast", headers=self.headers, name="Demand Forecast")

    @task(1)
    @tag("mobile")
    def mobile_critical(self):
        self.client.get("/api/dashboard/mobile/critical-issues", headers=self.headers, name="Mobile Critical")

    @task(1)
    @tag("housekeeping")
    def hk_delayed(self):
        self.client.get("/api/housekeeping/mobile/sla-delayed-rooms", headers=self.headers, name="HK Delayed")


class CheckoutSurge(HttpUser):
    """Simulates morning checkout surge."""
    wait_time = between(0.5, 1.5)
    token = None
    weight = 2

    def on_start(self):
        res = self.client.post("/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123",
        })
        if res.status_code == 200:
            self.token = res.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(4)
    @tag("checkout")
    def departures(self):
        self.client.get("/api/departures/today", headers=self.headers, name="Departures Today")

    @task(3)
    @tag("checkout", "folio")
    def audit_checklist(self):
        self.client.get("/api/frontdesk/audit-checklist", headers=self.headers, name="Audit Checklist")

    @task(2)
    @tag("checkout", "rooms")
    def room_status(self):
        self.client.get("/api/pms/rooms?limit=100", headers=self.headers, name="Rooms [Checkout]")

    @task(1)
    @tag("checkout", "metrics")
    def dashboard(self):
        self.client.get("/api/metrics/operational", headers=self.headers, name="Ops Metrics [Checkout]")
