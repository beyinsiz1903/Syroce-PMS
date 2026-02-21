"""Locust Load Testing for RoomOps PMS
Kullanimn: locust -f tests/locustfile.py --host=http://localhost:8001
Hedef: 1000+ concurrent kullanici, darbogazlari tespit
"""
from locust import HttpUser, task, between, events
import json
import random
import logging

logger = logging.getLogger(__name__)

# Test credentials
TEST_USERS = [
    {"email": "demo@hotel.com", "password": "demo123"},
    {"email": "admin@demo.com", "password": "demo123"},
    {"email": "manager@demo.com", "password": "demo123"},
    {"email": "frontdesk@demo.com", "password": "demo123"},
]


class HotelPMSUser(HttpUser):
    """Simulates a hotel staff member using the PMS"""
    wait_time = between(1, 5)
    token = None
    tenant_id = None

    def on_start(self):
        """Login on start"""
        user = random.choice(TEST_USERS)
        response = self.client.post(
            "/api/auth/login",
            json=user,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.tenant_id = data.get("tenant", {}).get("id")
        else:
            logger.warning(f"Login failed: {response.status_code}")

    def _headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ---- DASHBOARD ----
    @task(10)
    def view_dashboard(self):
        self.client.get("/api/pms/dashboard", headers=self._headers())

    # ---- ROOMS ----
    @task(8)
    def list_rooms(self):
        self.client.get("/api/pms/rooms", headers=self._headers())

    @task(3)
    def get_room_status(self):
        self.client.get("/api/pms/rooms?status=available", headers=self._headers())

    # ---- BOOKINGS ----
    @task(8)
    def list_bookings(self):
        self.client.get("/api/pms/bookings", headers=self._headers())

    @task(5)
    def list_today_arrivals(self):
        from datetime import date
        today = date.today().isoformat()
        self.client.get(
            f"/api/pms/bookings?start_date={today}&end_date={today}",
            headers=self._headers()
        )

    # ---- GUESTS ----
    @task(6)
    def list_guests(self):
        self.client.get("/api/pms/guests", headers=self._headers())

    @task(3)
    def search_guests(self):
        self.client.get("/api/pms/guests?search=test", headers=self._headers())

    # ---- REPORTS ----
    @task(4)
    def view_reports(self):
        self.client.get("/api/reports/basic-dashboard", headers=self._headers())

    # ---- HOUSEKEEPING ----
    @task(5)
    def view_housekeeping(self):
        self.client.get("/api/housekeeping/tasks", headers=self._headers())

    # ---- INVOICES ----
    @task(3)
    def list_invoices(self):
        self.client.get("/api/invoices", headers=self._headers())

    # ---- SYSTEM ----
    @task(2)
    def system_performance(self):
        self.client.get("/api/system/performance", headers=self._headers())

    @task(1)
    def health_check(self):
        self.client.get("/health")


class FrontDeskUser(HttpUser):
    """Simulates front desk operations (check-in heavy)"""
    wait_time = between(2, 8)
    token = None

    def on_start(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": "frontdesk@demo.com", "password": "demo123"}
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(10)
    def check_arrivals(self):
        self.client.get("/api/pms/bookings", headers=self._headers())

    @task(8)
    def check_room_status(self):
        self.client.get("/api/pms/rooms", headers=self._headers())

    @task(5)
    def view_guest_details(self):
        self.client.get("/api/pms/guests", headers=self._headers())

    @task(3)
    def view_dashboard(self):
        self.client.get("/api/pms/dashboard", headers=self._headers())
