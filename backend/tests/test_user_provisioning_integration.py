"""
User provisioning — entegrasyon testleri (kara-kutu, canli sunucuya vurur).

Doktrin / no-fake-green:
  - Sunucu/kimlik bilgisi yoksa testler temiz SKIP olur (pass DEGIL).
  - Uygun ortam varsa GERCEK assertion kosar.
  - Her test olusturdugu kayitlari `finally` ile temizler (pilot DB kirletmez).

Kapsam (Rota 2 — altyapi/yaris durumu zirhi):
  (a) Gecici (temp) kullanici sifre degistirmeden korumali ucta 403 (force-reset).
  (b) Transaction abort -> orphan kalmaz (atomik primitif).
  (c) Paket-disi / ozel rol atama -> 400.
  (d) Eszamanli ayni-email yarisi -> tam olarak biri 200, digeri 400 (DB unique zirhi).

Ortam:
  VITE_BACKEND_URL (vars. http://localhost:8000)
  E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD (vars. demo@hotel.com / demo123)
"""
import asyncio
import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("VITE_BACKEND_URL", "http://localhost:8000").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "demo@hotel.com")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "demo123")


def _uniq_email() -> str:
    return f"provtest+{uuid.uuid4().hex[:12]}@example.com"


async def _get_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")
    db_name = os.environ.get("DB_NAME", "syroce-pms")
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


async def _cleanup_email(email: str):
    """Olusturulan kullanici + ozluk + davet tokenlarini sil (pilot DB temizligi)."""
    try:
        from security.encrypted_lookup import build_user_email_query
        client, db = await _get_db()
        q = build_user_email_query(email)
        users = await db.users.find(q, {"_id": 0, "id": 1}).to_list(length=50)
        ids = [u["id"] for u in users if u.get("id")]
        if ids:
            await db.staff_members.delete_many({"user_id": {"$in": ids}})
        await db.users.delete_many(q)
        await db.password_reset_codes.delete_many({"email": email})
        client.close()
    except Exception:
        pass


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def admin_headers(event_loop):
    """Admin/super_admin token. Uygun degilse SKIP (fake-green degil)."""
    async def _login():
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=20) as c:
            try:
                r = await c.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            except Exception as e:
                pytest.skip(f"Backend erisilemez: {e}")
            if r.status_code != 200 or "access_token" not in r.json():
                pytest.skip(f"Admin login basarisiz ({r.status_code})")
            token = r.json()["access_token"]
            me = await c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            role = (me.json() or {}).get("role") if me.status_code == 200 else None
            if role not in ("admin", "super_admin"):
                pytest.skip(f"Test hesabi provisioning yetkisinde degil (role={role})")
            return {"Authorization": f"Bearer {token}"}
    return event_loop.run_until_complete(_login())


def test_privileged_and_invalid_role_rejected_400(event_loop, admin_headers):
    """(c) super_admin (ozel) ve gecersiz enum rolu -> 400; kayit olusmaz."""
    async def _run():
        email = _uniq_email()
        try:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=20) as c:
                r_priv = await c.post("/admin/users", headers=admin_headers, json={
                    "name": "Yetki Testi", "email": email, "role": "super_admin", "mode": "temp",
                })
                assert r_priv.status_code == 400, f"super_admin atanabilmemeli: {r_priv.status_code}"

                r_bad = await c.post("/admin/users", headers=admin_headers, json={
                    "name": "Gecersiz Rol", "email": _uniq_email(), "role": "kraliyet_naibi", "mode": "temp",
                })
                assert r_bad.status_code == 400, f"gecersiz rol 400 vermeli: {r_bad.status_code}"
        finally:
            await _cleanup_email(email)
    event_loop.run_until_complete(_run())


