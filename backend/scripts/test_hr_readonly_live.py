import asyncio
import os
import sys

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)
load_dotenv(override=False)

def log_result(step: str, status: str, extra: str = ""):
    print(f"[{status}] {step:<35} {extra}")

async def main():
    print("==================================================")
    print("HOTELRUNNER LIVE (READ-ONLY) DIAGNOSTIC")
    print("==================================================")
    
    if os.environ.get("APP_ENV") != "production":
        print("HATA: APP_ENV must be 'production'")
        sys.exit(1)
        
    from core import database
    from core.secrets import get_secrets_manager
    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    
    db = database._raw_db
    sm = get_secrets_manager()
    
    # 1. Find live connection
    conn = await db.hotelrunner_connections.find_one({"is_active": True, "environment": "live"})
    if not conn:
        log_result("Real HR connection lookup", "FAIL", "No live connection found")
        sys.exit(1)
        
    tenant_id = conn["tenant_id"]
    hr_id = conn["hr_id"]
    
    # Decrypt token
    try:
        secret_data = await sm.get_provider_credentials(tenant_id, "hotelrunner", hr_id)
        token = secret_data.get("token")
        if not token:
            raise ValueError("Token missing in decrypted secret")
        log_result("Real HR credential decrypt", "PASS")
    except Exception as e:
        log_result("Real HR credential decrypt", "FAIL", str(e))
        sys.exit(1)

    # 2. Test Real HR API Call (Read-Only GET Request)
    try:
        service = await HotelRunnerV2Service.create(tenant_id, hr_id)
        result = await service.fetch_rooms()
        if result.get("success"):
            data = result.get("data", {})
            rooms = data.get("rooms", [])
            log_result("Real HR API call (GET rooms)", "PASS", f"HTTP 200/2xx, fetched {len(rooms)} rooms")
        else:
            log_result("Real HR API call (GET rooms)", "FAIL", result.get("error", ""))
    except Exception as e:
        log_result("Real HR API call (GET rooms)", "FAIL", str(e))
        
    print("Token/secret log: Yok (Redacted & Clean)")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
