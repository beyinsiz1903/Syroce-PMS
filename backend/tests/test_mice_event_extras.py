"""MICE event opsiyonel ek alanlar (technical_requirements, staff_assignments,
entertainment) round-trip testleri.

Geriye dönük uyumluluk: alanlar verilmediğinde mevcut etkinlikler etkilenmez;
verildiğinde GET ve BEO çıktısında geri döner.
"""
import os

import pytest
import requests

BASE = os.environ.get("VITE_BACKEND_URL", "http://localhost:8000")


def _ev_payload(**extra):
    body = {
        "name": "Test Wedding",
        "client_name": "Test Client",
        "event_type": "wedding",
        "status": "tentative",
        "expected_pax": 120,
        "start_date": "2026-09-01",
        "end_date": "2026-09-01",
        "space_bookings": [],
        "resources": [],
        "agenda": [],
        "payment_schedule": [],
    }
    body.update(extra)
    return body


def test_event_create_without_extras_is_unchanged(demo_auth_headers):
    """Mevcut akış: extras yok → kayıt çalışır, GET'te alanlar yok/boş."""
    r = requests.post(f"{BASE}/api/mice/events",
                       headers=demo_auth_headers, json=_ev_payload())
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    try:
        g = requests.get(f"{BASE}/api/mice/events/{eid}",
                          headers=demo_auth_headers).json()
        # Yeni alanlar ya yok ya da default boş
        assert not g.get("technical_requirements")
        assert not g.get("staff_assignments")
        assert not g.get("entertainment")
    finally:
        requests.delete(f"{BASE}/api/mice/events/{eid}",
                         headers=demo_auth_headers)


def test_event_extras_round_trip_through_get_and_beo(demo_auth_headers):
    """Tüm 3 yeni alan POST → GET → BEO içinde korunur."""
    body = _ev_payload(
        technical_requirements={
            "projector": True, "sound_system": True,
            "microphone_wireless": 4, "internet_mbps": 200,
            "translation_booths": 2, "notes": "fiber zorunlu",
        },
        staff_assignments=[
            {"role": "chef", "name": "Ali Aşçı", "notes": "baş aşçı"},
            {"role": "server", "name": "Veli Servis"},
            {"role": "technician", "name": "Can Teknisyen"},
        ],
        entertainment={
            "type": "live_band", "name": "Yıldız Grubu",
            "contact": "+90 555 123 4567", "fee": 45000,
            "requirements": "8 kanal mixer + 2 monitör",
        },
    )
    r = requests.post(f"{BASE}/api/mice/events",
                       headers=demo_auth_headers, json=body)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    try:
        g = requests.get(f"{BASE}/api/mice/events/{eid}",
                          headers=demo_auth_headers).json()
        tr = g.get("technical_requirements") or {}
        assert tr.get("projector") is True
        assert tr.get("microphone_wireless") == 4
        assert tr.get("internet_mbps") == 200
        assert tr.get("translation_booths") == 2

        staff = g.get("staff_assignments") or []
        assert len(staff) == 3
        assert {s["role"] for s in staff} == {"chef", "server", "technician"}

        ent = g.get("entertainment") or {}
        assert ent.get("type") == "live_band"
        assert ent.get("name") == "Yıldız Grubu"
        assert ent.get("fee") == 45000

        beo = requests.get(f"{BASE}/api/mice/events/{eid}/beo",
                            headers=demo_auth_headers).json()
        assert beo.get("technical_requirements", {}).get("projector") is True
        assert len(beo.get("staff_assignments") or []) == 3
        assert (beo.get("entertainment") or {}).get("type") == "live_band"
    finally:
        requests.delete(f"{BASE}/api/mice/events/{eid}",
                         headers=demo_auth_headers)


def test_event_partial_extras_only_tech(demo_auth_headers):
    """Sadece bir extras alanı verilebilir, diğerleri default kalır."""
    body = _ev_payload(
        technical_requirements={"stage": True, "lighting": True}
    )
    r = requests.post(f"{BASE}/api/mice/events",
                       headers=demo_auth_headers, json=body)
    assert r.status_code == 200
    eid = r.json()["id"]
    try:
        g = requests.get(f"{BASE}/api/mice/events/{eid}",
                          headers=demo_auth_headers).json()
        tr = g.get("technical_requirements") or {}
        assert tr.get("stage") is True
        assert tr.get("lighting") is True
        # Diğer extras default
        assert not g.get("staff_assignments")
        assert not g.get("entertainment")
    finally:
        requests.delete(f"{BASE}/api/mice/events/{eid}",
                         headers=demo_auth_headers)
