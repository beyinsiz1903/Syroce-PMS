#!/usr/bin/env python3
"""
Comprehensive Backend Testing for RoomBlockRelease Semantic Migration
Test Cases from Review Request:
1. Authenticate and obtain bearer token
2. Create a room block using POST /api/pms/room-blocks with Idempotency-Key
3. Release that block using POST /api/pms/room-blocks/{block_id}/cancel with Idempotency-Key
4. Validate response structure
5. Verify outbox event inventory.released.v1 exists
6. Verify audit log room_block_released exists
7. Verify availability effects
8. Verify idempotency behavior
9. Verify validations (missing key, wrong property scope, wrong tenant)
10. Report any malformed payloads, duplicate events, or tenant isolation problems
"""

import os
import sys
import json
import uuid
import requests
import pymongo
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List


class RoomBlockReleaseSemanticMigrationTest:
    def __init__(self):
        # Get backend URL from environment
        self.backend_url = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
        if not self.backend_url:
            raise Exception("REACT_APP_BACKEND_URL not found in environment")
        
        print(f"🔗 Backend URL: {self.backend_url}")
        
        # Setup MongoDB connection for direct validation
        self.mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.mongo_client = pymongo.MongoClient(self.mongo_url)
            self.db = self.mongo_client.hotel_pms  # Backend uses hotel_pms database
            print(f"✅ MongoDB connection established: {self.mongo_url}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
        
        # Test session
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        # Test credentials
        self.email = "demo@hotel.com"
        self.password = "demo123"
        
        # Test state
        self.token = None
        self.tenant_id = None
        self.property_id = None
        self.test_room = None
        self.test_dates = None
        
        # Results tracking
        self.results = []
        self.critical_issues = []
        self.minor_issues = []
    
    def log_result(self, test_name: str, passed: bool, details: str = "", critical: bool = False):
        """Log test result and categorize issues"""
        result = {
            'test': test_name,
            'passed': passed,
            'details': details,
            'critical': critical
        }
        self.results.append(result)
        
        if not passed:
            if critical:
                self.critical_issues.append(f"❌ CRITICAL: {test_name} - {details}")
            else:
                self.minor_issues.append(f"⚠️  Minor: {test_name} - {details}")
        
        print(f"{'✅' if passed else ('❌' if critical else '⚠️ ')} {test_name}: {'PASS' if passed else 'FAIL'}")
        if details and not passed:
            print(f"   Details: {details}")
    
    def authenticate(self) -> bool:
        """Test Case 1: Authenticate and obtain bearer token"""
        try:
            print("\n🔐 Testing Authentication...")
            
            response = self.session.post(f'{self.backend_url}/api/auth/login', json={
                'email': self.email,
                'password': self.password
            })
            
            if response.status_code != 200:
                self.log_result("Authentication", False, 
                              f"Login failed with status {response.status_code}: {response.text}", 
                              critical=True)
                return False
            
            data = response.json()
            if 'access_token' not in data or 'user' not in data:
                self.log_result("Authentication", False, 
                              f"Invalid login response structure: {data}", 
                              critical=True)
                return False
            
            self.token = data['access_token']
            self.tenant_id = data['user']['tenant_id']
            self.property_id = self.tenant_id  # In single-tenant mode
            
            # Update session with bearer token
            self.session.headers.update({'Authorization': f'Bearer {self.token}'})
            
            self.log_result("Authentication", True, 
                          f"Token obtained, tenant_id: {self.tenant_id}")
            return True
            
        except Exception as e:
            self.log_result("Authentication", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def find_available_room(self) -> bool:
        """Find an available room for testing future dates"""
        try:
            print("\n🏨 Finding available room for testing...")
            
            # Use future dates (60-63 days out) to avoid conflicts
            start_date = (datetime.now().date() + timedelta(days=60)).isoformat()
            end_date = (datetime.now().date() + timedelta(days=63)).isoformat()
            
            response = self.session.get(
                f'{self.backend_url}/api/pms/rooms/availability'
                f'?check_in={start_date}&check_out={end_date}'
            )
            
            if response.status_code != 200:
                self.log_result("Find Available Room", False, 
                              f"Availability check failed: {response.status_code}", 
                              critical=True)
                return False
            
            availability = response.json()
            available_rooms = [room for room in availability if room.get('available') is True]
            
            if not available_rooms:
                self.log_result("Find Available Room", False, 
                              "No available rooms found for test date range", 
                              critical=True)
                return False
            
            self.test_room = available_rooms[0]
            self.test_dates = {'start_date': start_date, 'end_date': end_date}
            
            self.log_result("Find Available Room", True, 
                          f"Room {self.test_room['room_number']} available for {start_date} to {end_date}")
            return True
            
        except Exception as e:
            self.log_result("Find Available Room", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def create_room_block(self) -> Optional[Dict[str, Any]]:
        """Test Case 2: Create a room block using POST /api/pms/room-blocks with Idempotency-Key"""
        try:
            print("\n🔒 Testing Room Block Creation...")
            
            idempotency_key = f"test-create-{uuid.uuid4()}"
            
            payload = {
                'room_id': self.test_room['id'],
                'type': 'out_of_order',
                'reason': f'RoomBlockRelease semantic migration test - {uuid.uuid4().hex[:8]}',
                'details': 'Testing semantic ReleaseRoomBlockService migration',
                'start_date': self.test_dates['start_date'],
                'end_date': self.test_dates['end_date'],
                'allow_sell': False,
            }
            
            response = self.session.post(
                f'{self.backend_url}/api/pms/room-blocks',
                json=payload,
                headers={'Idempotency-Key': idempotency_key}
            )
            
            if response.status_code != 200:
                self.log_result("Create Room Block", False, 
                              f"Block creation failed: {response.status_code} - {response.text}", 
                              critical=True)
                return None
            
            data = response.json()
            
            # Validate response structure
            required_fields = ['message', 'block']
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                self.log_result("Create Room Block Response Structure", False, 
                              f"Missing fields: {missing_fields}", critical=True)
                return None
            
            block = data['block']
            block_required_fields = ['id', 'room_id', 'type', 'status', 'start_date', 'end_date']
            missing_block_fields = [field for field in block_required_fields if field not in block]
            if missing_block_fields:
                self.log_result("Create Room Block Structure", False, 
                              f"Missing block fields: {missing_block_fields}", critical=True)
                return None
            
            self.log_result("Create Room Block", True, 
                          f"Block created with ID: {block['id']}")
            return block
            
        except Exception as e:
            self.log_result("Create Room Block", False, f"Exception: {str(e)}", critical=True)
            return None
    
    def release_room_block(self, block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Test Case 3: Release room block using legacy endpoint with semantic service"""
        try:
            print("\n🔓 Testing Room Block Release...")
            
            idempotency_key = f"test-release-{uuid.uuid4()}"
            
            response = self.session.post(
                f'{self.backend_url}/api/pms/room-blocks/{block["id"]}/cancel',
                headers={'Idempotency-Key': idempotency_key}
            )
            
            if response.status_code != 200:
                self.log_result("Release Room Block", False, 
                              f"Block release failed: {response.status_code} - {response.text}", 
                              critical=True)
                return None
            
            data = response.json()
            self.log_result("Release Room Block", True, 
                          f"Block released: {block['id']}")
            return data
            
        except Exception as e:
            self.log_result("Release Room Block", False, f"Exception: {str(e)}", critical=True)
            return None
    
    def validate_release_response_structure(self, release_response: Dict[str, Any], 
                                          block: Dict[str, Any]) -> bool:
        """Test Case 4: Validate response structure"""
        try:
            print("\n📋 Validating Release Response Structure...")
            
            required_fields = [
                'message', 'block_id', 'room_block_id', 'status', 
                'released_at', 'property_id', 'room_id', 'correlation_id'
            ]
            
            missing_fields = []
            for field in required_fields:
                if field not in release_response:
                    missing_fields.append(field)
            
            if missing_fields:
                self.log_result("Release Response Structure", False, 
                              f"Missing required fields: {missing_fields}", critical=True)
                return False
            
            # Validate field values
            validations = [
                (release_response['block_id'] == block['id'], "block_id matches"),
                (release_response['room_block_id'] == block['id'], "room_block_id matches"),
                (release_response['status'] == 'released', "status is 'released'"),
                (release_response['property_id'] == self.property_id, "property_id matches"),
                (release_response['room_id'] == self.test_room['id'], "room_id matches"),
                (release_response['released_at'] is not None, "released_at is present"),
                (release_response['correlation_id'] is not None, "correlation_id is present"),
            ]
            
            failed_validations = [desc for valid, desc in validations if not valid]
            
            if failed_validations:
                self.log_result("Release Response Validation", False, 
                              f"Failed validations: {failed_validations}", critical=True)
                return False
            
            self.log_result("Release Response Structure", True, 
                          "All required fields present and valid")
            return True
            
        except Exception as e:
            self.log_result("Release Response Structure", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def verify_outbox_event(self, block: Dict[str, Any]) -> bool:
        """Test Case 5: Verify outbox event inventory.released.v1 exists and is not duplicated"""
        try:
            print("\n📤 Verifying Outbox Event...")
            
            # Query outbox events directly from MongoDB
            outbox_query = {
                'room_block_id': block['id'],
                'event_type': 'inventory.released.v1',
                'tenant_id': self.tenant_id
            }
            
            events = list(self.db.outbox_events.find(outbox_query, {'_id': 0}))
            
            if len(events) == 0:
                self.log_result("Outbox Event Exists", False, 
                              f"No inventory.released.v1 event found for block {block['id']}", 
                              critical=True)
                return False
            
            if len(events) > 1:
                self.log_result("Outbox Event Duplication", False, 
                              f"Multiple events found ({len(events)}) - duplicate events detected", 
                              critical=True)
                return False
            
            event = events[0]
            
            # Validate event structure
            required_event_fields = [
                'event_type', 'tenant_id', 'room_block_id', 'payload', 
                'property_id', 'released_at', 'status', 'created_at'
            ]
            
            missing_fields = [field for field in required_event_fields if field not in event]
            if missing_fields:
                self.log_result("Outbox Event Structure", False, 
                              f"Missing event fields: {missing_fields}", critical=True)
                return False
            
            # Validate payload structure
            payload = event.get('payload', {})
            required_payload_fields = [
                'release_scope', 'effective_date_range', 'actor_reference', 
                'reason', 'source', 'block_type', 'allow_sell'
            ]
            
            missing_payload_fields = [field for field in required_payload_fields if field not in payload]
            if missing_payload_fields:
                self.log_result("Outbox Event Payload", False, 
                              f"Missing payload fields: {missing_payload_fields}", critical=True)
                return False
            
            # Validate payload values
            payload_validations = [
                (payload['source'] == 'semantic_inventory_service', "source is semantic_inventory_service"),
                (payload['release_scope']['room_id'] == self.test_room['id'], "room_id matches in release_scope"),
                (payload['effective_date_range']['start_date'] == block['start_date'], "start_date matches"),
                (payload['effective_date_range']['end_date'] == block['end_date'], "end_date matches"),
                (payload['actor_reference']['actor_id'] is not None, "actor_id is present"),
            ]
            
            failed_payload_validations = [desc for valid, desc in payload_validations if not valid]
            if failed_payload_validations:
                self.log_result("Outbox Event Payload Validation", False, 
                              f"Failed payload validations: {failed_payload_validations}", critical=True)
                return False
            
            self.log_result("Outbox Event", True, 
                          f"inventory.released.v1 event exists and validated for block {block['id']}")
            return True
            
        except Exception as e:
            self.log_result("Outbox Event Verification", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def verify_audit_log(self, block: Dict[str, Any]) -> bool:
        """Test Case 6: Verify audit log room_block_released exists"""
        try:
            print("\n📝 Verifying Audit Log...")
            
            # Query audit logs directly from MongoDB
            audit_query = {
                'entity_type': 'room_block',
                'entity_id': block['id'],
                'action': 'room_block_released',
                'tenant_id': self.tenant_id
            }
            
            audit_logs = list(self.db.audit_logs.find(audit_query, {'_id': 0}))
            
            if len(audit_logs) == 0:
                self.log_result("Audit Log Exists", False, 
                              f"No room_block_released audit log found for block {block['id']}", 
                              critical=True)
                return False
            
            audit_log = audit_logs[0]  # Take the first one
            
            # Validate audit log structure
            required_audit_fields = [
                'entity_type', 'entity_id', 'action', 'tenant_id', 
                'property_id', 'actor_id', 'correlation_id'
            ]
            
            missing_audit_fields = [field for field in required_audit_fields if field not in audit_log]
            if missing_audit_fields:
                self.log_result("Audit Log Structure", False, 
                              f"Missing audit fields: {missing_audit_fields}", critical=True)
                return False
            
            self.log_result("Audit Log", True, 
                          f"room_block_released audit log exists for block {block['id']}")
            return True
            
        except Exception as e:
            self.log_result("Audit Log Verification", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def verify_availability_effects(self, block: Dict[str, Any]) -> bool:
        """Test Case 7: Verify availability effects before and after release"""
        try:
            print("\n🏨 Verifying Availability Effects...")
            
            start_date = self.test_dates['start_date']
            end_date = self.test_dates['end_date']
            
            # Check availability after release
            response = self.session.get(
                f'{self.backend_url}/api/pms/rooms/availability'
                f'?check_in={start_date}&check_out={end_date}'
            )
            
            if response.status_code != 200:
                self.log_result("Availability Check After Release", False, 
                              f"Availability check failed: {response.status_code}", critical=True)
                return False
            
            availability = response.json()
            released_room = next((room for room in availability if room['id'] == self.test_room['id']), None)
            
            if not released_room:
                self.log_result("Room Found in Availability", False, 
                              f"Room {self.test_room['id']} not found in availability response", 
                              critical=True)
                return False
            
            if not released_room.get('available'):
                self.log_result("Room Available After Release", False, 
                              f"Room {self.test_room['room_number']} is not available after release", 
                              critical=True)
                return False
            
            self.log_result("Availability Effects", True, 
                          f"Room {self.test_room['room_number']} is available after block release")
            return True
            
        except Exception as e:
            self.log_result("Availability Effects", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def test_idempotency_behavior(self) -> bool:
        """Test Case 8: Verify idempotency behavior"""
        try:
            print("\n🔄 Testing Idempotency Behavior...")
            
            # First, create a new block for idempotency testing
            test_block = self.create_room_block()
            if not test_block:
                self.log_result("Idempotency Setup", False, "Failed to create block for idempotency test", critical=True)
                return False
            
            # Test 1: Same Idempotency-Key returns same response
            idempotency_key = f"test-idempotency-{uuid.uuid4()}"
            
            first_response = self.session.post(
                f'{self.backend_url}/api/pms/room-blocks/{test_block["id"]}/cancel',
                headers={'Idempotency-Key': idempotency_key}
            )
            
            second_response = self.session.post(
                f'{self.backend_url}/api/pms/room-blocks/{test_block["id"]}/cancel',
                headers={'Idempotency-Key': idempotency_key}
            )
            
            if first_response.status_code != 200 or second_response.status_code != 200:
                self.log_result("Idempotency Same Key", False, 
                              f"Failed responses: {first_response.status_code}, {second_response.status_code}", 
                              critical=True)
                return False
            
            if first_response.json() != second_response.json():
                self.log_result("Idempotency Same Key", False, 
                              "Different responses for same Idempotency-Key", critical=True)
                return False
            
            # Test 2: Different Idempotency-Key after release returns deterministic final state
            different_key = f"test-idempotency-different-{uuid.uuid4()}"
            
            third_response = self.session.post(
                f'{self.backend_url}/api/pms/room-blocks/{test_block["id"]}/cancel',
                headers={'Idempotency-Key': different_key}
            )
            
            if third_response.status_code != 200:
                self.log_result("Idempotency Different Key", False, 
                              f"Failed response: {third_response.status_code}", critical=True)
                return False
            
            # Verify no duplicate events were created
            outbox_count = self.db.outbox_events.count_documents({
                'room_block_id': test_block['id'],
                'event_type': 'inventory.released.v1'
            })
            
            if outbox_count != 1:
                self.log_result("Idempotency Event Duplication", False, 
                              f"Expected 1 event, found {outbox_count}", critical=True)
                return False
            
            self.log_result("Idempotency Behavior", True, 
                          "Same key returns same response, different key is deterministic, no duplicate events")
            return True
            
        except Exception as e:
            self.log_result("Idempotency Behavior", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def test_validations(self) -> bool:
        """Test Case 9: Verify validations"""
        try:
            print("\n✅ Testing Validations...")
            
            # Create a block for validation tests
            test_block = self.create_room_block()
            if not test_block:
                return False
            
            # Test 1: Missing Idempotency-Key should return 400
            missing_key_response = self.session.post(
                f'{self.backend_url}/api/pms/room-blocks/{test_block["id"]}/cancel'
            )
            
            if missing_key_response.status_code != 400:
                self.log_result("Missing Idempotency-Key Validation", False, 
                              f"Expected 400, got {missing_key_response.status_code}", critical=True)
                return False
            
            if 'Idempotency-Key' not in missing_key_response.text:
                self.log_result("Missing Idempotency-Key Error Message", False, 
                              "Error message doesn't mention Idempotency-Key")
            
            # Test 2: Wrong property scope should return 403
            wrong_property_response = self.session.post(
                f'{self.backend_url}/api/pms/room-blocks/{test_block["id"]}/cancel',
                headers={
                    'Idempotency-Key': f'test-wrong-property-{uuid.uuid4()}',
                    'x-property-id': 'wrong-property-id'
                }
            )
            
            if wrong_property_response.status_code != 403:
                self.log_result("Wrong Property Scope Validation", False, 
                              f"Expected 403, got {wrong_property_response.status_code}", critical=True)
            
            # Test 3: Wrong tenant cannot release another tenant's block
            # First register a new tenant
            register_suffix = uuid.uuid4().hex[:8]
            register_response = requests.post(
                f'{self.backend_url}/api/auth/register',
                json={
                    'property_name': f'Test Property {register_suffix}',
                    'email': f'test-{register_suffix}@example.com',
                    'password': 'test123',
                    'name': f'Test User {register_suffix}',
                    'phone': '+905550000000',
                    'address': 'Test Address',
                    'location': 'Test City',
                }
            )
            
            if register_response.status_code == 200:
                other_token = register_response.json()['access_token']
                
                wrong_tenant_response = requests.post(
                    f'{self.backend_url}/api/pms/room-blocks/{test_block["id"]}/cancel',
                    headers={
                        'Authorization': f'Bearer {other_token}',
                        'Content-Type': 'application/json',
                        'Idempotency-Key': f'test-wrong-tenant-{uuid.uuid4()}',
                    }
                )
                
                if wrong_tenant_response.status_code != 404:
                    self.log_result("Wrong Tenant Isolation", False, 
                                  f"Expected 404, got {wrong_tenant_response.status_code}", critical=True)
                    return False
            
            self.log_result("Validations", True, 
                          "Missing key->400, wrong property->403, tenant isolation working")
            return True
            
        except Exception as e:
            self.log_result("Validations", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def run_comprehensive_test(self) -> bool:
        """Run all test cases in sequence"""
        print("🚀 Starting RoomBlockRelease Semantic Migration Test Suite")
        print("=" * 60)
        
        # Test Case 1: Authentication
        if not self.authenticate():
            return False
        
        # Setup: Find available room
        if not self.find_available_room():
            return False
        
        # Test Case 2: Create room block
        main_block = self.create_room_block()
        if not main_block:
            return False
        
        # Verify block was created and room is now unavailable
        try:
            start_date = self.test_dates['start_date']
            end_date = self.test_dates['end_date']
            
            availability_response = self.session.get(
                f'{self.backend_url}/api/pms/rooms/availability'
                f'?check_in={start_date}&check_out={end_date}'
            )
            
            if availability_response.status_code == 200:
                availability = availability_response.json()
                blocked_room = next((room for room in availability if room['id'] == self.test_room['id']), None)
                
                if blocked_room and not blocked_room.get('available'):
                    self.log_result("Room Blocked Before Release", True, 
                                  f"Room {self.test_room['room_number']} correctly blocked")
                else:
                    self.log_result("Room Blocked Before Release", False, 
                                  f"Room {self.test_room['room_number']} not blocked as expected", critical=True)
        except Exception as e:
            self.log_result("Room Blocked Before Release", False, f"Exception: {str(e)}")
        
        # Test Case 3: Release room block
        release_response = self.release_room_block(main_block)
        if not release_response:
            return False
        
        # Test Case 4: Validate response structure
        if not self.validate_release_response_structure(release_response, main_block):
            return False
        
        # Test Case 5: Verify outbox event
        if not self.verify_outbox_event(main_block):
            return False
        
        # Test Case 6: Verify audit log
        if not self.verify_audit_log(main_block):
            return False
        
        # Test Case 7: Verify availability effects
        if not self.verify_availability_effects(main_block):
            return False
        
        # Test Case 8: Test idempotency behavior
        if not self.test_idempotency_behavior():
            return False
        
        # Test Case 9: Test validations
        if not self.test_validations():
            return False
        
        return True
    
    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 60)
        print("🎯 ROOMBLOCKRELEASE SEMANTIC MIGRATION TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['passed'])
        failed_tests = total_tests - passed_tests
        
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"🎯 Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if self.critical_issues:
            print(f"\n🚨 CRITICAL ISSUES ({len(self.critical_issues)}):")
            for issue in self.critical_issues:
                print(f"  {issue}")
        
        if self.minor_issues:
            print(f"\n⚠️  MINOR ISSUES ({len(self.minor_issues)}):")
            for issue in self.minor_issues:
                print(f"  {issue}")
        
        if not self.critical_issues and not self.minor_issues:
            print("\n🎉 ALL TESTS PASSED - RoomBlockRelease semantic migration is working correctly!")
        
        print("\n📋 DETAILED TEST RESULTS:")
        for result in self.results:
            status = "✅ PASS" if result['passed'] else ("❌ CRITICAL FAIL" if result['critical'] else "⚠️  MINOR FAIL")
            print(f"  {status:<16} {result['test']}")
            if result['details'] and not result['passed']:
                print(f"    └─ {result['details']}")


def main():
    """Main test execution"""
    try:
        tester = RoomBlockReleaseSemanticMigrationTest()
        success = tester.run_comprehensive_test()
        tester.print_summary()
        
        # Return appropriate exit code
        if tester.critical_issues:
            print("\n❌ CRITICAL ISSUES DETECTED - MIGRATION HAS PROBLEMS")
            sys.exit(1)
        elif not success:
            print("\n⚠️  SOME TESTS FAILED - CHECK SUMMARY ABOVE")
            sys.exit(1)
        else:
            print("\n✅ ALL TESTS PASSED - ROOMBLOCKRELEASE SEMANTIC MIGRATION WORKING")
            sys.exit(0)
            
    except Exception as e:
        print(f"\n💥 FATAL ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()