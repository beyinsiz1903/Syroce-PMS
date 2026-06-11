"""
MICE AV Envanteri — Idempotent Kaynak Kilitleme Testleri
========================================================
Task #445 doğrulaması.

Sınırlı stoklu AV/dekor ekipmanı (`mice_resources.total_stock`) için, OTA oda
gece-kilidi (`room_night_locks`) ile aynı sertlikte atomik kaynak kilitlemesinin
çalıştığını kanıtlar: çakışan zaman aralığında aynı ekipmanı kapmaya çalışan iki
eşzamanlı isteğin tam olarak biri başarılı olur, diğeri 409 ile reddedilir;
tek-stok asla aşılmaz (over-subscription imkânsız).

Entegrasyon stilinde — gerçek backend'e HTTP ile bağlanır (Atlas replica set,
transaction'lar üretimle aynı şekilde çalışır). Sunucu erişilemezse test atlanır
(skip-as-pass değil; sahte yeşil yok — atlandığında PASS sayılmaz).

İki etkinlik FARKLI mekânlar ama AYNI sınırlı AV envanterini, ÖRTÜŞEN zaman
aralığında kullanır; böylece mekân çakışması (space conflict) tetiklenmez ve
yalnızca envanter kilidinin yarışı serileştirip serileştirmediği ölçülür.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

API_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
AUTH_CREDS = {"email": "demo@hotel.com", "password": "demo123"}

pytestmark = pytest.mark.skipif(
    not API_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


# ── helpers ───────────────────────────────────────────────────────
async def _login(client: httpx.AsyncClient) -> dict:
    resp = await client.post("/api/auth/login", json=AUTH_CREDS)
    if resp.status_code != 200:
        pytest.skip(f"Authentication failed for demo@hotel.com: {resp.status_code}")
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in login response: {data}")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _create_space(client: httpx.AsyncClient, headers: dict, name: str) -> str:
    resp = await client.post(
        "/api/mice/spaces",
        headers=headers,
        json={"name": name, "capacity_theatre": 100, "active": True},
    )
    assert resp.status_code == 200, f"space create failed: {resp.status_code} {resp.text}"
    return resp.json()["id"]


async def _create_av_resource(
    client: httpx.AsyncClient, headers: dict, name: str, total_stock: float
) -> str:
    resp = await client.post(
        "/api/mice/resources",
        headers=headers,
        json={
            "name": name,
            "type": "av",
            "total_stock": total_stock,
            "unit": "unit",
            "unit_price": 0,
            "active": True,
        },
    )
    assert resp.status_code == 200, f"resource create failed: {resp.status_code} {resp.text}"
    return resp.json()["id"]


def _event_payload(
    *,
    name: str,
    space_id: str,
    inventory_id: str,
    inv_name: str,
    quantity: float,
    start: datetime,
    end: datetime,
    status: str,
) -> dict:
    return {
        "name": name,
        "client_name": "Test Müşteri A.Ş.",
        "client_email": "test@example.com",
        "event_type": "conference",
        "status": status,
        "expected_pax": 40,
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
        "space_bookings": [
            {
                "space_id": space_id,
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
                "setup_style": "theatre",
                "expected_pax": 40,
            }
        ],
        "resources": [
            {
                "inventory_id": inventory_id,
                "name": inv_name,
                "type": "av",
                "quantity": quantity,
                "unit": "unit",
            }
        ],
        "agenda": [],
        "payment_schedule": [],
        "notes": "Task #445 concurrency test",
    }


async def _delete_event(client: httpx.AsyncClient, headers: dict, event_id: str) -> None:
    if event_id:
        await client.delete(f"/api/mice/events/{event_id}", headers=headers)


async def _delete_resource(client: httpx.AsyncClient, headers: dict, rid: str) -> None:
    if rid:
        await client.delete(f"/api/mice/resources/{rid}", headers=headers)


async def _committed_usage(
    client: httpx.AsyncClient, headers: dict, inventory_id: str,
    env_start: datetime, env_end: datetime,
) -> float:
    """Sum requested quantity of *inventory_id* across active events whose
    booking window overlaps [env_start, env_end). Mirrors the backend's
    aggregation so the test independently verifies stock is never exceeded.
    """
    resp = await client.get("/api/mice/events", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    events = body.get("events", body) if isinstance(body, dict) else body
    s_iso, e_iso = env_start.isoformat(), env_end.isoformat()
    total = 0.0
    for ev in events:
        if ev.get("status") not in ("tentative", "definite", "confirmed"):
            continue
        overlaps = False
        for sb in ev.get("space_bookings", []):
            if sb.get("starts_at", "") < e_iso and s_iso < sb.get("ends_at", ""):
                overlaps = True
                break
        if not overlaps:
            continue
        for r in ev.get("resources", []):
            if r.get("inventory_id") == inventory_id:
                total += float(r.get("quantity") or 0)
    return total


# ── tests ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_concurrent_create_only_one_wins_for_single_stock():
    """İki eşzamanlı create_event aynı tek-stoklu AV ekipmanını kapmaya
    çalışırsa: tam olarak biri 200, diğeri 409 alır; stok asla aşılmaz."""
    suffix = uuid.uuid4().hex[:8]
    start = datetime(2027, 6, 1, 9, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)
    created_events: list[str] = []
    resource_id = ""
    async with httpx.AsyncClient(base_url=API_URL, timeout=40) as client:
        headers = await _login(client)
        try:
            space_a = await _create_space(client, headers, f"AVlock-A-{suffix}")
            space_b = await _create_space(client, headers, f"AVlock-B-{suffix}")
            inv_name = f"Dev Ekran {suffix}"
            resource_id = await _create_av_resource(client, headers, inv_name, 1)

            p1 = _event_payload(
                name=f"AVlock-E1-{suffix}", space_id=space_a,
                inventory_id=resource_id, inv_name=inv_name, quantity=1,
                start=start, end=end, status="definite")
            p2 = _event_payload(
                name=f"AVlock-E2-{suffix}", space_id=space_b,
                inventory_id=resource_id, inv_name=inv_name, quantity=1,
                start=start, end=end, status="definite")

            r1, r2 = await asyncio.gather(
                client.post("/api/mice/events", headers=headers, json=p1),
                client.post("/api/mice/events", headers=headers, json=p2),
            )
            results = [r1, r2]
            statuses = sorted(r.status_code for r in results)
            for r in results:
                if r.status_code == 200:
                    created_events.append(r.json()["id"])

            # Exactly one success (200) and one rejection (409). No oversell.
            assert statuses == [200, 409], (
                f"beklenen [200, 409], gelen {statuses} — "
                f"r1={r1.status_code}:{r1.text[:200]} | "
                f"r2={r2.status_code}:{r2.text[:200]}"
            )
            # The 409 must be an inventory-stock rejection (not a space clash).
            rej = next(r for r in results if r.status_code == 409)
            assert "envanteri yetersiz" in rej.text, (
                f"409 envanter reddi bekleniyordu, gelen: {rej.text[:300]}"
            )

            # Independent verification: committed usage never exceeds stock=1.
            used = await _committed_usage(client, headers, resource_id, start, end)
            assert used <= 1, f"over-subscription: {used} > stok 1"
        finally:
            for eid in created_events:
                await _delete_event(client, headers, eid)
            await _delete_resource(client, headers, resource_id)


@pytest.mark.asyncio
async def test_sequential_second_event_rejected_when_stock_exhausted():
    """Stok 1 iken birinci etkinlik ekipmanı alır; ikinci (örtüşen) etkinlik
    409 ile reddedilir — yarış olmadan da yumuşak+kilit kontrolü doğru."""
    suffix = uuid.uuid4().hex[:8]
    start = datetime(2027, 7, 1, 9, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)
    created_events: list[str] = []
    resource_id = ""
    async with httpx.AsyncClient(base_url=API_URL, timeout=40) as client:
        headers = await _login(client)
        try:
            space_a = await _create_space(client, headers, f"AVseq-A-{suffix}")
            space_b = await _create_space(client, headers, f"AVseq-B-{suffix}")
            inv_name = f"Kürsü {suffix}"
            resource_id = await _create_av_resource(client, headers, inv_name, 1)

            r1 = await client.post("/api/mice/events", headers=headers, json=_event_payload(
                name=f"AVseq-E1-{suffix}", space_id=space_a,
                inventory_id=resource_id, inv_name=inv_name, quantity=1,
                start=start, end=end, status="definite"))
            assert r1.status_code == 200, f"first event should win: {r1.text[:300]}"
            created_events.append(r1.json()["id"])

            r2 = await client.post("/api/mice/events", headers=headers, json=_event_payload(
                name=f"AVseq-E2-{suffix}", space_id=space_b,
                inventory_id=resource_id, inv_name=inv_name, quantity=1,
                start=start, end=end, status="definite"))
            assert r2.status_code == 409, f"second event should be rejected: {r2.text[:300]}"
            assert "envanteri yetersiz" in r2.text

            used = await _committed_usage(client, headers, resource_id, start, end)
            assert used <= 1, f"over-subscription: {used} > stok 1"
        finally:
            for eid in created_events:
                await _delete_event(client, headers, eid)
            await _delete_resource(client, headers, resource_id)


@pytest.mark.asyncio
async def test_concurrent_status_promotion_only_one_wins():
    """İki lead etkinlik aynı tek-stoklu AV ekipmanını referanslar; ikisi de
    eşzamanlı aktif duruma ('tentative') yükseltilirse tam olarak biri başarılı
    olur, diğeri 409 (envanter) alır — durum geçişi yolu da kilit + işlem
    içinde korur. (lead → tentative, geçerli durum geçişi.)"""
    suffix = uuid.uuid4().hex[:8]
    start = datetime(2027, 8, 1, 9, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)
    created_events: list[str] = []
    resource_id = ""
    async with httpx.AsyncClient(base_url=API_URL, timeout=40) as client:
        headers = await _login(client)
        try:
            space_a = await _create_space(client, headers, f"AVst-A-{suffix}")
            space_b = await _create_space(client, headers, f"AVst-B-{suffix}")
            inv_name = f"Projeksiyon {suffix}"
            resource_id = await _create_av_resource(client, headers, inv_name, 1)

            # Two events created as 'lead' (no holds → no inventory consumed yet).
            ids = []
            for sid, nm in ((space_a, "E1"), (space_b, "E2")):
                r = await client.post("/api/mice/events", headers=headers, json=_event_payload(
                    name=f"AVst-{nm}-{suffix}", space_id=sid,
                    inventory_id=resource_id, inv_name=inv_name, quantity=1,
                    start=start, end=end, status="lead"))
                assert r.status_code == 200, f"lead create failed: {r.text[:300]}"
                eid = r.json()["id"]
                ids.append(eid)
                created_events.append(eid)

            # Concurrently promote both lead → tentative (active hold).
            r1, r2 = await asyncio.gather(
                client.post(f"/api/mice/events/{ids[0]}/status",
                            headers=headers, json={"status": "tentative"}),
                client.post(f"/api/mice/events/{ids[1]}/status",
                            headers=headers, json={"status": "tentative"}),
            )
            statuses = sorted([r1.status_code, r2.status_code])
            assert statuses == [200, 409], (
                f"beklenen [200, 409], gelen {statuses} — "
                f"r1={r1.status_code}:{r1.text[:200]} | "
                f"r2={r2.status_code}:{r2.text[:200]}"
            )
            rej = next(r for r in (r1, r2) if r.status_code == 409)
            assert "envanteri yetersiz" in rej.text, (
                f"409 envanter reddi bekleniyordu, gelen: {rej.text[:300]}"
            )
            used = await _committed_usage(client, headers, resource_id, start, end)
            assert used <= 1, f"over-subscription: {used} > stok 1"
        finally:
            for eid in created_events:
                await _delete_event(client, headers, eid)
            await _delete_resource(client, headers, resource_id)
