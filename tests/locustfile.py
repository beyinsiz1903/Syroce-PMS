"""Syroce PMS - Kapsamli Yuk Testi
Kullanim: locust -f tests/locustfile.py --host=http://localhost:8001 --headless -u 50 -r 5 -t 2m --html=load_test_report.html
"""
from locust import HttpUser, task, between, events, tag
from datetime import date, timedelta
import json
import random
import time
import logging

logger = logging.getLogger(__name__)

USERS = {
    "admin": {"email": "demo@hotel.com", "password": "demo123"},
    "frontdesk": {"email": "frontdesk@hotel.com", "password": "staff123"},
    "housekeeping": {"email": "housekeeping@hotel.com", "password": "staff123"},
    "finance": {"email": "finance@hotel.com", "password": "staff123"},
    "sales": {"email": "sales@hotel.com", "password": "staff123"},
}

TODAY = date.today().isoformat()
NEXT_WEEK = (date.today() + timedelta(days=7)).isoformat()
MONTH_START = date(date.today().year, date.today().month, 1).isoformat()
MONTH_END = (date(date.today().year, date.today().month + 1, 1) - timedelta(days=1)).isoformat() if date.today().month < 12 else f"{date.today().year}-12-31"


class PMSAdminUser(HttpUser):
    """Admin kullanici - tum modullere erisir, en yogun senaryo"""
    weight = 3
    wait_time = between(0.5, 2)
    token = None

    def on_start(self):
        cred = USERS["admin"]
        resp = self.client.post("/api/auth/login", json=cred)
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")
        else:
            logger.error(f"Admin login failed: {resp.status_code}")

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # --- Dashboard & Core ---
    @tag("dashboard")
    @task(10)
    def dashboard(self):
        self.client.get("/api/pms/dashboard", headers=self._h(), name="/api/pms/dashboard")

    @tag("rooms")
    @task(8)
    def list_rooms(self):
        self.client.get("/api/pms/rooms?limit=100", headers=self._h(), name="/api/pms/rooms")

    @tag("rooms")
    @task(3)
    def rooms_available(self):
        self.client.get("/api/pms/rooms?status=available", headers=self._h(), name="/api/pms/rooms?status=available")

    @tag("bookings")
    @task(8)
    def list_bookings(self):
        self.client.get(f"/api/pms/bookings?start_date={TODAY}&end_date={NEXT_WEEK}&limit=200", headers=self._h(), name="/api/pms/bookings")

    @tag("guests")
    @task(6)
    def list_guests(self):
        self.client.get("/api/pms/guests?limit=100", headers=self._h(), name="/api/pms/guests")

    @tag("guests")
    @task(2)
    def search_guests(self):
        self.client.get("/api/pms/guests?search=ahmet", headers=self._h(), name="/api/pms/guests?search")

    @tag("companies")
    @task(3)
    def list_companies(self):
        self.client.get("/api/companies?limit=50", headers=self._h(), name="/api/companies")

    # --- Front Desk ---
    @tag("frontdesk")
    @task(6)
    def frontdesk_arrivals(self):
        self.client.get("/api/frontdesk/arrivals", headers=self._h(), name="/api/frontdesk/arrivals")

    @tag("frontdesk")
    @task(5)
    def frontdesk_departures(self):
        self.client.get("/api/frontdesk/departures", headers=self._h(), name="/api/frontdesk/departures")

    @tag("frontdesk")
    @task(5)
    def frontdesk_inhouse(self):
        self.client.get("/api/frontdesk/inhouse", headers=self._h(), name="/api/frontdesk/inhouse")

    # --- Housekeeping ---
    @tag("housekeeping")
    @task(5)
    def hk_tasks(self):
        self.client.get("/api/housekeeping/tasks", headers=self._h(), name="/api/housekeeping/tasks")

    @tag("housekeeping")
    @task(4)
    def hk_room_status(self):
        self.client.get("/api/housekeeping/room-status", headers=self._h(), name="/api/housekeeping/room-status")

    @tag("housekeeping")
    @task(2)
    def hk_due_out(self):
        self.client.get("/api/housekeeping/due-out", headers=self._h(), name="/api/housekeeping/due-out")

    @tag("housekeeping")
    @task(2)
    def hk_stayovers(self):
        self.client.get("/api/housekeeping/stayovers", headers=self._h(), name="/api/housekeeping/stayovers")

    # --- Reports ---
    @tag("reports")
    @task(4)
    def report_daily_summary(self):
        self.client.get("/api/reports/daily-summary", headers=self._h(), name="/api/reports/daily-summary")

    @tag("reports")
    @task(3)
    def report_occupancy(self):
        self.client.get(f"/api/reports/occupancy?start_date={MONTH_START}&end_date={MONTH_END}", headers=self._h(), name="/api/reports/occupancy")

    @tag("reports")
    @task(3)
    def report_revenue(self):
        self.client.get(f"/api/reports/revenue?start_date={MONTH_START}&end_date={MONTH_END}", headers=self._h(), name="/api/reports/revenue")

    @tag("reports")
    @task(2)
    def report_forecast(self):
        self.client.get("/api/reports/forecast?days=7", headers=self._h(), name="/api/reports/forecast")

    @tag("reports")
    @task(2)
    def report_daily_flash(self):
        self.client.get("/api/reports/daily-flash", headers=self._h(), name="/api/reports/daily-flash")

    @tag("reports")
    @task(1)
    def report_market_segment(self):
        self.client.get(f"/api/reports/market-segment?start_date={MONTH_START}&end_date={MONTH_END}", headers=self._h(), name="/api/reports/market-segment")

    @tag("reports")
    @task(1)
    def report_company_aging(self):
        self.client.get("/api/reports/company-aging", headers=self._h(), name="/api/reports/company-aging")

    # --- Channel Manager ---
    @tag("channel")
    @task(2)
    def channel_ota(self):
        self.client.get("/api/channel-manager/ota-reservations?status=pending", headers=self._h(), name="/api/channel-manager/ota-reservations")

    @tag("channel")
    @task(2)
    def channel_exceptions(self):
        self.client.get("/api/channel-manager/exceptions?status=pending", headers=self._h(), name="/api/channel-manager/exceptions")

    @tag("rms")
    @task(2)
    def rms_suggestions(self):
        self.client.get("/api/rms/suggestions?status=pending", headers=self._h(), name="/api/rms/suggestions")

    # --- AI ---
    @tag("ai")
    @task(2)
    def ai_occupancy(self):
        self.client.get("/api/ai/pms/occupancy-prediction", headers=self._h(), name="/api/ai/occupancy-prediction")

    @tag("ai")
    @task(1)
    def ai_patterns(self):
        self.client.get("/api/ai/pms/guest-patterns", headers=self._h(), name="/api/ai/guest-patterns")

    # --- Rate Plans ---
    @tag("rates")
    @task(2)
    def rate_plans(self):
        self.client.get("/api/rates/rate-plans", headers=self._h(), name="/api/rates/rate-plans")

    @tag("rates")
    @task(1)
    def packages(self):
        self.client.get("/api/rates/packages", headers=self._h(), name="/api/rates/packages")

    # --- System ---
    @tag("system")
    @task(1)
    def audit_logs(self):
        self.client.get("/api/audit-logs?limit=20", headers=self._h(), name="/api/audit-logs")

    @tag("system")
    @task(1)
    def health(self):
        self.client.get("/health", name="/health")


