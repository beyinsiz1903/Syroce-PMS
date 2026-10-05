import asyncio
import sys
sys.path.append('backend')
from core.database import db

async def run():
    conn = await db.exely_connections.find_one({"is_active": True, "hotel_code": "501694"})
    if not conn:
        conn = await db.channel_connections.find_one({"provider": "exely"})
    print("Conn:", conn)
    
    ref = conn.get("credentials_ref")
    print("Ref:", ref)
    
    cred = await db.provider_credentials.find_one({"tenant_id": conn["tenant_id"], "provider": "exely"})
    print("Cred doc:", cred)
    
    from core.secrets import get_secrets_manager
    sm = get_secrets_manager()
    raw = await sm.get_provider_credentials(conn["tenant_id"], "exely", ref)
    print("Decrypted:", raw)

if __name__ == "__main__":
    asyncio.run(run())
