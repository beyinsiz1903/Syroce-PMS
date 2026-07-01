"""
Task #123 — Bekleyen kimlik fotoğrafları admin uçları: canlı entegrasyon.

`test_id_photo_admin.py` (Task #86) tüm uçları mock'lanmış motor cursor'ı
ile doğruluyor: gerçek koleksiyon, `require_module_v97("frontdesk")`
kapısı veya cross-call audit yazımı kapsam dışında. Bu dosya boşluğu
canlı bir HTTP suite ile doldurur:

  * `online_checkin_id_photos` koleksiyonuna sahte bir kayıt seed'lenir,
    GET /api/checkin/online/id-photos onu döner mi diye doğrulanır.
  * DELETE /api/checkin/online/id-photos/{photo_id} ile manuel silinir;
    `audit_logs` koleksiyonunda action="manual_delete" + actor_id +
    metadata.reason satırı oluştuğu kontrol edilir.
  * POST /api/checkin/online/id-photos/bulk-delete iki ayrı senaryoda
    (booking_id ve guest_id filtreleri) çağrılır; eşleşen tüm kayıtların
    silindiği ve her biri için ayrı audit kaydı düştüğü doğrulanır.
  * `housekeeping@hotel.com` (role=housekeeping; frontdesk modülünde
    yok) ile aynı uçlara erişim 403 döner.

Çalıştırmak için VITE_BACKEND_URL ile MONGO_URL/MONGO_ATLAS_URI ayarlı,
backend ayakta olmalı. CI'da bu değişkenler set olmayan ortamlarda dosya
toptan skip edilir.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI") or ""
DB_NAME = os.environ.get("DB_NAME", "syroce-pms")

pytestmark = pytest.mark.skipif(
    not BASE_URL or not MONGO_URL,
    reason=(
        "Live e2e: VITE_BACKEND_URL and MONGO_URL/MONGO_ATLAS_URI must be set "
        "and the backend must be running."
    ),
)

PHOTOS_COLL = "online_checkin_id_photos"
AUDIT_COLL = "audit_logs"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def mongo_db():
    """Sync pymongo handle; mirrors test_create_reservation_bridge.py pattern."""
    client = MongoClient(MONGO_URL)
    try:
        yield client[DB_NAME]
    finally:
        client.close()


@pytest.fixture(scope="module")
def demo_user_ctx(demo_auth_headers):
    """Resolve tenant_id and user.id of the demo super_admin via /api/auth/me.

    The router-side filter pins on `current_user.tenant_id`, so seeded
    docs MUST land in the same tenant or the list endpoint will simply
    not see them — masking real failures with a passing assertion.
    """
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=demo_auth_headers, timeout=10)
    if r.status_code != 200:
        pytest.skip(f"/api/auth/me unavailable for demo user: {r.status_code}")
    data = r.json()
    tenant_id = data.get("tenant_id")
    user_id = data.get("id")
    if not tenant_id or not user_id:
        pytest.skip("demo /auth/me response missing tenant_id/id")
    return {"tenant_id": tenant_id, "user_id": user_id}


@pytest.fixture(scope="module")
def non_frontdesk_headers():
    """Login as the seeded `housekeeping@hotel.com` (role=housekeeping).

    `MODULE_ROLES["frontdesk"]` = {FRONT_DESK, SUPERVISOR, ADMIN, SUPER_ADMIN}
    — housekeeping is intentionally NOT in that set, so every id-photo
    admin endpoint must reject this token with 403. If the seed account
    is missing (bare Atlas DB), skip rather than fail the suite.
    """
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "housekeeping@hotel.com", "password": "staff123"},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip("housekeeping@hotel.com seed account unavailable")
    token = resp.json().get("access_token")
    if not token:
        pytest.skip("housekeeping login returned no access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _seed_photo_doc(
    db,
    *,
    tenant_id: str,
    booking_id: str,
    guest_id: str,
    claimed: bool = True,
    uploaded_at: datetime | None = None,
) -> dict:
    """Insert a single fake id-photo metadata row (no encrypted file).

    The cleanup path tolerates missing files: `delete_id_photo` returns
    False silently and `_delete_one` still reports success because the
    metadata row was removed — exactly what we need for an HTTP-level
    e2e without forcing the test to manage AES key material.
    """
    ts = (uploaded_at or datetime.now(UTC)).isoformat()
    doc = {
        "photo_id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "checkin_id": f"chk-{uuid.uuid4().hex[:8]}",
        "claimed": claimed,
        "uploaded_at": ts,
        "size_bytes": 4096,
        "sha256": uuid.uuid4().hex,
        "content_type": "image/jpeg",
        "extension": "jpg",
        "uploaded_by": f"guest:{booking_id}",
        "uploaded_by_role": "guest",
        "source": "online_checkin",
    }
    db[PHOTOS_COLL].insert_one(dict(doc))
    return doc


def _purge_photos(db, tenant_id: str, photo_ids: list[str]) -> None:
    if photo_ids:
        db[PHOTOS_COLL].delete_many(
            {"tenant_id": tenant_id, "photo_id": {"$in": photo_ids}},
        )


def _purge_audit(db, tenant_id: str, photo_ids: list[str]) -> None:
    if photo_ids:
        db[AUDIT_COLL].delete_many(
            {
                "tenant_id": tenant_id,
                "entity_type": "online_checkin_id_photo",
                "entity_id": {"$in": photo_ids},
            },
        )


# ──────────────────────────────────────────────────────────────────────
# Live HTTP tests
# ──────────────────────────────────────────────────────────────────────


def test_seed_list_manual_delete_writes_manual_audit(
    mongo_db, demo_auth_headers, demo_user_ctx,
):
    """Seed → GET list → DELETE manual → verify audit row.

    End-to-end shape: the single insert MUST appear in the staff list
    response, the DELETE MUST drop both the metadata row and write an
    `audit_logs` entry whose action is `manual_delete` and whose
    `actor_id` matches the demo user's id (the cleanup module's
    `actor_id is None` branch produces `auto_delete` — verifying the
    `manual_delete` branch closes the cross-call audit shape).
    """
    tenant_id = demo_user_ctx["tenant_id"]
    user_id = demo_user_ctx["user_id"]
    booking_id = f"e2e-bk-{uuid.uuid4().hex[:8]}"
    guest_id = f"e2e-g-{uuid.uuid4().hex[:8]}"

    seeded = _seed_photo_doc(
        mongo_db, tenant_id=tenant_id, booking_id=booking_id, guest_id=guest_id,
    )
    photo_id = seeded["photo_id"]

    try:
        # 1) List with the booking_id filter — pinpoint our seed row.
        r = requests.get(
            f"{BASE_URL}/api/checkin/online/id-photos",
            params={"booking_id": booking_id, "limit": 50},
            headers=demo_auth_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        ids = [it["photo_id"] for it in body.get("items", [])]
        assert photo_id in ids, f"seeded photo not listed: {ids}"
        assert "retention_days" in body
        # Proven row → expires_at derived from uploaded_at + retention_days.
        row = next(it for it in body["items"] if it["photo_id"] == photo_id)
        assert row["booking_id"] == booking_id
        assert row["guest_id"] == guest_id
        assert "_id" not in row  # internal field never exposed

        # 2) Manual delete with a meaningful reason.
        reason = "e2e KVKK silme talebi #123"
        r = requests.delete(
            f"{BASE_URL}/api/checkin/online/id-photos/{photo_id}",
            params={"reason": reason},
            headers=demo_auth_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"photo_id": photo_id, "deleted": True, "reason": reason}

        # Metadata row gone.
        assert mongo_db[PHOTOS_COLL].find_one(
            {"tenant_id": tenant_id, "photo_id": photo_id},
        ) is None

        # 3) Audit row exists with manual_delete action + this actor.
        # Audit insert is awaited inline in `_delete_one`, so by the time
        # the HTTP response is back the row should already be there; one
        # short retry covers replica-set propagation jitter on Atlas.
        audit_row = None
        for _ in range(5):
            audit_row = mongo_db[AUDIT_COLL].find_one(
                {
                    "tenant_id": tenant_id,
                    "entity_type": "online_checkin_id_photo",
                    "entity_id": photo_id,
                    "action": "manual_delete",
                },
            )
            if audit_row:
                break
            time.sleep(0.2)
        assert audit_row is not None, "manual_delete audit row not found"
        assert audit_row["actor_id"] == user_id
        meta = audit_row.get("metadata") or {}
        assert meta.get("reason", "").startswith("manual_delete:")
        assert reason in meta["reason"]
        assert meta.get("guest_id") == guest_id
        assert meta.get("booking_id") == booking_id
    finally:
        _purge_photos(mongo_db, tenant_id, [photo_id])
        _purge_audit(mongo_db, tenant_id, [photo_id])


def test_bulk_delete_by_booking_id_removes_all_matches(
    mongo_db, demo_auth_headers, demo_user_ctx,
):
    """KVKK booking-bazlı toplu silme: aynı booking_id'li 3 kaydın hepsi
    silinmeli, her biri için ayrı `manual_delete` audit kaydı düşmeli."""
    tenant_id = demo_user_ctx["tenant_id"]
    user_id = demo_user_ctx["user_id"]
    booking_id = f"e2e-bk-{uuid.uuid4().hex[:8]}"
    guest_id = f"e2e-g-{uuid.uuid4().hex[:8]}"

    seeded = [
        _seed_photo_doc(
            mongo_db, tenant_id=tenant_id, booking_id=booking_id, guest_id=guest_id,
        )
        for _ in range(3)
    ]
    photo_ids = [d["photo_id"] for d in seeded]

    try:
        r = requests.post(
            f"{BASE_URL}/api/checkin/online/id-photos/bulk-delete",
            json={"booking_id": booking_id, "reason": "e2e KVKK toplu (booking)"},
            headers=demo_auth_headers,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["matched"] == 3
        assert body["deleted"] == 3
        assert body["failed_photo_ids"] == []

        # All metadata rows gone for that booking.
        remaining = list(
            mongo_db[PHOTOS_COLL].find(
                {"tenant_id": tenant_id, "booking_id": booking_id},
                {"photo_id": 1, "_id": 0},
            )
        )
        assert remaining == []

        # One audit row per photo, action=manual_delete, actor=demo user.
        audit_rows = list(
            mongo_db[AUDIT_COLL].find(
                {
                    "tenant_id": tenant_id,
                    "entity_type": "online_checkin_id_photo",
                    "entity_id": {"$in": photo_ids},
                    "action": "manual_delete",
                },
            )
        )
        assert {r["entity_id"] for r in audit_rows} == set(photo_ids)
        assert all(r["actor_id"] == user_id for r in audit_rows)
        assert all(
            (r.get("metadata") or {}).get("booking_id") == booking_id
            for r in audit_rows
        )
    finally:
        _purge_photos(mongo_db, tenant_id, photo_ids)
        _purge_audit(mongo_db, tenant_id, photo_ids)


def test_bulk_delete_by_guest_id_removes_all_matches(
    mongo_db, demo_auth_headers, demo_user_ctx,
):
    """KVKK guest-bazlı toplu silme: aynı guest_id'li 2 kaydın ikisi de
    silinir; başka booking'ler altında olsalar bile filtre guest_id."""
    tenant_id = demo_user_ctx["tenant_id"]
    guest_id = f"e2e-g-{uuid.uuid4().hex[:8]}"

    seeded = [
        _seed_photo_doc(
            mongo_db,
            tenant_id=tenant_id,
            booking_id=f"e2e-bk-{uuid.uuid4().hex[:8]}",
            guest_id=guest_id,
        )
        for _ in range(2)
    ]
    photo_ids = [d["photo_id"] for d in seeded]

    # Control row in a *different* guest — must NOT be deleted by this call.
    other_booking = f"e2e-bk-{uuid.uuid4().hex[:8]}"
    other_guest = f"e2e-g-{uuid.uuid4().hex[:8]}"
    other = _seed_photo_doc(
        mongo_db, tenant_id=tenant_id, booking_id=other_booking, guest_id=other_guest,
    )

    try:
        r = requests.post(
            f"{BASE_URL}/api/checkin/online/id-photos/bulk-delete",
            json={"guest_id": guest_id, "reason": "e2e KVKK toplu (guest)"},
            headers=demo_auth_headers,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["matched"] == 2
        assert body["deleted"] == 2
        assert body["failed_photo_ids"] == []

        # Targeted rows gone, control row untouched.
        assert mongo_db[PHOTOS_COLL].count_documents(
            {"tenant_id": tenant_id, "guest_id": guest_id},
        ) == 0
        assert mongo_db[PHOTOS_COLL].find_one(
            {"tenant_id": tenant_id, "photo_id": other["photo_id"]},
        ) is not None

        # Audit rows present for the deleted ones only.
        audit_rows = list(
            mongo_db[AUDIT_COLL].find(
                {
                    "tenant_id": tenant_id,
                    "entity_type": "online_checkin_id_photo",
                    "entity_id": {"$in": photo_ids},
                    "action": "manual_delete",
                },
            )
        )
        assert {r["entity_id"] for r in audit_rows} == set(photo_ids)
    finally:
        _purge_photos(mongo_db, tenant_id, photo_ids + [other["photo_id"]])
        _purge_audit(mongo_db, tenant_id, photo_ids + [other["photo_id"]])


def test_non_frontdesk_role_is_rejected_with_403(
    mongo_db, non_frontdesk_headers, demo_user_ctx,
):
    """`require_module_v97("frontdesk")` kapısı: housekeeping rolü
    listeleme, manuel silme ve toplu silme uçlarının hiçbirinde
    geçemez (403). Bu, modül-rol allowlist'ini canlı uçta doğrular —
    mock testlerde yalnızca handler gövdesi çağrıldığı için bu kapı
    hiç tetiklenmiyordu."""
    tenant_id = demo_user_ctx["tenant_id"]
    seed = _seed_photo_doc(
        mongo_db,
        tenant_id=tenant_id,
        booking_id=f"e2e-bk-{uuid.uuid4().hex[:8]}",
        guest_id=f"e2e-g-{uuid.uuid4().hex[:8]}",
    )
    photo_id = seed["photo_id"]

    try:
        r = requests.get(
            f"{BASE_URL}/api/checkin/online/id-photos",
            headers=non_frontdesk_headers,
            timeout=10,
        )
        assert r.status_code == 403, f"GET expected 403, got {r.status_code}: {r.text}"

        r = requests.delete(
            f"{BASE_URL}/api/checkin/online/id-photos/{photo_id}",
            params={"reason": "should not be allowed"},
            headers=non_frontdesk_headers,
            timeout=10,
        )
        assert r.status_code == 403, f"DELETE expected 403, got {r.status_code}: {r.text}"

        r = requests.post(
            f"{BASE_URL}/api/checkin/online/id-photos/bulk-delete",
            json={"booking_id": seed["booking_id"], "reason": "should not be allowed"},
            headers=non_frontdesk_headers,
            timeout=10,
        )
        assert r.status_code == 403, f"BULK expected 403, got {r.status_code}: {r.text}"

        # The 403 handler must NOT have touched the seeded row.
        assert mongo_db[PHOTOS_COLL].find_one(
            {"tenant_id": tenant_id, "photo_id": photo_id},
        ) is not None
        # And no audit row should have been written for this photo_id either.
        assert mongo_db[AUDIT_COLL].find_one(
            {
                "tenant_id": tenant_id,
                "entity_type": "online_checkin_id_photo",
                "entity_id": photo_id,
            },
        ) is None
    finally:
        _purge_photos(mongo_db, tenant_id, [photo_id])
        _purge_audit(mongo_db, tenant_id, [photo_id])
