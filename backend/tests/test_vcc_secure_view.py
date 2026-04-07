"""
VCC (Virtual Credit Card) Secure View API Tests
Tests the 3-view limit feature for OTA/Agency virtual credit cards.

Features tested:
- POST /api/pms/reservations/{booking_id}/vcc - Store VCC (encrypted at rest)
- GET /api/pms/reservations/{booking_id}/vcc/status - Check VCC status without consuming a view
- POST /api/pms/reservations/{booking_id}/vcc/reveal - Reveal card details (consumes 1 of 3 views)
- 4th reveal attempt should return 403 (view limit reached)
- DELETE /api/pms/reservations/{booking_id}/vcc - Delete VCC data
- Duplicate card storage should return 409
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'https://auto-mapping.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

# Test card data
TEST_CARD = {
    "card_holder": "TEST VCC Holder",
    "card_number": "4111111111111111",
    "expiry": "12/28",
    "cvv": "123",
    "card_type": "virtual"
}


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture(scope="module")
def booking_id(api_client):
    """Get a valid booking ID for testing"""
    response = api_client.get(f"{BASE_URL}/api/pms/bookings?limit=1")
    assert response.status_code == 200, f"Failed to get bookings: {response.text}"
    bookings = response.json()
    assert len(bookings) > 0, "No bookings found for testing"
    return bookings[0]["id"]


@pytest.fixture(autouse=True)
def cleanup_vcc(api_client, booking_id):
    """Cleanup VCC data before and after each test"""
    # Cleanup before test
    api_client.delete(f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc")
    yield
    # Cleanup after test
    api_client.delete(f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc")


class TestVCCStore:
    """Test VCC storage endpoint"""
    
    def test_store_vcc_success(self, api_client, booking_id):
        """Test storing a VCC successfully"""
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        assert response.status_code == 200, f"Store VCC failed: {response.text}"
        
        data = response.json()
        assert data["success"] is True
        assert "vcc" in data
        
        vcc = data["vcc"]
        assert "id" in vcc
        assert "card_mask" in vcc
        assert vcc["card_type"] == "virtual"
        assert vcc["view_count"] == 0
        assert vcc["max_views"] == 3
        assert vcc["locked"] is False
        
        # Verify card is masked (should show first 6 and last 4 digits)
        assert "****" in vcc["card_mask"] or "*" in vcc["card_mask"]
        print(f"✓ VCC stored successfully with mask: {vcc['card_mask']}")
    
    def test_store_vcc_duplicate_returns_409(self, api_client, booking_id):
        """Test that storing a duplicate VCC returns 409"""
        # First store
        response1 = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        assert response1.status_code == 200, f"First store failed: {response1.text}"
        
        # Second store should fail with 409
        response2 = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        assert response2.status_code == 409, f"Expected 409, got {response2.status_code}: {response2.text}"
        
        data = response2.json()
        assert "detail" in data
        print(f"✓ Duplicate VCC correctly rejected with 409: {data['detail']}")
    
    def test_store_vcc_invalid_booking_returns_404(self, api_client):
        """Test that storing VCC for invalid booking returns 404"""
        fake_booking_id = str(uuid.uuid4())
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{fake_booking_id}/vcc",
            json=TEST_CARD
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Invalid booking correctly rejected with 404")


class TestVCCStatus:
    """Test VCC status endpoint"""
    
    def test_status_no_vcc(self, api_client, booking_id):
        """Test status when no VCC exists"""
        response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/status"
        )
        assert response.status_code == 200, f"Status check failed: {response.text}"
        
        data = response.json()
        assert data["has_vcc"] is False
        print("✓ Status correctly shows no VCC")
    
    def test_status_with_vcc(self, api_client, booking_id):
        """Test status when VCC exists"""
        # First store a VCC
        api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        
        # Check status
        response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/status"
        )
        assert response.status_code == 200, f"Status check failed: {response.text}"
        
        data = response.json()
        assert data["has_vcc"] is True
        assert "vcc" in data
        
        vcc = data["vcc"]
        assert "id" in vcc
        assert "card_mask" in vcc
        assert vcc["view_count"] == 0
        assert vcc["max_views"] == 3
        assert vcc["locked"] is False
        print(f"✓ Status correctly shows VCC with {vcc['view_count']}/{vcc['max_views']} views")
    
    def test_status_does_not_consume_view(self, api_client, booking_id):
        """Test that checking status does not consume a view"""
        # Store VCC
        api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        
        # Check status multiple times
        for i in range(5):
            response = api_client.get(
                f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/status"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["vcc"]["view_count"] == 0, f"View count should be 0, got {data['vcc']['view_count']}"
        
        print("✓ Status check does not consume views (checked 5 times, view_count still 0)")


class TestVCCReveal:
    """Test VCC reveal endpoint with 3-view limit"""
    
    def test_reveal_consumes_view(self, api_client, booking_id):
        """Test that reveal consumes a view"""
        # Store VCC
        api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        
        # Reveal once
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/reveal"
        )
        assert response.status_code == 200, f"Reveal failed: {response.text}"
        
        data = response.json()
        assert data["success"] is True
        assert data["view_count"] == 1
        assert data["max_views"] == 3
        assert data["remaining_views"] == 2
        assert data["locked"] is False
        
        # Verify card details are returned
        assert "card" in data
        card = data["card"]
        assert card["card_holder"] == TEST_CARD["card_holder"]
        assert card["card_number"] == TEST_CARD["card_number"]
        assert card["expiry"] == TEST_CARD["expiry"]
        assert card["cvv"] == TEST_CARD["cvv"]
        
        print(f"✓ Reveal successful: {data['view_count']}/{data['max_views']} views used")
    
    def test_reveal_three_times_then_locked(self, api_client, booking_id):
        """Test that after 3 reveals, the card is locked"""
        # Store VCC
        api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        
        # Reveal 3 times
        for i in range(1, 4):
            response = api_client.post(
                f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/reveal"
            )
            assert response.status_code == 200, f"Reveal {i} failed: {response.text}"
            
            data = response.json()
            assert data["view_count"] == i
            assert data["remaining_views"] == 3 - i
            
            if i == 3:
                assert data["locked"] is True, "Card should be locked after 3rd reveal"
            else:
                assert data["locked"] is False
            
            print(f"  Reveal {i}: view_count={data['view_count']}, remaining={data['remaining_views']}, locked={data['locked']}")
        
        print("✓ Card correctly locked after 3 reveals")
    
    def test_fourth_reveal_returns_403(self, api_client, booking_id):
        """Test that 4th reveal attempt returns 403"""
        # Store VCC
        api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        
        # Reveal 3 times
        for i in range(3):
            response = api_client.post(
                f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/reveal"
            )
            assert response.status_code == 200, f"Reveal {i+1} failed: {response.text}"
        
        # 4th reveal should fail with 403
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/reveal"
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data
        print(f"✓ 4th reveal correctly rejected with 403: {data['detail']}")
    
    def test_reveal_no_vcc_returns_404(self, api_client, booking_id):
        """Test that reveal without VCC returns 404"""
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/reveal"
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Reveal without VCC correctly rejected with 404")


class TestVCCDelete:
    """Test VCC delete endpoint"""
    
    def test_delete_vcc_success(self, api_client, booking_id):
        """Test deleting a VCC successfully"""
        # Store VCC
        api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        
        # Delete VCC
        response = api_client.delete(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc"
        )
        assert response.status_code == 200, f"Delete failed: {response.text}"
        
        data = response.json()
        assert data["success"] is True
        
        # Verify VCC is deleted
        status_response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/status"
        )
        status_data = status_response.json()
        assert status_data["has_vcc"] is False
        
        print("✓ VCC deleted successfully and verified")
    
    def test_delete_no_vcc_returns_404(self, api_client, booking_id):
        """Test that deleting non-existent VCC returns 404"""
        response = api_client.delete(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc"
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Delete non-existent VCC correctly rejected with 404")


class TestVCCFullFlow:
    """Test complete VCC flow end-to-end"""
    
    def test_full_vcc_lifecycle(self, api_client, booking_id):
        """Test complete VCC lifecycle: store -> status -> reveal x3 -> locked -> delete"""
        print("\n=== VCC Full Lifecycle Test ===")
        
        # 1. Store VCC
        print("1. Storing VCC...")
        store_response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc",
            json=TEST_CARD
        )
        assert store_response.status_code == 200
        print(f"   ✓ VCC stored with mask: {store_response.json()['vcc']['card_mask']}")
        
        # 2. Check status (should not consume view)
        print("2. Checking status...")
        status_response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/status"
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["has_vcc"] is True
        assert status_data["vcc"]["view_count"] == 0
        print(f"   ✓ Status: has_vcc=True, view_count=0")
        
        # 3. Reveal 3 times
        print("3. Revealing card 3 times...")
        for i in range(1, 4):
            reveal_response = api_client.post(
                f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/reveal"
            )
            assert reveal_response.status_code == 200
            reveal_data = reveal_response.json()
            print(f"   Reveal {i}: view_count={reveal_data['view_count']}, remaining={reveal_data['remaining_views']}, locked={reveal_data['locked']}")
            
            # Verify decrypted card data
            assert reveal_data["card"]["card_number"] == TEST_CARD["card_number"]
        
        # 4. Verify locked status
        print("4. Verifying locked status...")
        status_response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/status"
        )
        status_data = status_response.json()
        assert status_data["vcc"]["locked"] is True or status_data["vcc"]["view_count"] >= 3
        print(f"   ✓ Card is locked: view_count={status_data['vcc']['view_count']}")
        
        # 5. Try 4th reveal (should fail)
        print("5. Attempting 4th reveal (should fail)...")
        reveal_response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/reveal"
        )
        assert reveal_response.status_code == 403
        print(f"   ✓ 4th reveal rejected with 403")
        
        # 6. Delete VCC
        print("6. Deleting VCC...")
        delete_response = api_client.delete(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc"
        )
        assert delete_response.status_code == 200
        print(f"   ✓ VCC deleted")
        
        # 7. Verify deletion
        print("7. Verifying deletion...")
        status_response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vcc/status"
        )
        status_data = status_response.json()
        assert status_data["has_vcc"] is False
        print(f"   ✓ VCC no longer exists")
        
        print("\n=== VCC Full Lifecycle Test PASSED ===")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
