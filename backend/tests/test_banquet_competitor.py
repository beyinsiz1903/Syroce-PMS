"""
Banquet Competitor Tests
=========================
T002 doğrulaması: `routers/banquet_competitor.py` içindeki rakip CRUD,
fiyat snapshot CRUD ve pozisyonlama endpoint'lerinin bekleneni döndürdüğünü
test eder.

Entegrasyon stilinde — gerçek backend'e HTTP ile bağlanır.
Çift cleanup'lı: testler kendi yarattıklarını siler. Aynı suite içinde
oluşan kayıtlar pozisyonlama özetinde görünmeli.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


def _create_competitor(headers: dict, **overrides) -> dict:
    """Helper: rakip oluştur, response'u döndür."""
    payload = {
        "name": f"Test Rakip {uuid.uuid4().hex[:8]}",
        "hotel_class": 5,
        "capacity_max": 600,
        "venues": ["Grand Ballroom", "Boardroom A"],
        "notes": "Otomatik test kaydı",
        "active": True,
    }
    payload.update(overrides)
    r = requests.post(f"{BASE_URL}/api/banquet/competitors", json=payload, headers=headers)
    assert r.status_code == 201, f"create failed: {r.status_code} {r.text}"
    return r.json()


def _delete_competitor(headers: dict, comp_id: str) -> None:
    requests.delete(f"{BASE_URL}/api/banquet/competitors/{comp_id}", headers=headers)


class TestBanquetCompetitor:

    def test_create_and_list(self, demo_auth_headers):
        comp = _create_competitor(demo_auth_headers, name="ListTest-A")
        comp_id = comp["id"]
        try:
            r = requests.get(
                f"{BASE_URL}/api/banquet/competitors", headers=demo_auth_headers
            )
            assert r.status_code == 200
            names = [c["name"] for c in r.json().get("competitors", [])]
            assert "ListTest-A" in names
        finally:
            _delete_competitor(demo_auth_headers, comp_id)

    def test_update_competitor(self, demo_auth_headers):
        comp = _create_competitor(demo_auth_headers, name="UpdateTest")
        comp_id = comp["id"]
        try:
            updated = {
                "name": "UpdateTest-Renamed",
                "hotel_class": 4,
                "capacity_max": 300,
                "venues": ["Yeni Salon"],
                "notes": "Güncellendi",
                "active": False,
            }
            r = requests.put(
                f"{BASE_URL}/api/banquet/competitors/{comp_id}",
                json=updated,
                headers=demo_auth_headers,
            )
            assert r.status_code == 200, r.text
            r = requests.get(
                f"{BASE_URL}/api/banquet/competitors", headers=demo_auth_headers
            )
            comps = {c["id"]: c for c in r.json().get("competitors", [])}
            doc = comps.get(comp_id) or {}
            assert doc.get("name") == "UpdateTest-Renamed"
            assert doc.get("hotel_class") == 4
            assert doc.get("active") is False
        finally:
            _delete_competitor(demo_auth_headers, comp_id)

    def test_delete_competitor(self, demo_auth_headers):
        comp = _create_competitor(demo_auth_headers, name="DeleteTest")
        comp_id = comp["id"]
        r = requests.delete(
            f"{BASE_URL}/api/banquet/competitors/{comp_id}",
            headers=demo_auth_headers,
        )
        assert r.status_code == 200
        # Tekrar silmek 404 dönmeli
        r2 = requests.delete(
            f"{BASE_URL}/api/banquet/competitors/{comp_id}",
            headers=demo_auth_headers,
        )
        assert r2.status_code == 404

    def test_rate_snapshots_crud(self, demo_auth_headers):
        comp = _create_competitor(demo_auth_headers, name="RateTest")
        comp_id = comp["id"]
        try:
            rate_payload = {
                "event_type": "wedding",
                "season": "high",
                "per_pax_price": 1850.0,
                "currency": "TRY",
                "min_pax": 200,
                "max_pax": 500,
                "package_includes": ["welcome_cocktail", "open_bar_4h"],
                "source": "web",
                "note": "2026 yaz menüsü",
            }
            r = requests.post(
                f"{BASE_URL}/api/banquet/competitors/{comp_id}/rates",
                json=rate_payload,
                headers=demo_auth_headers,
            )
            assert r.status_code == 201, r.text
            rate_id = r.json()["id"]

            # 2. snapshot
            requests.post(
                f"{BASE_URL}/api/banquet/competitors/{comp_id}/rates",
                json={**rate_payload, "per_pax_price": 1950.0, "season": "shoulder"},
                headers=demo_auth_headers,
            )

            r = requests.get(
                f"{BASE_URL}/api/banquet/competitors/{comp_id}/rates",
                headers=demo_auth_headers,
            )
            assert r.status_code == 200
            rates = r.json().get("rates", [])
            assert len(rates) == 2
            # Newest first → ilk pozisyon en son eklenen
            assert rates[0]["per_pax_price"] == 1950.0
            assert rates[1]["per_pax_price"] == 1850.0

            # delete one
            r = requests.delete(
                f"{BASE_URL}/api/banquet/competitors/{comp_id}/rates/{rate_id}",
                headers=demo_auth_headers,
            )
            assert r.status_code == 200
            r = requests.get(
                f"{BASE_URL}/api/banquet/competitors/{comp_id}/rates",
                headers=demo_auth_headers,
            )
            assert len(r.json().get("rates", [])) == 1
        finally:
            _delete_competitor(demo_auth_headers, comp_id)

    def test_positioning_returns_event_type_band(self, demo_auth_headers):
        """En az 2 farklı fiyat ekleyince pozisyonlama satırlarında min/max/avg
        beklenen şekilde olmalı; status 200 dönmeli."""
        comp = _create_competitor(demo_auth_headers, name="PositioningTest")
        comp_id = comp["id"]
        try:
            base = {
                "event_type": "gala",
                "season": "all",
                "currency": "TRY",
                "min_pax": 100,
                "max_pax": 400,
                "source": "test",
            }
            for px in (1000.0, 1500.0, 2000.0):
                requests.post(
                    f"{BASE_URL}/api/banquet/competitors/{comp_id}/rates",
                    json={**base, "per_pax_price": px},
                    headers=demo_auth_headers,
                )

            r = requests.get(
                f"{BASE_URL}/api/banquet/competitor-positioning",
                headers=demo_auth_headers,
            )
            assert r.status_code == 200, r.text
            payload = r.json()
            rows = payload.get("rows", [])
            gala_row = next((r for r in rows if r.get("event_type") == "gala"), None)
            assert gala_row is not None, f"gala row missing: {rows}"
            # Bu suite en az 1000 / 1500 / 2000 ekledi; başka testler de
            # olabilir, ama min ≤ 1000 ve max ≥ 2000 olmalı.
            assert gala_row["competitor_min"] <= 1000.0
            assert gala_row["competitor_max"] >= 2000.0
            assert gala_row["competitor_avg"] > 0
            assert gala_row["competitor_count"] >= 3
            assert "position" in gala_row
        finally:
            _delete_competitor(demo_auth_headers, comp_id)

    def test_unauthenticated_request_blocked(self):
        """Token olmadan competitor list çağrısı 401/403 dönmeli."""
        r = requests.get(f"{BASE_URL}/api/banquet/competitors")
        assert r.status_code in (401, 403), (
            f"unauthenticated should be rejected, got {r.status_code}"
        )
