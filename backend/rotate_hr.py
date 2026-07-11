import asyncio
import os
import sys

token = os.environ.get("HOTELRUNNER_NEW_TOKEN")
hr_id = os.environ.get("HOTELRUNNER_HR_ID")
tenant_id = os.environ.get("HOTELRUNNER_TENANT_ID")
mongo_url = os.environ.get("MONGO_URL")
db_name = os.environ.get("DB_NAME")
confirm = os.environ.get("CONFIRM_HOTELRUNNER_ROTATION")
app_env = os.environ.get("APP_ENV")
secrets_provider = os.environ.get("SECRETS_PROVIDER")

# Bu sistemde property_id SecretsManager path'inde hr_id olarak kullanılıyor.
# DB kaydında ayrı bir property_id alanı bulunmuyor.
property_id = hr_id  # syroce/.../hotelrunner/{hr_id}

if not all([token, hr_id, tenant_id, mongo_url, db_name]):
    print("HATA: Gerekli çevre değişkenlerinden biri veya birkaçı eksik.")
    sys.exit(1)

if confirm != "YES":
    print("HATA: Explicit confirmation is required (CONFIRM_HOTELRUNNER_ROTATION=YES)")
    sys.exit(1)

# Ortamı değiştirmiyoruz; doğruluyoruz.
if app_env != "production":
    print("HATA: APP_ENV must already be 'production'")
    sys.exit(1)

if secrets_provider not in {"aws_secrets_manager", "vault", "env"}:
    print("HATA: Unsupported or missing SECRETS_PROVIDER")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv(override=False)

if os.environ.get("MONGO_URL") != mongo_url:
    print("HATA: MONGO_URL changed during initialization")
    sys.exit(1)
if os.environ.get("DB_NAME") != db_name:
    print("HATA: DB_NAME changed during initialization")
    sys.exit(1)


