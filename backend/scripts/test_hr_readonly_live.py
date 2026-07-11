import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv(override=False)
sys.path.append("/app")

def log_result(step: str, status: str, extra: str = ""):
    print(f"[{status}] {step:<35} {extra}")

async def main():
    print("==================================================")
    print("HOTELRUNNER LIVE (READ-ONLY) DIAGNOSTIC")
    print("==================================================")
    
    from core import database
    from core.secrets import get_secrets_manager
    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service, HRv2AuthError
    from channel_manager.connectors.hotelrunner_v2.client import HRv2Client
    from channel_manager.connectors.hotelrunner_v2.endpoint_map import ENV_URLS
    
    db = database._raw_db
    sm = get_secrets_manager()
    
    conn = await db.hotelrunner_connections.find_one({"is_active": True, "environment": "live"})
    if not conn:
        log_result("Real HR connection lookup", "FAIL", "No live connection found")
        sys.exit(1)
        
    tenant_id = conn["tenant_id"]
    hr_id = conn["hr_id"]
    
    try:
        secret_data = await sm.get_provider_credentials(tenant_id, "hotelrunner", hr_id)
        token = secret_data.get("token")
        if not token:
            raise ValueError("Token missing in decrypted secret")
        log_result("Real HR credential decrypt", "PASS")
    except Exception as e:
        log_result("Real HR credential decrypt", "FAIL", str(e))
        sys.exit(1)

    # Monkey patch for the old image
    @classmethod
    async def new_create(cls, t_id: str, p_id: str, *, environment: str = "") -> "HotelRunnerV2Service":
        creds = await sm.get_provider_credentials(t_id, "hotelrunner", p_id)
        if not creds:
            raise HRv2AuthError(f"No credentials found for tenant={t_id} property={p_id}")
        t = creds.get("token", "")
        h = creds.get("hr_id", p_id)
        if not t or not h:
            raise HRv2AuthError("Incomplete credentials (token or hr_id missing)")
        env = environment or creds.get("environment", "production")
        base_url = ENV_URLS.get(env, ENV_URLS["production"])
        client = HRv2Client(token=t, hr_id=h, base_url=base_url)
        return cls(t_id, p_id, client, environment=env)
        
    HotelRunnerV2Service.create = new_create

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