class FrontDeskUser(HttpUser):
    """On buro kullanicisi - check-in/out yogunluklu"""
    weight = 3
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        cred = USERS["frontdesk"]
        resp = self.client.post("/api/auth/login", json=cred)
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @tag("frontdesk")
    @task(10)
    def arrivals(self):
        self.client.get("/api/frontdesk/arrivals", headers=self._h(), name="/api/frontdesk/arrivals")

    @tag("frontdesk")
    @task(8)
    def departures(self):
        self.client.get("/api/frontdesk/departures", headers=self._h(), name="/api/frontdesk/departures")

    @tag("frontdesk")
    @task(8)
    def inhouse(self):
        self.client.get("/api/frontdesk/inhouse", headers=self._h(), name="/api/frontdesk/inhouse")

    @tag("rooms")
    @task(6)
    def rooms(self):
        self.client.get("/api/pms/rooms?limit=100", headers=self._h(), name="/api/pms/rooms")

    @tag("bookings")
    @task(6)
    def bookings(self):
        self.client.get(f"/api/pms/bookings?start_date={TODAY}&end_date={NEXT_WEEK}&limit=200", headers=self._h(), name="/api/pms/bookings")

    @tag("guests")
    @task(5)
    def guests(self):
        self.client.get("/api/pms/guests?limit=100", headers=self._h(), name="/api/pms/guests")

    @tag("dashboard")
    @task(3)
    def dashboard(self):
        self.client.get("/api/pms/dashboard", headers=self._h(), name="/api/pms/dashboard")


