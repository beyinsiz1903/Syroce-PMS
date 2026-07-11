import asyncio
import os
import sys

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)
load_dotenv(override=False)

async def main():
    print("==================================================")
    print("HOTELRUNNER SECRET BACKFILL")
    print("==================================================")

    if os.environ.get("APP_ENV") != "production":
        print("HATA: APP_ENV must be 'production'")
        sys.exit(1)

    from core import database
    from core.secrets import get_secrets_manager

    db = database._raw_db
    sm = get_secrets_manager()

    docs = await db.hotelrunner_connections.find({"is_active": True, "environment": "live"}).to_list(100)

    if not docs:
        print("No active live connection found.")
        sys.exit(0)

    for conn in docs:
        tenant_id = conn.get("tenant_id")
        hr_id = conn.get("hr_id")
        token = conn.get("token")

        if not token:
            print(f"tenant_id={tenant_id} hr_id={hr_id} NO TOKEN FOUND on connection doc.")
            continue

        print(f"Processing tenant_id: {tenant_id}, hr_id: {hr_id}")

        creds = {"token": token}
        if conn.get("callback_secret"):
            creds["callback_secret"] = conn.get("callback_secret")

        try:
            # Store credentials securely
            path = await sm.store_provider_credentials(
                tenant_id,
                "hotelrunner",
                hr_id,
                creds
            )
            print(f"  tenant_id: {tenant_id}")
            print(f"  hr_id: {hr_id}")
            print(f"  secret_path: {path}")
            print(f"  stored: true")
            print(f"  token_logged: false")

            # Note: We do NOT delete or modify the legacy field here per requirements.
        except Exception as e:
            print(f"  tenant_id: {tenant_id}")
            print(f"  hr_id: {hr_id}")
            print(f"  stored: false")
            print(f"  token_logged: false")
            print(f"  error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
