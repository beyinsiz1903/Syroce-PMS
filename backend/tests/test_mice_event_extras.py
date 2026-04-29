"""
MICE Event Extras Tests
========================
T001 doğrulaması: EventIn modeline eklenen opsiyonel alanların
(`technical_requirements`, `staff_assignments`, `entertainment`) create/update
round-trip ettiğini ve geriye uyumlu kaldığını (alanlar gönderilmediğinde
event'in normal yaratılabildiğini) test eder. Ayrıca BEO çıktısında
göründüğünü doğrular.

Entegrasyon stilinde — gerçek backend'e HTTP ile bağlanır
(conftest.py:demo_auth_headers).
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


def _make_event_payload(
    *,
    name: str,
    with_extras: bool,
) -> dict:
    today = date.today()
    payload = {
        "name": name,
        "client_name": "Test Müşteri A.Ş.",
        "client_email": "test@example.com",
        "event_type": "meeting",
        "status": "lead",
        "expected_pax": 50,
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=1)).isoformat(),
        "space_bookings": [],
        "resources": [],
        "agenda": [],
        "payment_schedule": [],
        "notes": "Otomatik test event'i",
    }
    if with_extras:
        payload["technical_requirements"] = {
            "projector": True,
            "screen": True,
            "microphone_wired": 2,
            "microphone_wireless": 1,
            "sound_system": True,
            "stage": False,
            "lighting": True,
            "livestream": False,
            "internet_mbps": 100,
            "translation_booths": 0,
            "notes": "Sahne ışığı yok, projeksiyon HDMI",
        }
        payload["staff_assignments"] = [
            {"role": "host", "name": "Ayşe Yılmaz", "notes": "Ana sunucu"},
            {"role": "technician", "name": "Mehmet Kaya"},
            {"role": "server", "name": "Coffee break ekibi (4 kişi)"},
        ]
        payload["entertainment"] = {
            "type": "dj",
            "name": "DJ Volkan",
            "contact": "+90 555 000 0000",
            "requirements": "2 monitor, kabin ışığı",
            "fee": 5000.0,
        }
    return payload


def _create(headers: dict, payload: dict) -> dict:
    r = requests.post(f"{BASE_URL}/api/mice/events", json=payload, headers=headers)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
    return r.json()


def _delete(headers: dict, event_id: str) -> None:
    requests.delete(f"{BASE_URL}/api/mice/events/{event_id}", headers=headers)


class TestMiceEventExtras:

    def test_create_with_all_extras_round_trips(self, demo_auth_headers):
        """Tüm yeni alanlar dolu olarak create edilen event GET'te dönmeli."""
        payload = _make_event_payload(
            name="MICE-Extras-Full", with_extras=True
        )
        created = _create(demo_auth_headers, payload)
        event_id = created.get("id")
        assert event_id, f"id missing in response: {created}"

        try:
            r = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}",
                headers=demo_auth_headers,
            )
            assert r.status_code == 200
            doc = r.json()

            tr = doc.get("technical_requirements")
            assert tr is not None
            assert tr["projector"] is True
            assert tr["microphone_wired"] == 2
            assert tr["internet_mbps"] == 100
            assert tr["notes"]

            sa = doc.get("staff_assignments") or []
            assert len(sa) == 3
            roles = {s["role"] for s in sa}
            assert {"host", "technician", "server"} <= roles

            ent = doc.get("entertainment")
            assert ent is not None
            assert ent["type"] == "dj"
            assert ent["name"] == "DJ Volkan"
            assert float(ent["fee"]) == 5000.0
        finally:
            _delete(demo_auth_headers, event_id)

    def test_create_without_extras_is_backwards_compatible(self, demo_auth_headers):
        """Yeni alanlar gönderilmediğinde event normal yaratılmalı,
        teknik beklentiler `None`, eğlence `None`, personel boş liste olmalı."""
        payload = _make_event_payload(
            name="MICE-Extras-Empty", with_extras=False
        )
        created = _create(demo_auth_headers, payload)
        event_id = created.get("id")
        assert event_id

        try:
            r = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}",
                headers=demo_auth_headers,
            )
            assert r.status_code == 200
            doc = r.json()
            # Geriye uyumluluk: alanlar yoksa None / boş liste
            assert doc.get("technical_requirements") in (None, {})
            assert doc.get("staff_assignments") in (None, [])
            assert doc.get("entertainment") in (None, {})
        finally:
            _delete(demo_auth_headers, event_id)

    def test_update_round_trips_extras(self, demo_auth_headers):
        """Mevcut event'e PUT ile alanlar eklendiğinde sonraki GET'te dönmeli."""
        # Önce alanları olmayan event yarat
        created = _create(
            demo_auth_headers,
            _make_event_payload(name="MICE-Extras-Update", with_extras=False),
        )
        event_id = created["id"]
        try:
            updated = _make_event_payload(
                name="MICE-Extras-Update", with_extras=True
            )
            r = requests.put(
                f"{BASE_URL}/api/mice/events/{event_id}",
                json=updated,
                headers=demo_auth_headers,
            )
            assert r.status_code == 200, r.text

            r = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}",
                headers=demo_auth_headers,
            )
            doc = r.json()
            assert doc["technical_requirements"]["projector"] is True
            assert len(doc["staff_assignments"]) == 3
            assert doc["entertainment"]["type"] == "dj"
        finally:
            _delete(demo_auth_headers, event_id)

    def test_beo_includes_new_fields(self, demo_auth_headers):
        """BEO çıktısı yeni alanları (varsa) içermeli."""
        created = _create(
            demo_auth_headers,
            _make_event_payload(name="MICE-Extras-BEO", with_extras=True),
        )
        event_id = created["id"]
        try:
            r = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}/beo",
                headers=demo_auth_headers,
            )
            assert r.status_code == 200, r.text
            beo = r.json()
            assert beo.get("technical_requirements") is not None
            assert beo.get("technical_requirements", {}).get("projector") is True
            assert beo.get("entertainment", {}).get("type") == "dj"
            assert len(beo.get("staff_assignments") or []) == 3
        finally:
            _delete(demo_auth_headers, event_id)

    def test_partial_extras_only_technical(self, demo_auth_headers):
        """Sadece bir alanı (technical_requirements) gönderince diğerleri default."""
        payload = _make_event_payload(name="MICE-Extras-Partial", with_extras=False)
        payload["technical_requirements"] = {
            "projector": True,
            "internet_mbps": 50,
        }
        created = _create(demo_auth_headers, payload)
        event_id = created["id"]
        try:
            r = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}",
                headers=demo_auth_headers,
            )
            doc = r.json()
            tr = doc.get("technical_requirements")
            assert tr is not None
            assert tr["projector"] is True
            assert tr["internet_mbps"] == 50
            # default değer alanları
            assert tr.get("microphone_wired", 0) == 0
            assert doc.get("entertainment") in (None, {})
        finally:
            _delete(demo_auth_headers, event_id)