def test_temp_user_force_reset_403(event_loop, admin_headers):
    """(a) temp kullanici: /auth/me 200 (izinli) ama korumali uc 403."""
    async def _run():
        email = _uniq_email()
        try:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=20) as c:
                r = await c.post("/admin/users", headers=admin_headers, json={
                    "name": "Gecici Kullanici", "email": email, "role": "staff", "mode": "temp",
                })
                assert r.status_code == 200, f"temp kullanici olusmali: {r.status_code} {r.text}"
                temp_password = r.json().get("temp_password")
                assert temp_password, "temp_password donmeli"

                lr = await c.post("/auth/login", json={"email": email, "password": temp_password})
                assert lr.status_code == 200, f"temp kullanici login olabilmeli: {lr.status_code}"
                tok = lr.json()["access_token"]
                h = {"Authorization": f"Bearer {tok}"}

                me = await c.get("/auth/me", headers=h)
                assert me.status_code == 200, f"/auth/me izinli olmali: {me.status_code}"

                protected = await c.get("/pms/rooms", headers=h)
                assert protected.status_code == 403, (
                    f"force-reset: korumali uc 403 vermeli, gelen {protected.status_code}"
                )
        finally:
            await _cleanup_email(email)
    event_loop.run_until_complete(_run())


def test_concurrent_same_email_one_loses_400(event_loop, admin_headers):
    """(d) Eszamanli ayni-email: tam olarak biri 200, digeri 400; DB'de tek kayit."""
    async def _run():
        email = _uniq_email()
        try:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
                payload = {"name": "Yaris", "email": email, "role": "staff", "mode": "invite"}
                r1, r2 = await asyncio.gather(
                    c.post("/admin/users", headers=admin_headers, json=payload),
                    c.post("/admin/users", headers=admin_headers, json=payload),
                    return_exceptions=False,
                )
                codes = sorted([r1.status_code, r2.status_code])
                assert codes == [200, 400], f"yaris sonucu [200,400] olmali, gelen {codes}"

                # DB-zirhi: tam olarak bir kullanici olmali (orphan/cift yok).
                from security.encrypted_lookup import build_user_email_query
                client, db = await _get_db()
                cnt = await db.users.count_documents(build_user_email_query(email))
                client.close()
                assert cnt == 1, f"e-posta icin tam 1 kullanici olmali, bulunan {cnt}"
        finally:
            await _cleanup_email(email)
    event_loop.run_until_complete(_run())


def test_transaction_rollback_no_orphan(event_loop):
    """(b) Atomik primitif: transaction icinde hata -> insert geri alinir (orphan yok).

    Endpoint tam da bu primitife dayanir. RS/transaction desteklenmiyorsa (tek
    dugum yerel Mongo) test temiz SKIP olur — fake-green degil.
    """
    async def _run():
        from motor.motor_asyncio import AsyncIOMotorClient
        from pymongo.errors import OperationFailure
        mongo_url = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")
        if not mongo_url:
            pytest.skip("MONGO_URL/MONGO_ATLAS_URI yok")
        db_name = os.environ.get("DB_NAME", "syroce-pms")
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        sentinel_id = f"rollback-probe-{uuid.uuid4().hex}"
        try:
            class _Boom(Exception):
                pass
            try:
                async with await client.start_session() as session:
                    async with session.start_transaction():
                        await db.users.insert_one(
                            {"id": sentinel_id, "tenant_id": "__rollback_probe__",
                             "email": "__rollback_probe__", "role": "staff"},
                            session=session,
                        )
                        raise _Boom()  # transaction'i abort'a zorla
            except _Boom:
                pass
            except OperationFailure as e:
                msg = str(e).lower()
                if "replica set" in msg or "transaction numbers" in msg or "transactions are not supported" in msg:
                    pytest.skip("Yerel Mongo replica-set degil; transaction testi atlandi")
                raise
            leftover = await db.users.find_one({"id": sentinel_id})
            assert leftover is None, "abort sonrasi orphan kullanici kalmamali"
        finally:
            await db.users.delete_many({"id": sentinel_id})
            client.close()
    event_loop.run_until_complete(_run())
