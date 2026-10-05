import asyncio
import sys
import logging
from datetime import UTC, datetime
from lxml import etree

sys.path.append('backend')
from domains.channel_manager.providers.exely.client import ExelySoapTransport
from domains.channel_manager.providers.exely.soap_builder import _soap_envelope

logging.basicConfig(level=logging.INFO)

async def test():
    transport = ExelySoapTransport(connection_mode="sandbox")
    
    rq = etree.Element("{http://www.opentravel.org/OTA/2003/05}OTA_ReadRQ", attrib={
        "Version": "1.17",
        "TimeStamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    read_requests = etree.SubElement(rq, "{http://www.opentravel.org/OTA/2003/05}ReadRequests")
    read_request = etree.SubElement(read_requests, "{http://www.opentravel.org/OTA/2003/05}HotelReadRequest", attrib={
        "HotelCode": "501694",
    })
    etree.SubElement(read_request, "{http://www.opentravel.org/OTA/2003/05}SelectionCriteria", attrib={
        "SelectionType": "All",
        "Start": "2026-09-01",
        "End": "2026-10-30",
        "DateType": "CreateDate"
    })
    
    xml = _soap_envelope("API501694", "4150530", "501694", rq)
    
    try:
        raw = await transport.send_soap(xml, "https://www.hopenapi.com/Api/PMSConnect/HotelReadReservationRQ")
        print("RAW RESPONSE:")
        print(raw.decode('utf-8'))
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(test())
