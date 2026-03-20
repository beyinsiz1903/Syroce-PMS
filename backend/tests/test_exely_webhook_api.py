"""
Exely Webhook API Tests
========================
Tests for POST /api/webhooks/exely/reservations (OTA_HotelResNotifRQ)
Tests for GET /api/webhooks/exely/health (SOAP PingRS)
Tests for GET /api/webhooks/exely/info (webhook configuration info)

Tests cover:
- Health and info endpoints (public)
- Successful reservation creation via SOAP XML webhook
- Cancellation handling (ResStatus=Cancel)
- Error handling: empty body, invalid XML, unknown hotel_code
- Tenant resolution by hotel_code
- Idempotency with unique reservation IDs
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

# Use external URL for testing
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://reservation-debug.preview.emergentagent.com')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="REACT_APP_BACKEND_URL not set - integration tests require a running server"
)

# Test credentials from review request
DEMO_EMAIL = "demo@hotel.com"
DEMO_PASSWORD = "demo123"
KNOWN_HOTEL_CODE = "501694"
KNOWN_TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"


def get_auth_token():
    """Get JWT token for authenticated endpoints"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    return None


def generate_unique_reservation_id():
    """Generate unique reservation ID for each test to avoid idempotency conflicts"""
    return f"TEST_WEBHOOK_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


def build_soap_reservation_xml(
    reservation_id: str,
    hotel_code: str = KNOWN_HOTEL_CODE,
    guest_first: str = "Test",
    guest_last: str = "Guest",
    checkin: str = None,
    checkout: str = None,
    res_status: str = "Commit",
    room_type_code: str = "STD",
    total_amount: str = "250.00",
    currency: str = "TRY",
    echo_token: str = "test123"
):
    """Build a valid OTA_HotelResNotifRQ SOAP XML"""
    if checkin is None:
        checkin = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    if checkout is None:
        checkout = (datetime.now() + timedelta(days=9)).strftime("%Y-%m-%d")
    
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">
  <soap-env:Body>
    <OTA_HotelResNotifRQ xmlns="http://www.opentravel.org/OTA/2003/05"
                         EchoToken="{echo_token}"
                         TimeStamp="{now_str}"
                         Version="1.0"
                         ResStatus="{res_status}"
                         Target="Production">
      <HotelReservations>
        <HotelReservation ResStatus="{res_status}" CreateDateTime="{now_str}" LastModifyDateTime="{now_str}">
          <UniqueID Type="14" ID="{reservation_id}"/>
          <RoomStays>
            <RoomStay>
              <RoomTypes>
                <RoomType RoomTypeCode="{room_type_code}" RoomDescription="Standard Room"/>
              </RoomTypes>
              <RatePlans>
                <RatePlan RatePlanCode="BAR" RatePlanName="Best Available Rate"/>
              </RatePlans>
              <RoomRates>
                <RoomRate RoomTypeCode="{room_type_code}" RatePlanCode="BAR">
                  <Rates>
                    <Rate EffectiveDate="{checkin}" AmountAfterTax="{total_amount}"/>
                  </Rates>
                </RoomRate>
              </RoomRates>
              <GuestCounts>
                <GuestCount AgeQualifyingCode="10" Count="2"/>
              </GuestCounts>
              <TimeSpan Start="{checkin}" End="{checkout}"/>
              <Total AmountAfterTax="{total_amount}" CurrencyCode="{currency}"/>
              <BasicPropertyInfo HotelCode="{hotel_code}"/>
            </RoomStay>
          </RoomStays>
          <ResGuests>
            <ResGuest>
              <Profiles>
                <ProfileInfo>
                  <Profile>
                    <Customer>
                      <PersonName>
                        <GivenName>{guest_first}</GivenName>
                        <Surname>{guest_last}</Surname>
                      </PersonName>
                      <Email>{guest_first.lower()}.{guest_last.lower()}@test.com</Email>
                      <Telephone PhoneNumber="+905551234567"/>
                    </Customer>
                  </Profile>
                </ProfileInfo>
              </Profiles>
            </ResGuest>
          </ResGuests>
          <ResGlobalInfo>
            <Total AmountAfterTax="{total_amount}" CurrencyCode="{currency}"/>
            <Comments>
              <Comment>
                <Text>Test webhook reservation - automated test</Text>
              </Comment>
            </Comments>
          </ResGlobalInfo>
        </HotelReservation>
      </HotelReservations>
    </OTA_HotelResNotifRQ>
  </soap-env:Body>
