import asyncio
import sys
from datetime import UTC, datetime
from lxml import etree
sys.path.append('backend')
from domains.channel_manager.providers.exely.client import ExelySoapTransport
from domains.channel_manager.providers.exely.soap_builder import build_hotel_avail_rq

async def test():
    xml = build_hotel_avail_rq("API501694", "4150530", "501694", "2026-09-01", "2026-09-05")
    transport = ExelySoapTransport(connection_mode="sandbox")
    raw = await transport.send_soap(xml, "https://www.hopenapi.com/Api/PMSConnect/HotelAvailRQ")
    print(raw.decode('utf-8'))

if __name__ == "__main__":
    asyncio.run(test())
