import asyncio
import sys
import os
sys.path.append(os.getcwd())
from core.database import db
from core.tenant_db import set_tenant_context

async def main():
    tenant_id = "bb306859-9748-430f-b24a-5a0d0ea29309"
    set_tenant_context(tenant_id)
    
    docs = await db.bookings.find({"$text": {"$search": "R558962623"}}).to_list(10)
    if docs:
        print("Found via text search:", len(docs))
    else:
        # Search all fields manually if text index is missing
        docs = await db.bookings.find().to_list(1000)
        found = [d for d in docs if "R558962623" in str(d)]
        print("Found via string conversion:", len(found))
        for d in found:
            print(f"ID: {d.get('id')}, Source: {d.get('source')}")

asyncio.run(main())
