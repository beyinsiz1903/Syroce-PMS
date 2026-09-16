import asyncio
import sys
import logging
sys.path.append('backend')
from core.database import db
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.security import resolve_exely_credentials
from domains.channel_manager.providers.exely.soap_builder import _soap_envelope, OTA_NS, SOAP_NS, datetime, UTC
from lxml import etree

logging.basicConfig(level=logging.INFO)

async def run():
    # find any exely connection
    conn = await db.exely_connections.find_one({"is_active": True, "hotel_code": "501694"})
    if not conn:
        # Just grab ANY exely connection to see if we can find credentials
        conn = await db.exely_connections.find_one({"is_active": True})
    
    if not conn:
        print("No exely_connections found in DB.")
        # fallback to db.channel_connections
        conn = await db.channel_connections.find_one({"provider": "exely"})
        if not conn:
            print("No channel_connections found.")
            return

    tenant_id = conn.get("tenant_id")
    print(f"Found tenant {tenant_id}, hotel_code {conn.get('hotel_code')}")
    
    creds = await resolve_exely_credentials(tenant_id, conn, actor="test")
    if not creds:
        print("Could not resolve credentials")
        return
        
    username = creds["username"]
    password = creds["password"]
    hotel_code = creds["hotel_code"]
    
    print("Resolved credentials!")
    
    # Now build the read request
    rq = etree.Element(
        f"{{{OTA_NS}}}OTA_ReadRQ",
        attrib={
            "Version": "1.17",
            "TimeStamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )

    read_requests = etree.SubElement(rq, f"{{{OTA_NS}}}ReadRequests")
    read_request = etree.SubElement(
        read_requests,
        f"{{{OTA_NS}}}HotelReadRequest",
        attrib={"HotelCode": hotel_code},
    )

    # Date range covering test reservation (let's assume it was created in Sept or Oct)
    etree.SubElement(
        read_request,
        f"{{{OTA_NS}}}SelectionCriteria",
        attrib={
            "SelectionType": "All",
            "Start": "2026-09-01",
            "End": "2026-10-31",
            "DateType": "CreateDate"
        },
    )
    
    xml = _soap_envelope(username, password, hotel_code, rq)
    
    # Send request
    from domains.channel_manager.providers.exely.client import ExelySoapTransport
    transport = ExelySoapTransport(connection_mode="sandbox")
    try:
        raw = await transport.send_soap(xml, "https://www.hopenapi.com/Api/PMSConnect/HotelReadReservationRQ")
        print("RAW RESPONSE:")
        print(raw.decode('utf-8'))
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(run())