class HousekeepingUser(HttpUser):
    """Kat hizmetleri kullanicisi"""
    weight = 2
    wait_time = between(2, 5)
    token = None

    def on_start(self):
        cred = USERS["housekeeping"]
        resp = self.client.post("/api/auth/login", json=cred)
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @tag("housekeeping")
    @task(10)
    def hk_task_list(self):
        self.client.get("/api/housekeeping/tasks", headers=self._h(), name="/api/housekeeping/tasks")

    @tag("housekeeping")
    @task(8)
    def room_status(self):
        self.client.get("/api/housekeeping/room-status", headers=self._h(), name="/api/housekeeping/room-status")

    @tag("housekeeping")
    @task(5)
    def due_out(self):
        self.client.get("/api/housekeeping/due-out", headers=self._h(), name="/api/housekeeping/due-out")

    @tag("housekeeping")
    @task(5)
    def stayovers(self):
        self.client.get("/api/housekeeping/stayovers", headers=self._h(), name="/api/housekeeping/stayovers")

    @tag("housekeeping")
    @task(4)
    def arrivals(self):
        self.client.get("/api/housekeeping/arrivals", headers=self._h(), name="/api/housekeeping/arrivals")

    @tag("rooms")
    @task(3)
    def rooms(self):
        self.client.get("/api/pms/rooms?limit=100", headers=self._h(), name="/api/pms/rooms")


class FinanceUser(HttpUser):
    """Finans kullanicisi - rapor yogunluklu"""
    weight = 1
    wait_time = between(3, 8)
    token = None

    def on_start(self):
        cred = USERS["finance"]
        resp = self.client.post("/api/auth/login", json=cred)
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @tag("reports")
    @task(8)
    def revenue_report(self):
        self.client.get(f"/api/reports/revenue?start_date={MONTH_START}&end_date={MONTH_END}", headers=self._h(), name="/api/reports/revenue")

    @tag("reports")
    @task(6)
    def occupancy_report(self):
        self.client.get(f"/api/reports/occupancy?start_date={MONTH_START}&end_date={MONTH_END}", headers=self._h(), name="/api/reports/occupancy")

    @tag("reports")
    @task(5)
    def daily_flash(self):
        self.client.get("/api/reports/daily-flash", headers=self._h(), name="/api/reports/daily-flash")

    @tag("reports")
    @task(4)
    def daily_summary(self):
        self.client.get("/api/reports/daily-summary", headers=self._h(), name="/api/reports/daily-summary")

    @tag("reports")
    @task(3)
    def forecast_30(self):
        self.client.get("/api/reports/forecast?days=30", headers=self._h(), name="/api/reports/forecast?days=30")

    @tag("reports")
    @task(3)
    def company_aging(self):
        self.client.get("/api/reports/company-aging", headers=self._h(), name="/api/reports/company-aging")

    @tag("reports")
    @task(2)
    def hk_efficiency(self):
        self.client.get(f"/api/reports/housekeeping-efficiency?start_date={MONTH_START}&end_date={MONTH_END}", headers=self._h(), name="/api/reports/hk-efficiency")

    @tag("reports")
    @task(2)
    def market_segment(self):
        self.client.get(f"/api/reports/market-segment?start_date={MONTH_START}&end_date={MONTH_END}", headers=self._h(), name="/api/reports/market-segment")

    @tag("dashboard")
    @task(3)
    def dashboard(self):
        self.client.get("/api/pms/dashboard", headers=self._h(), name="/api/pms/dashboard")