async def main():
    masked_tenant = f"{tenant_id[:4]}...{tenant_id[-4:]}" if len(tenant_id) > 8 else "***"
    masked_hr_id = f"{hr_id[:2]}...{hr_id[-2:]}" if len(hr_id) > 4 else "***"
    masked_mongo = f"{mongo_url.split('@')[-1]}" if "@" in mongo_url else "masked"

    print("DB host:", masked_mongo)
    print("DB name:", db_name)
    print("tenant:", masked_tenant)
    print("hr_id:", masked_hr_id)
    print("property_id (=hr_id):", masked_hr_id)
    print("secrets_provider:", secrets_provider)
    print("operation: rotate")
    print("-" * 40)

    from core import database
    from core.secrets.manager import get_secrets_manager

    db = database._raw_db

    if db.name != db_name:
        print("HATA: Database resolution mismatch")
        sys.exit(1)

    sm = get_secrets_manager()

    # DB kaydında property_id ve provider alanları yok; filtre tenant_id + hr_id ile yapılıyor.
    connection_filter = {
        "tenant_id": tenant_id,
        "hr_id": hr_id,
    }

    count = await db.hotelrunner_connections.count_documents(connection_filter)
    if count != 1:
        print(f"HATA: Expected exactly one connection, found {count}")
        sys.exit(1)

    # Eski credentials — rotation scripti; create senaryosunu reddet
    old_credentials = await sm.get_provider_credentials(tenant_id, "hotelrunner", property_id, actor="hotelrunner_rotation_preflight")
    if not old_credentials:
        print("HATA: Existing credentials not found; rotation aborted (use store, not rotate)")
        sys.exit(1)

    # Eski connection metadata yedekle (rollback için)
    old_connection = await db.hotelrunner_connections.find_one(
        connection_filter,
        {"_id": 0, "credentials_ref": 1, "is_active": 1, "token": 1},
    )
    if not old_connection:
        print("HATA: Connection metadata not found")
        sys.exit(1)

    async def rollback(reason: str):
        """Hem secret'ı hem connection metadata'yı eski hâline geri al."""
        print(f"Rollback başlatılıyor — neden: {reason}")
        try:
            # Secret'ı geri yükle
            await sm.store_provider_credentials(
                tenant_id=tenant_id,
                provider="hotelrunner",
                property_id=property_id,
                credentials=old_credentials,
                actor="hotelrunner_rotation_rollback",
            )

            # Connection metadata'yı geri yükle
            restore_set = {}
            if "credentials_ref" in old_connection:
                restore_set["credentials_ref"] = old_connection["credentials_ref"]
            if "is_active" in old_connection:
                restore_set["is_active"] = old_connection["is_active"]

            update = {}
            if restore_set:
                update["$set"] = restore_set
            if "credentials_ref" not in old_connection:
                update.setdefault("$unset", {})["credentials_ref"] = ""

            restore_result = await db.hotelrunner_connections.update_one(connection_filter, update, upsert=False)
            if restore_result.matched_count != 1:
                raise RuntimeError("Rollback connection metadata match failed")

            # Rollback doğrulama: DB'den oku
            restored = await db.hotelrunner_connections.find_one(connection_filter, {"_id": 0, "credentials_ref": 1, "is_active": 1})
            if not restored:
                raise RuntimeError("Rollback connection verification failed")
            if restored.get("credentials_ref") != old_connection.get("credentials_ref"):
                raise RuntimeError("Rollback credentials_ref mismatch")
            if restored.get("is_active") != old_connection.get("is_active"):
                raise RuntimeError("Rollback active-state mismatch")

            # Rollback sonrası secret read-back
            restored_creds = await sm.get_provider_credentials(tenant_id, "hotelrunner", property_id, actor="hotelrunner_rollback_verify")
            if not restored_creds:
                raise RuntimeError("Rollback secret read-back failed: not found")
            if restored_creds.get("token") != old_credentials.get("token"):
                raise RuntimeError("Rollback secret token mismatch")

            print("Rollback başarılı.")
        except Exception as rb_exc:
            print(f"KRİTİK HATA: Rollback başarısız oldu: {rb_exc}")
            sys.exit(1)

    # ── 1. Gerçek rotation API'sini kullan ───────────────────────────────
    try:
        rotation_meta = await sm.rotate_provider_credentials(
            tenant_id=tenant_id,
            provider="hotelrunner",
            property_id=property_id,
            new_credentials={
                "token": token,
                "hr_id": hr_id,
                "environment": "production",
            },
            actor="hotelrunner_manual_rotation",
        )
        path = rotation_meta.secret_path
    except Exception:
        print("HATA: SecretsManager.rotate_provider_credentials başarısız oldu.")
        sys.exit(1)

    # ── 2. Secret read-back doğrulama (connection update'den önce) ────────
    try:
        rotated_creds = await sm.get_provider_credentials(tenant_id, "hotelrunner", property_id, actor="hotelrunner_rotation_verify")
        if not rotated_creds:
            await rollback("rotated credentials could not be read back")
            raise SystemExit("Rotated credentials could not be read back")
        if rotated_creds.get("token") != token:
            await rollback("rotated token verification failed")
            raise SystemExit("Rotated token verification failed")
        if rotated_creds.get("hr_id") != hr_id:
            await rollback("rotated hr_id verification failed")
            raise SystemExit("Rotated hr_id verification failed")
    except SystemExit:
        sys.exit(1)

    # ── 3. Connection metadata güncelle (is_active değiştirme) ───────────
    try:
        result = await db.hotelrunner_connections.update_one(
            connection_filter,
            {"$set": {"credentials_ref": path}, "$unset": {"token": ""}},
            upsert=False,
        )

        if result.matched_count != 1:
            raise Exception(f"Expected to match 1 document, matched {result.matched_count}")

        # Doğrulama: DB'den tekrar oku
        updated = await db.hotelrunner_connections.find_one(
            connection_filter,
            {"_id": 0, "credentials_ref": 1, "is_active": 1, "token": 1},
        )
        if not updated:
            raise Exception("Connection disappeared after update")
        if updated.get("credentials_ref") != path:
            raise Exception("credentials_ref verification failed")
        if "token" in updated:
            raise Exception("plaintext token field still exists after update")

    except Exception as e:
        await rollback(str(e))
        sys.exit(1)

    # ── 4. Plaintext tarama ──────────────────────────────────────────────
    # Not: Yalnızca bilinen MongoDB alanlarını tarıyoruz.
    # Log, dosya veya trace sistemleri bu script kapsamı dışındadır.
    plaintext_found_in_checked_fields = False
    queries = [
        {"token": token},
        {"hr_token": token},
        {"credentials.token": token},
        {"credentials.hr_token": token},
    ]

    try:
        collections = await db.list_collection_names()
    except Exception:
        print("HATA: Koleksiyon listesi alınamadı.")
        await rollback("collection listing failed")
        sys.exit(1)

    for collection_name in collections:
        if collection_name == "_dev_secrets":
            continue
        try:
            for q in queries:
                leak_count = await db[collection_name].count_documents(q)
                if leak_count > 0:
                    plaintext_found_in_checked_fields = True
                    print(f"UYARI: Plaintext token {collection_name} koleksiyonunda sızıntı tespit edildi!")
        except Exception:
            print(f"HATA: {collection_name} taranırken hata oluştu.")
            print("plaintext token found in checked MongoDB fields: unknown")
            await rollback("plaintext scan error")
            sys.exit(1)

    if plaintext_found_in_checked_fields:
        print("plaintext token found in checked MongoDB fields: yes")
        await rollback("plaintext token found in MongoDB")
        sys.exit(2)

    print("secret operation: rotate")
    print(f"rotation_count: {rotation_meta.rotation_count}")
    print("secret path: masked")
    print("connection metadata updated: yes")
    print("plaintext token found in checked MongoDB fields: no")


if __name__ == "__main__":
    asyncio.run(main())
