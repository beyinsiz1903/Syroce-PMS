"""Every discovery/snapshot transport path must use the PMSConnect 1.17 contract."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lxml import etree

from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.snapshot_adapter import ExelySnapshotAdapter

pytestmark = pytest.mark.exely_failure_stress
OTA = "http://www.opentravel.org/OTA/2003/05"
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
RESPONSE = f'''<s:Envelope xmlns:s="{SOAP}"><s:Body><OTA_HotelAvailRS xmlns="{OTA}">
<Success/><RoomStays><RoomStay><RoomRates><RoomRate RoomTypeCode="STANDARD" RatePlanCode="BASE">
<Rates><Rate Start="2030-11-23" End="2030-11-25"><BaseByGuestAmts>
<BaseByGuestAmt AmountBeforeTax="80"/></BaseByGuestAmts></Rate></Rates>
</RoomRate></RoomRates></RoomStay></RoomStays></OTA_HotelAvailRS></s:Body></s:Envelope>'''.encode()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["test_connection", "discover_rooms", "snapshot"])
async def test_hotel_avail_wire_version_for_every_caller(monkeypatch, operation):
    transport = SimpleNamespace(send_soap=AsyncMock(return_value=RESPONSE))
    if operation == "snapshot":
        result = await ExelySnapshotAdapter(transport).fetch_snapshot("tenant", "property", {
            "username": "synthetic-user", "password": "synthetic-password", "hotel_code": "TEST-PROPERTY",
            "api_url": "https://example.invalid/soap",
        }, date_from="2030-11-23", date_to="2030-11-25")
        assert len(result) == 2
    else:
        monkeypatch.setattr("domains.channel_manager.providers.exely.provider.provider_io_block_reason", lambda: None)
        provider = ExelyProvider(username="synthetic-user", password="synthetic-password", hotel_code="TEST-PROPERTY")
        provider._transport = transport
        result = await getattr(provider, operation)()
        assert result.success
    transport.send_soap.assert_awaited_once()
    xml, action = transport.send_soap.call_args.args
    request = etree.fromstring(xml.encode()).find(f"{{{SOAP}}}Body/{{{OTA}}}OTA_HotelAvailRQ")
    assert request is not None
    assert request.get("Version") == "1.17"
    assert request.find(f".//{{{OTA}}}HotelRef").get("HotelCode") == "TEST-PROPERTY"
    assert action == "https://www.hopenapi.com/Api/PMSConnect/HotelAvailRQ"