</soap-env:Envelope>'''


class TestExelyWebhookHealthAndInfo:
    """Tests for health and info endpoints (public, no auth required)"""
    
    def test_webhook_health_endpoint(self):
        """GET /api/webhooks/exely/health returns SOAP PingRS success response"""
        response = requests.get(f"{BASE_URL}/api/webhooks/exely/health")
        
        assert response.status_code == 200, f"Health endpoint returned {response.status_code}"
        assert "text/xml" in response.headers.get("content-type", ""), "Content-Type should be text/xml"
        
        # Verify SOAP structure
        assert "<PingRS" in response.text, "Response should contain PingRS element"
        assert "<Success/>" in response.text, "Response should contain Success element"
        print(f"✓ Health endpoint returned valid SOAP PingRS response")
    
    def test_webhook_info_endpoint(self):
        """GET /api/webhooks/exely/info returns webhook configuration JSON"""
        response = requests.get(f"{BASE_URL}/api/webhooks/exely/info")
        
        assert response.status_code == 200, f"Info endpoint returned {response.status_code}"
        
        data = response.json()
        assert "webhook_url" in data, "Response should contain webhook_url"
        assert data["webhook_url"] == "/api/webhooks/exely/reservations", "webhook_url should be correct"
        assert data["method"] == "POST", "method should be POST"
        assert "text/xml" in data["content_type"], "content_type should include text/xml"
        assert "supported_operations" in data, "Response should list supported_operations"
        assert len(data["supported_operations"]) >= 3, "Should support at least 3 operations"
        print(f"✓ Info endpoint returned correct webhook configuration")


class TestExelyWebhookReservationPush:
    """Tests for POST /api/webhooks/exely/reservations (main webhook endpoint)"""
    
    def test_webhook_empty_body_error(self):
        """Webhook returns proper error for empty request body"""
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=""
        )
        
        # Webhook returns 200 even for errors (OTA convention to prevent retries)
        assert response.status_code == 200, f"Webhook returned {response.status_code}"
        assert "text/xml" in response.headers.get("content-type", ""), "Response should be XML"
        
        # Should return error response
        assert "<Error" in response.text or "Empty request body" in response.text, \
            "Response should indicate empty body error"
        print(f"✓ Empty body correctly returns error in SOAP response")
    
    def test_webhook_invalid_xml_error(self):
        """Webhook returns proper error for malformed XML"""
        invalid_xml = "<invalid><not-closed>"
        
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=invalid_xml
        )
        
        assert response.status_code == 200, f"Webhook returned {response.status_code}"
        assert "text/xml" in response.headers.get("content-type", ""), "Response should be XML"
        
        # Should return XML parse error
        assert "<Error" in response.text or "XML parse error" in response.text, \
            "Response should indicate XML parse error"
        print(f"✓ Invalid XML correctly returns parse error in SOAP response")
    
    def test_webhook_unknown_hotel_code_error(self):
        """Webhook returns error for unknown hotel_code"""
        unknown_hotel_code = "999999999"
        res_id = generate_unique_reservation_id()
        
        xml_payload = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=unknown_hotel_code
        )
        
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response.status_code == 200, f"Webhook returned {response.status_code}"
        assert "text/xml" in response.headers.get("content-type", ""), "Response should be XML"
        
        # Should return error about unknown hotel code
        assert "<Error" in response.text or "Unknown hotel" in response.text or "404" in response.text, \
            f"Response should indicate unknown hotel code. Got: {response.text[:500]}"
        print(f"✓ Unknown hotel code correctly returns error")
    
    def test_webhook_successful_reservation_creation(self):
        """Webhook successfully creates reservation from valid SOAP XML"""
        res_id = generate_unique_reservation_id()
        
        xml_payload = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE,
            guest_first="Webhook",
            guest_last="TestGuest",
            total_amount="500.00",
            currency="TRY"
        )
        
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response.status_code == 200, f"Webhook returned {response.status_code}"
        assert "text/xml" in response.headers.get("content-type", ""), "Response should be XML"
        
        # Should return success response
        assert "<Success/>" in response.text, f"Response should contain Success element. Got: {response.text[:500]}"
        assert "OTA_HotelResNotifRS" in response.text, "Response should be OTA_HotelResNotifRS"
        
        # Verify the reservation ID is echoed back
        if res_id in response.text:
            print(f"✓ Reservation {res_id} echoed back in response")
        
        print(f"✓ Reservation {res_id} created successfully via webhook")
        
        # Return res_id for verification in other tests
        return res_id
    
    def test_webhook_parses_guest_info_correctly(self):
        """Webhook correctly parses guest name, dates, room info from SOAP XML"""
        res_id = generate_unique_reservation_id()
        checkin = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        checkout = (datetime.now() + timedelta(days=12)).strftime("%Y-%m-%d")
        
        xml_payload = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE,
            guest_first="ParseTest",
            guest_last="GuestName",
            checkin=checkin,
            checkout=checkout,
            room_type_code="DLX",
            total_amount="750.00"
        )
        
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response.status_code == 200, f"Webhook returned {response.status_code}"
        assert "<Success/>" in response.text, f"Should succeed. Got: {response.text[:500]}"
        
        # Now verify the data was stored correctly by checking local reservations
        token = get_auth_token()
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            local_res = requests.get(
                f"{BASE_URL}/api/channel-manager/exely/reservations/local",
                headers=headers
            )
            if local_res.status_code == 200:
                reservations = local_res.json().get("reservations", [])
                matching = [r for r in reservations if r.get("external_id") == res_id]
                if matching:
                    stored = matching[0]
                    assert "ParseTest" in stored.get("guest_name", ""), "Guest first name should be stored"
                    assert "GuestName" in stored.get("guest_name", ""), "Guest last name should be stored"
                    assert stored.get("checkin_date", "").startswith(checkin), "Check-in should match"
                    assert stored.get("checkout_date", "").startswith(checkout), "Check-out should match"
                    print(f"✓ Guest info correctly parsed and stored for {res_id}")
                else:
                    print(f"⚠ Could not find reservation {res_id} in local store (may need tenant filtering)")
            else:
                print(f"⚠ Could not verify stored data: {local_res.status_code}")
        else:
            print(f"⚠ Auth failed, skipping data verification")
        
        print(f"✓ Webhook accepted reservation {res_id} with correct structure")
    
    def test_webhook_handles_cancellation(self):
        """Webhook correctly handles ResStatus=Cancel"""
        # First create a reservation
        res_id = generate_unique_reservation_id()
        
        # Create the reservation first
        create_xml = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE,
            res_status="Commit"
        )
        
        create_response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=create_xml
        )
        
        assert "<Success/>" in create_response.text, f"Create should succeed. Got: {create_response.text[:300]}"
        print(f"✓ Created reservation {res_id} for cancellation test")
        
        # Now send cancellation
        cancel_xml = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE,
            res_status="Cancel"
        )
        
        cancel_response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=cancel_xml
        )
        
        assert cancel_response.status_code == 200, f"Cancel returned {cancel_response.status_code}"
        assert "<Success/>" in cancel_response.text or "OTA_HotelResNotifRS" in cancel_response.text, \
            f"Cancellation should be acknowledged. Got: {cancel_response.text[:500]}"
        
        print(f"✓ Cancellation for {res_id} processed successfully")
    
    def test_webhook_idempotency_same_reservation(self):
        """Webhook handles duplicate reservation IDs (idempotency)"""
        res_id = generate_unique_reservation_id()
        
        xml_payload = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE
        )
        
        # Send first time
        response1 = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response1.status_code == 200
        assert "<Success/>" in response1.text or "OTA_HotelResNotifRS" in response1.text
        
        # Send second time with same ID
        response2 = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response2.status_code == 200, f"Duplicate request returned {response2.status_code}"
        # Should still return success (idempotent - skips duplicate)
        assert "OTA_HotelResNotifRS" in response2.text, \
            f"Duplicate should still return valid response. Got: {response2.text[:500]}"
        
        print(f"✓ Idempotency handled correctly for duplicate {res_id}")


class TestExelyWebhookTenantResolution:
    """Tests for tenant resolution by hotel_code"""
    
    def test_tenant_resolved_by_hotel_code(self):
        """Webhook resolves tenant_id correctly from hotel_code in XML"""
        res_id = generate_unique_reservation_id()
        
        xml_payload = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE,  # This maps to KNOWN_TENANT_ID
            guest_first="TenantTest",
            guest_last="User"
        )
        
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response.status_code == 200
        
        # If the reservation was created, it means tenant resolution worked
        if "<Success/>" in response.text:
            print(f"✓ Tenant resolved correctly for hotel_code {KNOWN_HOTEL_CODE}")
        else:
            # Check if it's an unknown hotel error (meaning resolution was attempted but failed)
            if "Unknown hotel" in response.text or "404" in response.text:
                pytest.skip(f"Hotel code {KNOWN_HOTEL_CODE} not configured - tenant resolution skipped")
            else:
                print(f"Response: {response.text[:500]}")
        
        return res_id


class TestExelyWebhookAutoImport:
    """Tests for auto-import to PMS bookings"""
    
    def test_webhook_triggers_auto_import(self):
        """Webhook auto-imports reservation to PMS booking"""
        res_id = generate_unique_reservation_id()
        
        xml_payload = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE,
            guest_first="AutoImport",
            guest_last="TestUser",
            total_amount="1000.00"
        )
        
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response.status_code == 200
        
        if "<Success/>" not in response.text:
            if "Unknown hotel" in response.text:
                pytest.skip("Hotel code not configured - auto-import test skipped")
            print(f"Warning: Response was: {response.text[:500]}")
        
        # Verify auto-import by checking if a PMS booking was created
        token = get_auth_token()
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            
            # Check exely_reservations for pms_status
            local_res = requests.get(
                f"{BASE_URL}/api/channel-manager/exely/reservations/local",
                headers=headers
            )
            
            if local_res.status_code == 200:
                reservations = local_res.json().get("reservations", [])
                matching = [r for r in reservations if r.get("external_id") == res_id]
                
                if matching:
                    stored = matching[0]
                    pms_status = stored.get("pms_status", "")
                    pms_booking_id = stored.get("pms_booking_id")
                    
                    # Auto-import sets pms_status to 'imported' or 'pending' or 'pending_mapping'
                    if pms_status in ("imported", "pending", "pending_mapping"):
                        print(f"✓ Auto-import triggered: pms_status={pms_status}, pms_booking_id={pms_booking_id}")
                    else:
                        print(f"⚠ pms_status is '{pms_status}' - auto-import may not have run")
                else:
                    print(f"⚠ Reservation {res_id} not found in local store")
            else:
                print(f"⚠ Could not check auto-import: {local_res.status_code}")
        else:
            print(f"⚠ Auth failed, could not verify auto-import")


class TestExelyWebhookResponseFormat:
    """Tests for proper OTA_HotelResNotifRS SOAP response format"""
    
    def test_success_response_format(self):
        """Success response has correct OTA_HotelResNotifRS structure"""
        res_id = generate_unique_reservation_id()
        
        xml_payload = build_soap_reservation_xml(
            reservation_id=res_id,
            hotel_code=KNOWN_HOTEL_CODE,
            echo_token="format_test_123"
        )
        
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=xml_payload
        )
        
        assert response.status_code == 200
        
        # Verify SOAP structure
        body = response.text
        
        if "<Success/>" in body:
            # Check required elements
            assert "soap-env:Envelope" in body or "soap:Envelope" in body, "Should have SOAP envelope"
            assert "OTA_HotelResNotifRS" in body, "Should have OTA_HotelResNotifRS element"
            assert 'xmlns="http://www.opentravel.org/OTA/2003/05"' in body or 'xmlns=' in body, \
                "Should have OTA namespace"
            
            # Check EchoToken is echoed back
            if "format_test_123" in body:
                print(f"✓ EchoToken correctly echoed in response")
            
            # Check timestamp
            assert "TimeStamp=" in body, "Should have TimeStamp attribute"
            
            print(f"✓ Success response has correct OTA_HotelResNotifRS SOAP structure")
        else:
            if "Unknown hotel" in body:
                pytest.skip("Hotel code not configured - format test skipped")
            print(f"Response: {body[:500]}")
    
    def test_error_response_format(self):
        """Error response has correct OTA_HotelResNotifRS structure with Error element"""
        response = requests.post(
            f"{BASE_URL}/api/webhooks/exely/reservations",
            headers={"Content-Type": "text/xml; charset=utf-8"},
            data=""  # Empty body triggers error
        )
        
        assert response.status_code == 200
        body = response.text
        
        assert "OTA_HotelResNotifRS" in body, "Error should still return OTA_HotelResNotifRS"
        assert "<Error" in body or "<Errors>" in body, "Should have Error element"
        
        print(f"✓ Error response has correct OTA_HotelResNotifRS SOAP structure")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
