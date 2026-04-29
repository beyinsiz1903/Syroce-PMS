"""Banket rakip analizi modülü testleri.

Demo tenant üzerinde CRUD + fiyat snapshot + pozisyonlama hesaplaması.
Tenant izolasyonu için aynı tenant içinde yaratıp temizliyoruz; çapraz tenant
kontrolü ayrı bir kullanıcı gerektirir, burada API seviyesinde tenant_id
filtresinin etkin olduğunu (başka tenant'a sızmama) router kodu garantiler.
"""
import os

import pytest
import requests

BASE = os.environ.get("VITE_BACKEND_URL", "http://localhost:8000")


@pytest.fixture
def competitor(demo_auth_headers):
    """Test rakibi yarat, test sonunda temizle."""
    r = requests.post(f"{BASE}/api/banquet/competitors",
                       headers=demo_auth_headers, json={
        "name": "Test Otel A", "hotel_class": 5,
        "capacity_max": 800, "venues": ["Grand", "Bahçe"],
        "notes": "test fixture",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    yield cid
    requests.delete(f"{BASE}/api/banquet/competitors/{cid}",
                     headers=demo_auth_headers)


def test_competitor_crud(demo_auth_headers):
    """Create, list, update, delete tam akış."""
    r = requests.post(f"{BASE}/api/banquet/competitors",
                       headers=demo_auth_headers, json={
        "name": "CRUD Test", "hotel_class": 4,
        "capacity_max": 300, "venues": [],
    })
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["account_type"] == "banquet_competitor"

    # List içinde olmalı
    lst = requests.get(f"{BASE}/api/banquet/competitors",
                         headers=demo_auth_headers).json()["competitors"]
    assert any(c["id"] == cid for c in lst)

    # Update
    u = requests.put(f"{BASE}/api/banquet/competitors/{cid}",
                       headers=demo_auth_headers, json={
        "name": "CRUD Test Renamed", "hotel_class": 5,
        "capacity_max": 400, "venues": ["A"], "notes": "updated",
    })
    assert u.status_code == 200

    # CRM accounts listesi rakibi DÖNDÜRMEMELİ (discriminator filtresi)
    accts = requests.get(f"{BASE}/api/mice/accounts",
                          headers=demo_auth_headers).json()["accounts"]
    assert not any(a["id"] == cid for a in accts), \
        "rakip kaydı CRM hesap listesine sızmış"

    # Delete
    d = requests.delete(f"{BASE}/api/banquet/competitors/{cid}",
                         headers=demo_auth_headers)
    assert d.status_code == 200


def test_rate_snapshots(demo_auth_headers, competitor):
    """Fiyat ekle, listele, sil."""
    # Bir kaç rate ekle
    for price, season in [(1000, "high"), (1200, "high"), (800, "low")]:
        r = requests.post(
            f"{BASE}/api/banquet/competitors/{competitor}/rates",
            headers=demo_auth_headers, json={
                "event_type": "wedding", "season": season,
                "per_pax_price": price, "min_pax": 100, "max_pax": 500,
                "source": "web",
            })
        assert r.status_code == 201, r.text

    rates = requests.get(
        f"{BASE}/api/banquet/competitors/{competitor}/rates",
        headers=demo_auth_headers).json()["rates"]
    assert len(rates) == 3
    # En yeni başta (POST $position:0)
    assert rates[0]["per_pax_price"] == 800

    # Sil
    rid = rates[0]["id"]
    requests.delete(
        f"{BASE}/api/banquet/competitors/{competitor}/rates/{rid}",
        headers=demo_auth_headers)
    rates2 = requests.get(
        f"{BASE}/api/banquet/competitors/{competitor}/rates",
        headers=demo_auth_headers).json()["rates"]
    assert len(rates2) == 2


def test_positioning_aggregation(demo_auth_headers, competitor):
    """Pozisyonlama: birden çok rakip rate'inden min/avg/max çıkmalı."""
    for price in [800, 1000, 1500]:
        requests.post(
            f"{BASE}/api/banquet/competitors/{competitor}/rates",
            headers=demo_auth_headers, json={
                "event_type": "gala", "season": "high",
                "per_pax_price": price, "min_pax": 50, "max_pax": 200,
            })

    pos = requests.get(f"{BASE}/api/banquet/competitor-positioning",
                        headers=demo_auth_headers).json()
    rows = {r["event_type"]: r for r in pos.get("rows", [])}
    gala = rows.get("gala")
    assert gala, "gala satırı pozisyonlamada yok"
    assert gala["competitor_min"] == 800
    assert gala["competitor_max"] == 1500
    # Avg ~1100
    assert 1090 <= gala["competitor_avg"] <= 1110
    assert gala["competitor_count"] == 3
    # Bizim event yoksa position no_data olur
    assert gala["position"] in ("no_data", "below_market",
                                 "in_band", "above_market")


def test_unauthenticated_access_blocked():
    """Auth header'sız 401/403 dönmeli."""
    r = requests.get(f"{BASE}/api/banquet/competitors")
    assert r.status_code in (401, 403)


def test_crm_account_endpoints_cannot_touch_competitor_docs(
        demo_auth_headers, competitor):
    """Discriminator guard: PUT/DELETE /mice/accounts/{id} a competitor ID
    must NOT mutate or remove the competitor record."""
    # PUT denenir → 404 (discriminator filter eşleştirmiyor)
    pu = requests.put(f"{BASE}/api/mice/accounts/{competitor}",
                       headers=demo_auth_headers, json={
        "name": "HIJACKED", "active": True, "credit_limit": 0,
        "payment_terms_days": 0,
    })
    assert pu.status_code == 404, \
        f"CRM PUT competitor ID'sini değiştirmemeli: {pu.status_code}"

    # DELETE denenir → 404
    de = requests.delete(f"{BASE}/api/mice/accounts/{competitor}",
                          headers=demo_auth_headers)
    assert de.status_code == 404, \
        f"CRM DELETE competitor ID'sini silmemeli: {de.status_code}"

    # Competitor hâlâ banquet endpoint'inden erişilebilir ve adı değişmedi
    lst = requests.get(f"{BASE}/api/banquet/competitors",
                        headers=demo_auth_headers).json()["competitors"]
    found = next((c for c in lst if c["id"] == competitor), None)
    assert found is not None, "Competitor silinmiş!"
    assert found["name"] != "HIJACKED", "Competitor adı değişmiş!"
