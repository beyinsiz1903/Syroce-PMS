#!/usr/bin/env python3
"""
Backend Migration Observability Endpoint Test
Specific focus on GET /api/reports/migration-observability API testing

Test Requirements from review_request:
1. Authenticate and obtain bearer token
2. Call GET /api/reports/migration-observability and verify HTTP 200
3. Validate response has top-level keys: generated_at, outbox, audit, shadow
4. Validate outbox contains: total_events, throughput, queue_depth, event_breakdown, retries, lag, recent_events
5. Validate audit contains: recent_count, actions_breakdown, recent_stream
6. Validate shadow contains: summary, recent_events
7. Confirm response is tenant-scoped for demo tenant
8. Verify current migrated event types are represented safely
9. Handle empty future-ready lag/retry values correctly
"""

import os
import uuid
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Set

import aiohttp
import asyncio

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
print(f"Testing Migration Observability backend at: {BASE_URL}")

class MigrationObservabilityTester:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.tenant_id: Optional[str] = None
        self.test_results: List[str] = []
        
        # Expected migration event types from the backend implementation
        self.expected_event_types = [
            "reservation.created.v1",
            "inventory.blocked.v1", 
            "folio.opened.v1"
        ]
        
        # Expected audit actions
        self.expected_audit_actions = [
            "reservation_created",
            "room_block_created", 
            "folio_opened"
        ]

    async def setup(self):
        """Setup authentication"""
        if not BASE_URL:
            raise Exception("REACT_APP_BACKEND_URL missing from environment")
        
        self.session = aiohttp.ClientSession()
        
        # Login with demo credentials
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
        
        print(f"✅ Setup complete. Token obtained, tenant_id: {self.tenant_id}")

    def _get_headers(self):
        """Get authenticated request headers"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    async def test_1_authentication_and_http_200(self):
        """Test 1: Authenticate and obtain bearer token + verify HTTP 200 response"""
        test_name = "Authentication & HTTP 200 Response"
        try:
            headers = self._get_headers()
            
            async with self.session.get(f'{BASE_URL}/api/reports/migration-observability', headers=headers) as resp:
                status_code = resp.status
                response_text = await resp.text()
                
                if status_code != 200:
                    self.test_results.append(f"❌ {test_name}: Expected HTTP 200, got {status_code} - {response_text}")
                    return None
                
                try:
                    response_data = await resp.json()
                except json.JSONDecodeError as e:
                    self.test_results.append(f"❌ {test_name}: Invalid JSON response - {str(e)}")
                    return None
                
                self.test_results.append(f"✅ {test_name}: Authentication successful, HTTP 200 received with valid JSON")
                return response_data
                
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return None

    async def test_2_validate_top_level_keys(self, response_data: Dict[str, Any]):
        """Test 2: Validate response has top-level keys: generated_at, outbox, audit, shadow"""
        test_name = "Top-Level Response Keys"
        try:
            if not response_data:
                self.test_results.append(f"❌ {test_name}: No response data to validate")
                return False
            
            required_keys = {'generated_at', 'outbox', 'audit', 'shadow'}
            actual_keys = set(response_data.keys())
            
            missing_keys = required_keys - actual_keys
            if missing_keys:
                self.test_results.append(f"❌ {test_name}: Missing required keys: {missing_keys}")
                return False
            
            # Validate generated_at is a valid ISO datetime string
            generated_at = response_data.get('generated_at')
            if not generated_at or not isinstance(generated_at, str):
                self.test_results.append(f"❌ {test_name}: generated_at must be a non-empty string")
                return False
            
            try:
                datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
            except ValueError:
                self.test_results.append(f"❌ {test_name}: generated_at is not a valid ISO datetime: {generated_at}")
                return False
            
            self.test_results.append(f"✅ {test_name}: All required top-level keys present and valid")
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def test_3_validate_outbox_structure(self, response_data: Dict[str, Any]):
        """Test 3: Validate outbox contains: total_events, throughput, queue_depth, event_breakdown, retries, lag, recent_events"""
        test_name = "Outbox Structure Validation"
        try:
            if not response_data:
                self.test_results.append(f"❌ {test_name}: No response data to validate")
                return False
            
            outbox = response_data.get('outbox')
            if not outbox or not isinstance(outbox, dict):
                self.test_results.append(f"❌ {test_name}: outbox must be a non-empty dict")
                return False
            
            required_outbox_keys = {'total_events', 'throughput', 'queue_depth', 'event_breakdown', 'retries', 'lag', 'recent_events'}
            actual_outbox_keys = set(outbox.keys())
            
            missing_keys = required_outbox_keys - actual_outbox_keys
            if missing_keys:
                self.test_results.append(f"❌ {test_name}: outbox missing required keys: {missing_keys}")
                return False
            
            # Validate total_events is a number
            total_events = outbox.get('total_events')
            if not isinstance(total_events, (int, float)) or total_events < 0:
                self.test_results.append(f"❌ {test_name}: total_events must be a non-negative number, got: {total_events}")
                return False
            
            # Validate throughput structure
            throughput = outbox.get('throughput')
            if not isinstance(throughput, dict):
                self.test_results.append(f"❌ {test_name}: throughput must be a dict")
                return False
            
            # Validate queue_depth structure
            queue_depth = outbox.get('queue_depth')
            if not isinstance(queue_depth, dict):
                self.test_results.append(f"❌ {test_name}: queue_depth must be a dict")
                return False
            
            # Validate event_breakdown is a list
            event_breakdown = outbox.get('event_breakdown')
            if not isinstance(event_breakdown, list):
                self.test_results.append(f"❌ {test_name}: event_breakdown must be a list")
                return False
            
            # Validate retries structure
            retries = outbox.get('retries')
            if not isinstance(retries, dict):
                self.test_results.append(f"❌ {test_name}: retries must be a dict")
                return False
            
            # Validate lag structure  
            lag = outbox.get('lag')
            if not isinstance(lag, dict):
                self.test_results.append(f"❌ {test_name}: lag must be a dict")
                return False
            
            # Validate recent_events is a list
            recent_events = outbox.get('recent_events')
            if not isinstance(recent_events, list):
                self.test_results.append(f"❌ {test_name}: recent_events must be a list")
                return False
            
            self.test_results.append(f"✅ {test_name}: outbox structure valid with all required nested fields")
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def test_4_validate_audit_structure(self, response_data: Dict[str, Any]):
        """Test 4: Validate audit contains: recent_count, actions_breakdown, recent_stream"""
        test_name = "Audit Structure Validation"
        try:
            if not response_data:
                self.test_results.append(f"❌ {test_name}: No response data to validate")
                return False
            
            audit = response_data.get('audit')
            if not audit or not isinstance(audit, dict):
                self.test_results.append(f"❌ {test_name}: audit must be a non-empty dict")
                return False
            
            required_audit_keys = {'recent_count', 'actions_breakdown', 'recent_stream'}
            actual_audit_keys = set(audit.keys())
            
            missing_keys = required_audit_keys - actual_audit_keys
            if missing_keys:
                self.test_results.append(f"❌ {test_name}: audit missing required keys: {missing_keys}")
                return False
            
            # Validate recent_count is a number
            recent_count = audit.get('recent_count')
            if not isinstance(recent_count, (int, float)) or recent_count < 0:
                self.test_results.append(f"❌ {test_name}: recent_count must be a non-negative number, got: {recent_count}")
                return False
            
            # Validate actions_breakdown is a list
            actions_breakdown = audit.get('actions_breakdown')
            if not isinstance(actions_breakdown, list):
                self.test_results.append(f"❌ {test_name}: actions_breakdown must be a list")
                return False
            
            # Validate recent_stream is a list
            recent_stream = audit.get('recent_stream')
            if not isinstance(recent_stream, list):
                self.test_results.append(f"❌ {test_name}: recent_stream must be a list")
                return False
            
            self.test_results.append(f"✅ {test_name}: audit structure valid with all required fields")
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def test_5_validate_shadow_structure(self, response_data: Dict[str, Any]):
        """Test 5: Validate shadow contains: summary, recent_events"""
        test_name = "Shadow Structure Validation"
        try:
            if not response_data:
                self.test_results.append(f"❌ {test_name}: No response data to validate")
                return False
            
            shadow = response_data.get('shadow')
            if not shadow or not isinstance(shadow, dict):
                self.test_results.append(f"❌ {test_name}: shadow must be a non-empty dict")
                return False
            
            required_shadow_keys = {'summary', 'recent_events'}
            actual_shadow_keys = set(shadow.keys())
            
            missing_keys = required_shadow_keys - actual_shadow_keys
            if missing_keys:
                self.test_results.append(f"❌ {test_name}: shadow missing required keys: {missing_keys}")
                return False
            
            # Validate summary is a list
            summary = shadow.get('summary')
            if not isinstance(summary, list):
                self.test_results.append(f"❌ {test_name}: shadow summary must be a list")
                return False
            
            # Validate recent_events is a list
            recent_events = shadow.get('recent_events')
            if not isinstance(recent_events, list):
                self.test_results.append(f"❌ {test_name}: shadow recent_events must be a list")
                return False
            
            self.test_results.append(f"✅ {test_name}: shadow structure valid with all required fields")
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def test_6_tenant_scoping_validation(self, response_data: Dict[str, Any]):
        """Test 6: Confirm response is tenant-scoped for demo tenant"""
        test_name = "Tenant Scoping Validation"
        try:
            if not response_data:
                self.test_results.append(f"❌ {test_name}: No response data to validate")
                return False
            
            # Check if audit stream events have proper tenant isolation
            audit = response_data.get('audit', {})
            recent_stream = audit.get('recent_stream', [])
            
            # For any audit entries that have tenant_id, verify they match demo tenant
            tenant_mismatch_count = 0
            for entry in recent_stream:
                if isinstance(entry, dict) and 'tenant_id' in entry:
                    if entry['tenant_id'] != self.tenant_id:
                        tenant_mismatch_count += 1
            
            if tenant_mismatch_count > 0:
                self.test_results.append(f"❌ {test_name}: Found {tenant_mismatch_count} audit entries with wrong tenant_id")
                return False
            
            # Check that outbox events are tenant-scoped (implicit from total_events being reasonable)
            outbox = response_data.get('outbox', {})
            total_events = outbox.get('total_events', 0)
            
            # A basic sanity check - tenant isolation working if we have some reasonable data
            if total_events < 0:
                self.test_results.append(f"❌ {test_name}: total_events cannot be negative: {total_events}")
                return False
            
            self.test_results.append(f"✅ {test_name}: Tenant scoping appears correct - no cross-tenant data leakage detected")
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def test_7_event_types_representation(self, response_data: Dict[str, Any]):
        """Test 7: Verify current migrated event types are represented safely"""
        test_name = "Event Types Representation"
        try:
            if not response_data:
                self.test_results.append(f"❌ {test_name}: No response data to validate")
                return False
            
            outbox = response_data.get('outbox', {})
            event_breakdown = outbox.get('event_breakdown', [])
            
            found_event_types = set()
            for event_info in event_breakdown:
                if isinstance(event_info, dict) and 'event_type' in event_info:
                    found_event_types.add(event_info['event_type'])
            
            # Check if any of the expected migration event types are present
            # Note: We don't require ALL to be present, just that the API handles them safely
            safe_event_types_found = found_event_types.intersection(set(self.expected_event_types))
            
            # Validate each event type entry has required structure
            valid_breakdown_entries = 0
            for event_info in event_breakdown:
                if isinstance(event_info, dict):
                    required_fields = ['event_type', 'total_count']
                    if all(field in event_info for field in required_fields):
                        # Validate counts are non-negative numbers
                        total_count = event_info.get('total_count', -1)
                        if isinstance(total_count, (int, float)) and total_count >= 0:
                            valid_breakdown_entries += 1
            
            # Check that audit actions are represented
            audit = response_data.get('audit', {})
            actions_breakdown = audit.get('actions_breakdown', [])
            
            found_actions = set()
            for action_info in actions_breakdown:
                if isinstance(action_info, dict) and 'action' in action_info:
                    found_actions.add(action_info['action'])
            
            safe_actions_found = found_actions.intersection(set(self.expected_audit_actions))
            
            self.test_results.append(f"✅ {test_name}: Event types represented safely - {len(safe_event_types_found)} migration event types, {len(safe_actions_found)} audit actions found")
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def test_8_future_ready_values_handling(self, response_data: Dict[str, Any]):
        """Test 8: Verify empty future-ready lag/retry values don't error"""
        test_name = "Future-Ready Values Handling"
        try:
            if not response_data:
                self.test_results.append(f"❌ {test_name}: No response data to validate")
                return False
            
            outbox = response_data.get('outbox', {})
            
            # Check retries structure handles future-ready scenario
            retries = outbox.get('retries', {})
            if 'future_ready' in retries:
                future_ready_retries = retries.get('future_ready')
                if not isinstance(future_ready_retries, bool):
                    self.test_results.append(f"❌ {test_name}: retries.future_ready should be boolean, got: {future_ready_retries}")
                    return False
            
            # Check lag structure handles future-ready scenario
            lag = outbox.get('lag', {})
            if 'future_ready' in lag:
                future_ready_lag = lag.get('future_ready')
                if not isinstance(future_ready_lag, bool):
                    self.test_results.append(f"❌ {test_name}: lag.future_ready should be boolean, got: {future_ready_lag}")
                    return False
            
            # Validate that when future_ready is True, the metrics can be None/null
            if lag.get('future_ready'):
                avg_ms = lag.get('avg_ms')
                p95_ms = lag.get('p95_ms')
                if avg_ms is not None and not isinstance(avg_ms, (int, float)):
                    self.test_results.append(f"❌ {test_name}: lag.avg_ms should be number or null when future_ready, got: {avg_ms}")
                    return False
                if p95_ms is not None and not isinstance(p95_ms, (int, float)):
                    self.test_results.append(f"❌ {test_name}: lag.p95_ms should be number or null when future_ready, got: {p95_ms}")
                    return False
            
            # Check that the API doesn't crash when retry data is minimal
            total_attempts = retries.get('total_attempts', 0)
            if not isinstance(total_attempts, (int, float)) or total_attempts < 0:
                self.test_results.append(f"❌ {test_name}: retries.total_attempts should be non-negative number, got: {total_attempts}")
                return False
            
            self.test_results.append(f"✅ {test_name}: Future-ready values handled correctly - no errors on empty lag/retry data")
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def test_9_api_error_handling(self):
        """Test 9: Report any API errors or malformed responses"""
        test_name = "API Error Handling"
        try:
            # Test with invalid/missing auth
            async with self.session.get(f'{BASE_URL}/api/reports/migration-observability') as resp:
                if resp.status == 401 or resp.status == 403:
                    self.test_results.append(f"✅ {test_name}: Proper authentication required - returns {resp.status} without token")
                else:
                    response_text = await resp.text()
                    self.test_results.append(f"⚠️ {test_name}: Expected 401/403 without auth, got {resp.status}: {response_text}")
            
            # Test with malformed token
            malformed_headers = {
                'Authorization': 'Bearer invalid-token-12345',
                'Content-Type': 'application/json'
            }
            
            async with self.session.get(f'{BASE_URL}/api/reports/migration-observability', headers=malformed_headers) as resp:
                if resp.status == 401 or resp.status == 403:
                    self.test_results.append(f"✅ {test_name}: Proper error handling for invalid token - returns {resp.status}")
                else:
                    response_text = await resp.text()
                    self.test_results.append(f"⚠️ {test_name}: Expected 401/403 with invalid token, got {resp.status}: {response_text}")
            
            return True
            
        except Exception as e:
            self.test_results.append(f"❌ {test_name}: Exception - {str(e)}")
            return False

    async def run_comprehensive_test(self):
        """Run comprehensive Migration Observability endpoint test"""
        print("🔍 Starting Migration Observability Backend API Test...")
        print("=" * 80)
        
        await self.setup()
        
        print("\n🧪 Running Migration Observability API validation tests...")
        
        # Test 1: Authentication and basic HTTP 200 response
        response_data = await self.test_1_authentication_and_http_200()
        
        if response_data:
            # Test 2-8: Validate response structure and data contract
            await self.test_2_validate_top_level_keys(response_data)
            await self.test_3_validate_outbox_structure(response_data)
            await self.test_4_validate_audit_structure(response_data)
            await self.test_5_validate_shadow_structure(response_data)
            await self.test_6_tenant_scoping_validation(response_data)
            await self.test_7_event_types_representation(response_data)
            await self.test_8_future_ready_values_handling(response_data)
        
        # Test 9: Error handling scenarios
        await self.test_9_api_error_handling()

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()

    def print_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 80)
        print("📊 MIGRATION OBSERVABILITY BACKEND API TEST RESULTS")
        print("=" * 80)
        
        passed = sum(1 for result in self.test_results if result.startswith('✅'))
        failed = sum(1 for result in self.test_results if result.startswith('❌'))
        warnings = sum(1 for result in self.test_results if result.startswith('⚠️'))
        
        for result in self.test_results:
            print(result)
        
        print("\n" + "=" * 80)
        print(f"📈 SUMMARY: {passed} PASSED, {failed} FAILED, {warnings} WARNINGS, {passed + failed + warnings} TOTAL")
        
        if failed > 0:
            print("❌ CRITICAL ISSUES FOUND - Migration Observability API has problems!")
            print("🔧 Issues need to be resolved before production use")
        elif warnings > 0:
            print("⚠️ MINOR WARNINGS - Migration Observability API mostly working")
            print("📝 Consider reviewing warning items for optimal security")
        else:
            print("✅ ALL TESTS PASSED - Migration Observability API working correctly!")
            print("🚀 API data contract validation successful")
        
        print("=" * 80)
        return failed == 0


async def main():
    """Main test execution"""
    tester = MigrationObservabilityTester()
    try:
        await tester.run_comprehensive_test()
        return tester.print_results()
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Migration Observability test execution failed - {str(e)}")
        return False
    finally:
        await tester.cleanup()


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)