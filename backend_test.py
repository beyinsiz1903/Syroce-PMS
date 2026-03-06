#!/usr/bin/env python3
"""
Backend test for Turkish Room Block Create package validation
Test Focus:
1. POST /api/pms/room-blocks yeni semantic service üzerinden çalışıyor mu?
2. Idempotency enforcement aktif mi?
3. Başarılı create sonrası inventory.blocked.v1 outbox kaydı oluşuyor mu?
4. Audit kaydı oluşuyor mu?
5. Invalid date range / missing key / wrong property scope güvenli mi?
6. Availability etkisi beklenen şekilde görünüyor mu?
7. Response contract bozulmuş mu?
"""

import os
import uuid
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

import aiohttp
import asyncio


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
print(f"Testing backend at: {BASE_URL}")

class RoomBlockTestValidator:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.tenant_id: Optional[str] = None
        self.test_results = []
        self.available_room = None
        self.test_start_date = None
        self.test_end_date = None

    async def setup(self):
        """Setup authentication and get available room"""
        if not BASE_URL:
            raise Exception("REACT_APP_BACKEND_URL missing from environment")
        
        self.session = aiohttp.ClientSession()
        
        # Login
        login_payload = {
            'email': 'demo@hotel.com', 
            'password': 'demo123'
        }
        
        async with self.session.post(f'{BASE_URL}/api/auth/login', json=login_payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Login failed: {resp.status} - {text}")
            
            login_data = await resp.json()
            self.token = login_data['access_token']
            self.tenant_id = login_data['user']['tenant_id']
        
        # Get available room for testing
        await self._find_available_room()
        print(f"✅ Setup complete. Token obtained, tenant_id: {self.tenant_id}")
        print(f"✅ Test room: {self.available_room['room_number']} ({self.available_room['id']})")
        print(f"✅ Test dates: {self.test_start_date} to {self.test_end_date}")

    async def _find_available_room(self):
        """Find an available room for testing"""
        self.test_start_date = (datetime.utcnow().date() + timedelta(days=30)).isoformat()
        self.test_end_date = (datetime.utcnow().date() + timedelta(days=32)).isoformat()
        
        headers = {'Authorization': f'Bearer {self.token}'}
        url = f'{BASE_URL}/api/pms/rooms/availability?check_in={self.test_start_date}&check_out={self.test_end_date}'
        
        async with self.session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Failed to get availability: {resp.status} - {text}")
            
            availability = await resp.json()
            available_rooms = [room for room in availability if room.get('available') is True]
            
            if not available_rooms:
                raise Exception("No available rooms found for testing date range")
            
            self.available_room = available_rooms[0]

    def _get_headers(self, idempotency_key: str = None, property_id: str = None):
        """Build request headers"""
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        if property_id:
            headers['x-property-id'] = property_id
        return headers

    def _build_room_block_payload(self, room_id: str = None, start_date: str = None, end_date: str = None):
        """Build room block create payload"""
        return {
            'room_id': room_id or self.available_room['id'],
            'type': 'out_of_order',
            'reason': f'TEST-semantic-room-block-{uuid.uuid4().hex[:8]}',
            'details': 'Semantic room block bridge validation test',
            'start_date': start_date or self.test_start_date,
            'end_date': end_date or self.test_end_date,
            'allow_sell': False
        }

    async def _check_database_records(self, block_id: str):
        """Check if outbox and audit records were created"""
        from core.database import db
        
        # Check outbox event
        outbox = await db.outbox_events.find_one({
            'room_block_id': block_id,
            'event_type': 'inventory.blocked.v1',
            'tenant_id': self.tenant_id
        }, {'_id': 0})
        
        # Check audit log
        audit = await db.audit_logs.find_one({
            'entity_type': 'room_block',
            'entity_id': block_id,
            'action': 'room_block_created',
            'tenant_id': self.tenant_id
        }, {'_id': 0})
        
        return outbox, audit

    async def test_1_semantic_service_create_working(self):
        """Test 1: POST /api/pms/room-blocks yeni semantic service üzerinden çalışıyor mu?"""
        test_name = "Semantic Service Create Working"
        try:
            payload = self._build_room_block_payload()
            idem_key = f'test-1-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key)
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: HTTP {resp.status} - {text}")
                    return
                
                data = await resp.json()
                
                # Validate response structure
                if 'block' not in data or 'message' not in data:
                    self.test_results.append(f"❌ {test_name}: Response structure invalid - missing block or message")
                    return
                
                block = data['block']
                if block.get('room_id') != payload['room_id'] or block.get('type') != payload['type']:
                    self.test_results.append(f"❌ {test_name}: Block data mismatch")
                    return
                
                self.test_results.append(f"✅ {test_name}: Semantic service creates room blocks successfully")
                return block['id']
                
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return None

    async def test_2_idempotency_enforcement(self):
        """Test 2: Idempotency enforcement aktif mi?"""
        test_name = "Idempotency Enforcement"
        try:
            payload = self._build_room_block_payload()
            idem_key = f'test-2-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key)
            
            # First request
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: First request failed: HTTP {resp.status} - {text}")
                    return
                
                first_response = await resp.json()
                first_block_id = first_response['block']['id']
            
            # Second request with same idempotency key
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Second request failed: HTTP {resp.status} - {text}")
                    return
                
                second_response = await resp.json()
                second_block_id = second_response['block']['id']
            
            # Validate idempotency
            if first_block_id != second_block_id:
                self.test_results.append(f"❌ {test_name}: Different block IDs returned ({first_block_id} vs {second_block_id})")
                return
            
            self.test_results.append(f"✅ {test_name}: Idempotency enforcement working - same block returned")
            return first_block_id
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return None

    async def test_3_outbox_event_creation(self):
        """Test 3: Başarılı create sonrası inventory.blocked.v1 outbox kaydı oluşuyor mu?"""
        test_name = "Outbox Event Creation"
        try:
            payload = self._build_room_block_payload()
            idem_key = f'test-3-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key)
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Room block create failed: HTTP {resp.status} - {text}")
                    return
                
                data = await resp.json()
                block_id = data['block']['id']
            
            # Check outbox record
            outbox, _ = await self._check_database_records(block_id)
            
            if not outbox:
                self.test_results.append(f"❌ {test_name}: No outbox event found for block {block_id}")
                return
            
            # Validate outbox event structure
            expected_fields = ['event_type', 'tenant_id', 'room_block_id', 'payload']
            missing_fields = [field for field in expected_fields if field not in outbox]
            if missing_fields:
                self.test_results.append(f"❌ {test_name}: Outbox event missing fields: {missing_fields}")
                return
            
            if outbox['event_type'] != 'inventory.blocked.v1':
                self.test_results.append(f"❌ {test_name}: Wrong event type: {outbox['event_type']}")
                return
            
            self.test_results.append(f"✅ {test_name}: inventory.blocked.v1 outbox event created successfully")
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")

    async def test_4_audit_log_creation(self):
        """Test 4: Audit kaydı oluşuyor mu?"""
        test_name = "Audit Log Creation"
        try:
            payload = self._build_room_block_payload()
            idem_key = f'test-4-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key)
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Room block create failed: HTTP {resp.status} - {text}")
                    return
                
                data = await resp.json()
                block_id = data['block']['id']
            
            # Check audit record
            _, audit = await self._check_database_records(block_id)
            
            if not audit:
                self.test_results.append(f"❌ {test_name}: No audit log found for block {block_id}")
                return
            
            # Validate audit log structure
            expected_fields = ['entity_type', 'entity_id', 'action', 'tenant_id']
            missing_fields = [field for field in expected_fields if field not in audit]
            if missing_fields:
                self.test_results.append(f"❌ {test_name}: Audit log missing fields: {missing_fields}")
                return
            
            if audit['action'] != 'room_block_created':
                self.test_results.append(f"❌ {test_name}: Wrong audit action: {audit['action']}")
                return
            
            self.test_results.append(f"✅ {test_name}: Audit log created successfully")
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")

    async def test_5_security_validations(self):
        """Test 5: Invalid date range / missing key / wrong property scope güvenli mi?"""
        test_name = "Security Validations"
        
        # Test missing idempotency key
        try:
            payload = self._build_room_block_payload()
            headers = self._get_headers()  # No idempotency key
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status == 400:
                    text = await resp.text()
                    if 'Idempotency-Key' in text or 'idempotency' in text.lower():
                        self.test_results.append(f"✅ {test_name}: Missing idempotency key properly rejected (HTTP 400)")
                    else:
                        self.test_results.append(f"❌ {test_name}: Missing idempotency key rejected but wrong error message: {text}")
                else:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Missing idempotency key not rejected (HTTP {resp.status}): {text}")
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception testing missing idempotency key - {str(e)}")
        
        # Test invalid date range (end < start)
        try:
            payload = self._build_room_block_payload(
                start_date=self.test_end_date,  # Swap dates to make invalid
                end_date=self.test_start_date
            )
            idem_key = f'test-5b-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key)
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status == 400:
                    self.test_results.append(f"✅ {test_name}: Invalid date range properly rejected (HTTP 400)")
                else:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Invalid date range not rejected (HTTP {resp.status}): {text}")
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception testing invalid date range - {str(e)}")
        
        # Test wrong property scope
        try:
            payload = self._build_room_block_payload()
            idem_key = f'test-5c-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key, property_id='wrong-property-id')
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status == 403:
                    self.test_results.append(f"✅ {test_name}: Wrong property scope properly rejected (HTTP 403)")
                else:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Wrong property scope not rejected (HTTP {resp.status}): {text}")
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception testing wrong property scope - {str(e)}")

    async def test_6_availability_impact(self):
        """Test 6: Availability etkisi beklenen şekilde görünüyor mu?"""
        test_name = "Availability Impact"
        try:
            # Create room block
            payload = self._build_room_block_payload()
            idem_key = f'test-6-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key)
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Room block create failed: HTTP {resp.status} - {text}")
                    return
                
                data = await resp.json()
                blocked_room_id = payload['room_id']
            
            # Check availability impact
            headers = self._get_headers()
            url = f'{BASE_URL}/api/pms/rooms/availability?check_in={self.test_start_date}&check_out={self.test_end_date}'
            
            async with self.session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Failed to get availability: HTTP {resp.status} - {text}")
                    return
                
                availability = await resp.json()
                blocked_room = next((room for room in availability if room.get('id') == blocked_room_id), None)
                
                if not blocked_room:
                    self.test_results.append(f"❌ {test_name}: Blocked room not found in availability response")
                    return
                
                if blocked_room.get('available') is not False:
                    self.test_results.append(f"❌ {test_name}: Blocked room still shows as available: {blocked_room.get('available')}")
                    return
                
                # Check if reason includes block information
                reason = blocked_room.get('reason', '')
                blocks = blocked_room.get('blocks', [])
                
                if 'out_of_order' not in reason and not blocks:
                    self.test_results.append(f"❌ {test_name}: Block not reflected in availability reason/blocks: reason='{reason}', blocks={blocks}")
                    return
                
                self.test_results.append(f"✅ {test_name}: Availability correctly shows room as blocked (available=False)")
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")

    async def test_7_response_contract_integrity(self):
        """Test 7: Response contract bozulmuş mu?"""
        test_name = "Response Contract Integrity"
        try:
            payload = self._build_room_block_payload()
            idem_key = f'test-7-{uuid.uuid4()}'
            headers = self._get_headers(idempotency_key=idem_key)
            
            async with self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.test_results.append(f"❌ {test_name}: Room block create failed: HTTP {resp.status} - {text}")
                    return
                
                data = await resp.json()
                
                # Check required response fields
                required_fields = ['message', 'block', 'room_number']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    self.test_results.append(f"❌ {test_name}: Response missing required fields: {missing_fields}")
                    return
                
                # Check block object structure
                block = data['block']
                required_block_fields = ['id', 'room_id', 'type', 'reason', 'start_date', 'status', 'created_by', 'created_at']
                missing_block_fields = [field for field in required_block_fields if field not in block]
                if missing_block_fields:
                    self.test_results.append(f"❌ {test_name}: Block object missing required fields: {missing_block_fields}")
                    return
                
                # Validate field values
                if block['type'] != payload['type']:
                    self.test_results.append(f"❌ {test_name}: Block type mismatch: expected {payload['type']}, got {block['type']}")
                    return
                
                if block['room_id'] != payload['room_id']:
                    self.test_results.append(f"❌ {test_name}: Block room_id mismatch: expected {payload['room_id']}, got {block['room_id']}")
                    return
                
                # Check if warnings array exists
                if 'warnings' not in data:
                    self.test_results.append(f"❌ {test_name}: Response missing warnings array")
                    return
                
                self.test_results.append(f"✅ {test_name}: Response contract intact - all required fields present and valid")
                
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")

    async def run_all_tests(self):
        """Run all validation tests"""
        print("🚀 Starting Room Block Create Package Validation Tests...")
        print("=" * 70)
        
        await self.setup()
        
        print("\n📋 Running validation tests...")
        
        # Run all tests
        await self.test_1_semantic_service_create_working()
        await self.test_2_idempotency_enforcement()
        await self.test_3_outbox_event_creation()
        await self.test_4_audit_log_creation()
        await self.test_5_security_validations()
        await self.test_6_availability_impact()
        await self.test_7_response_contract_integrity()

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()

    def print_results(self):
        """Print test results summary"""
        print("\n" + "=" * 70)
        print("📊 ROOM BLOCK CREATE PACKAGE VALIDATION RESULTS")
        print("=" * 70)
        
        passed = sum(1 for result in self.test_results if result.startswith('✅'))
        failed = sum(1 for result in self.test_results if result.startswith('❌'))
        
        for result in self.test_results:
            print(result)
        
        print("\n" + "=" * 70)
        print(f"📈 SUMMARY: {passed} PASSED, {failed} FAILED, {passed + failed} TOTAL")
        
        if failed > 0:
            print("❌ KRİTİK HATALAR VAR - Ana ajana bildir!")
        else:
            print("✅ TÜM TESTLER BAŞARILI - Room block create paketi çalışıyor!")
        
        print("=" * 70)
        return failed == 0


async def main():
    """Main test execution"""
    validator = RoomBlockTestValidator()
    try:
        await validator.run_all_tests()
        return validator.print_results()
    except Exception as e:
        print(f"❌ KRITIK HATA: Test çalıştırma başarısız - {str(e)}")
        return False
    finally:
        await validator.cleanup()


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)