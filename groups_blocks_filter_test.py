#!/usr/bin/env python3
"""
GROUPS BLOCKS ENDPOINT FILTER TESTING
Testing /api/groups/blocks endpoint with new filter parameters

TEST SCENARIOS:
1. Parametresiz çağrı (no parameters)
2. Status filtresi (status=tentative)
3. Tarih aralığı filtresi - bugün (date_range=today)
4. Tarih aralığı filtresi - bu ay (date_range=this_month)
5. Custom tarih aralığı (date_range=custom&start_date=2025-11-01&end_date=2025-11-30)
6. Status + tarih filtresi birlikte (status=definite&date_range=this_month)

Base URL: https://pms-i18next-demo.preview.emergentagent.com/api
Auth: demo@hotel.com / demo123
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Any, Optional
import uuid

# Configuration
BACKEND_URL = "https://pms-i18next-demo.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class GroupsBlocksFilterTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate and get token"""
        try:
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data["access_token"]
                    self.tenant_id = data["user"]["tenant_id"]
                    self.user_id = data["user"]["id"]
                    print(f"✅ Authentication successful - Tenant: {self.tenant_id}")
                    return True
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    error_text = await response.text()
                    print(f"   Error details: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    async def test_groups_blocks_no_params(self):
        """Test 1: GET /groups/blocks - Parametresiz çağrı"""
        print("\n🏨 Test 1: Groups Blocks - No Parameters")
        print("Expected: Tüm tenant'a ait group_blocks kayıtlarını döndürmeli")
        
        try:
            url = f"{BACKEND_URL}/groups/blocks"
            
            start_time = datetime.now()
            async with self.session.get(url, headers=self.get_headers()) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Check response structure
                    if "blocks" in data and "total" in data:
                        blocks = data["blocks"]
                        total = data["total"]
                        
                        print(f"  ✅ HTTP 200 - Response time: {response_time:.1f}ms")
                        print(f"  ✅ Response structure correct: blocks ({len(blocks)} items), total ({total})")
                        
                        # Verify all blocks belong to tenant
                        if blocks:
                            tenant_check = all(block.get("tenant_id") == self.tenant_id for block in blocks)
                            if tenant_check:
                                print(f"  ✅ All blocks belong to correct tenant: {self.tenant_id}")
                            else:
                                print(f"  ⚠️ Some blocks don't belong to tenant: {self.tenant_id}")
                        else:
                            print(f"  ℹ️ No blocks found for tenant")
                        
                        self.test_results.append({
                            "test": "No Parameters",
                            "status": "PASSED",
                            "response_time": f"{response_time:.1f}ms",
                            "blocks_count": len(blocks),
                            "total": total
                        })
                    else:
                        print(f"  ❌ Invalid response structure. Expected 'blocks' and 'total' fields")
                        print(f"     Actual fields: {list(data.keys())}")
                        self.test_results.append({
                            "test": "No Parameters",
                            "status": "FAILED",
                            "error": "Invalid response structure"
                        })
                else:
                    error_text = await response.text()
                    print(f"  ❌ HTTP {response.status}")
                    print(f"     Error: {error_text}")
                    self.test_results.append({
                        "test": "No Parameters",
                        "status": "FAILED",
                        "error": f"HTTP {response.status}: {error_text}"
                    })
                    
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            self.test_results.append({
                "test": "No Parameters",
                "status": "FAILED",
                "error": str(e)
            })

    async def test_groups_blocks_status_filter(self):
        """Test 2: GET /groups/blocks?status=tentative - Status filtresi"""
        print("\n🏨 Test 2: Groups Blocks - Status Filter (tentative)")
        print("Expected: Tüm dönen block'ların status alanı 'tentative' olmalı")
        
        try:
            url = f"{BACKEND_URL}/groups/blocks?status=tentative"
            
            start_time = datetime.now()
            async with self.session.get(url, headers=self.get_headers()) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    if "blocks" in data and "total" in data:
                        blocks = data["blocks"]
                        total = data["total"]
                        
                        print(f"  ✅ HTTP 200 - Response time: {response_time:.1f}ms")
                        print(f"  ✅ Response structure correct: blocks ({len(blocks)} items), total ({total})")
                        
                        # Verify all blocks have status=tentative
                        if blocks:
                            status_check = all(block.get("status") == "tentative" for block in blocks)
                            if status_check:
                                print(f"  ✅ All blocks have status='tentative'")
                            else:
                                invalid_statuses = [block.get("status") for block in blocks if block.get("status") != "tentative"]
                                print(f"  ❌ Some blocks have different status: {set(invalid_statuses)}")
                        else:
                            print(f"  ℹ️ No tentative blocks found")
                        
                        self.test_results.append({
                            "test": "Status Filter (tentative)",
                            "status": "PASSED" if not blocks or all(block.get("status") == "tentative" for block in blocks) else "FAILED",
                            "response_time": f"{response_time:.1f}ms",
                            "blocks_count": len(blocks),
                            "total": total
                        })
                    else:
                        print(f"  ❌ Invalid response structure")
                        self.test_results.append({
                            "test": "Status Filter (tentative)",
                            "status": "FAILED",
                            "error": "Invalid response structure"
                        })
                else:
                    error_text = await response.text()
                    print(f"  ❌ HTTP {response.status}: {error_text}")
                    self.test_results.append({
                        "test": "Status Filter (tentative)",
                        "status": "FAILED",
                        "error": f"HTTP {response.status}"
                    })
                    
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            self.test_results.append({
                "test": "Status Filter (tentative)",
                "status": "FAILED",
                "error": str(e)
            })

    async def test_groups_blocks_date_range_today(self):
        """Test 3: GET /groups/blocks?date_range=today - Bugün filtresi"""
        print("\n🏨 Test 3: Groups Blocks - Date Range Filter (today)")
        print("Expected: Dönen kayıtların check_in alanı bugünün tarihi olmalı")
        
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"  Today's date: {today}")
        
        try:
            url = f"{BACKEND_URL}/groups/blocks?date_range=today"
            
            start_time = datetime.now()
            async with self.session.get(url, headers=self.get_headers()) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    if "blocks" in data and "total" in data:
                        blocks = data["blocks"]
                        total = data["total"]
                        
                        print(f"  ✅ HTTP 200 - Response time: {response_time:.1f}ms")
                        print(f"  ✅ Response structure correct: blocks ({len(blocks)} items), total ({total})")
                        
                        # Verify all blocks have check_in date = today
                        if blocks:
                            date_check_results = []
                            for block in blocks:
                                check_in = block.get("check_in", "")
                                # Extract date part from check_in (could be datetime string or date string)
                                if isinstance(check_in, str):
                                    check_in_date = check_in.split("T")[0] if "T" in check_in else check_in
                                else:
                                    check_in_date = str(check_in)
                                
                                date_check_results.append(check_in_date == today)
                                if check_in_date != today:
                                    print(f"     Block check_in: {check_in_date} (expected: {today})")
                            
                            if all(date_check_results):
                                print(f"  ✅ All blocks have check_in date = today ({today})")
                            else:
                                failed_count = len([r for r in date_check_results if not r])
                                print(f"  ❌ {failed_count}/{len(blocks)} blocks have incorrect check_in date")
                        else:
                            print(f"  ℹ️ No blocks found for today")
                        
                        self.test_results.append({
                            "test": "Date Range Filter (today)",
                            "status": "PASSED" if not blocks or all(
                                (block.get("check_in", "").split("T")[0] if "T" in block.get("check_in", "") else block.get("check_in", "")) == today
                                for block in blocks
                            ) else "FAILED",
                            "response_time": f"{response_time:.1f}ms",
                            "blocks_count": len(blocks),
                            "total": total,
                            "filter_date": today
                        })
                    else:
                        print(f"  ❌ Invalid response structure")
                        self.test_results.append({
                            "test": "Date Range Filter (today)",
                            "status": "FAILED",
                            "error": "Invalid response structure"
                        })
                else:
                    error_text = await response.text()
                    print(f"  ❌ HTTP {response.status}: {error_text}")
                    self.test_results.append({
                        "test": "Date Range Filter (today)",
                        "status": "FAILED",
                        "error": f"HTTP {response.status}"
                    })
                    
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            self.test_results.append({
                "test": "Date Range Filter (today)",
                "status": "FAILED",
                "error": str(e)
            })

    async def test_groups_blocks_date_range_this_month(self):
        """Test 4: GET /groups/blocks?date_range=this_month - Bu ay filtresi"""
        print("\n🏨 Test 4: Groups Blocks - Date Range Filter (this_month)")
        print("Expected: Dönen kayıtların check_in alanlarının ayı/yılı içinde bulunduğumuz ay/yıl olmalı")
        
        current_month = datetime.now().strftime("%Y-%m")
        print(f"  Current month: {current_month}")
        
        try:
            url = f"{BACKEND_URL}/groups/blocks?date_range=this_month"
            
            start_time = datetime.now()
            async with self.session.get(url, headers=self.get_headers()) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    if "blocks" in data and "total" in data:
                        blocks = data["blocks"]
                        total = data["total"]
                        
                        print(f"  ✅ HTTP 200 - Response time: {response_time:.1f}ms")
                        print(f"  ✅ Response structure correct: blocks ({len(blocks)} items), total ({total})")
                        
                        # Verify all blocks have check_in month/year = current month/year
                        if blocks:
                            date_check_results = []
                            for block in blocks:
                                check_in = block.get("check_in", "")
                                # Extract year-month part from check_in
                                if isinstance(check_in, str):
                                    check_in_date = check_in.split("T")[0] if "T" in check_in else check_in
                                    check_in_month = check_in_date[:7] if len(check_in_date) >= 7 else ""
                                else:
                                    check_in_month = ""
                                
                                date_check_results.append(check_in_month == current_month)
                                if check_in_month != current_month:
                                    print(f"     Block check_in month: {check_in_month} (expected: {current_month})")
                            
                            if all(date_check_results):
                                print(f"  ✅ All blocks have check_in month = current month ({current_month})")
                            else:
                                failed_count = len([r for r in date_check_results if not r])
                                print(f"  ❌ {failed_count}/{len(blocks)} blocks have incorrect check_in month")
                        else:
                            print(f"  ℹ️ No blocks found for this month")
                        
                        self.test_results.append({
                            "test": "Date Range Filter (this_month)",
                            "status": "PASSED" if not blocks or all(
                                (block.get("check_in", "").split("T")[0][:7] if "T" in block.get("check_in", "") else block.get("check_in", "")[:7]) == current_month
                                for block in blocks
                            ) else "FAILED",
                            "response_time": f"{response_time:.1f}ms",
                            "blocks_count": len(blocks),
                            "total": total,
                            "filter_month": current_month
                        })
                    else:
                        print(f"  ❌ Invalid response structure")
                        self.test_results.append({
                            "test": "Date Range Filter (this_month)",
                            "status": "FAILED",
                            "error": "Invalid response structure"
                        })
                else:
                    error_text = await response.text()
                    print(f"  ❌ HTTP {response.status}: {error_text}")
                    self.test_results.append({
                        "test": "Date Range Filter (this_month)",
                        "status": "FAILED",
                        "error": f"HTTP {response.status}"
                    })
                    
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            self.test_results.append({
                "test": "Date Range Filter (this_month)",
                "status": "FAILED",
                "error": str(e)
            })

    async def test_groups_blocks_custom_date_range(self):
        """Test 5: GET /groups/blocks?date_range=custom&start_date=2025-11-01&end_date=2025-11-30 - Custom tarih aralığı"""
        print("\n🏨 Test 5: Groups Blocks - Custom Date Range Filter")
        print("Expected: Dönen tüm kayıtların check_in değeri aralıkta (>=start_date ve <=end_date) olmalı")
        
        start_date = "2025-11-01"
        end_date = "2025-11-30"
        print(f"  Date range: {start_date} to {end_date}")
        
        try:
            url = f"{BACKEND_URL}/groups/blocks?date_range=custom&start_date={start_date}&end_date={end_date}"
            
            start_time = datetime.now()
            async with self.session.get(url, headers=self.get_headers()) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    if "blocks" in data and "total" in data:
                        blocks = data["blocks"]
                        total = data["total"]
                        
                        print(f"  ✅ HTTP 200 - Response time: {response_time:.1f}ms")
                        print(f"  ✅ Response structure correct: blocks ({len(blocks)} items), total ({total})")
                        
                        # Verify all blocks have check_in within date range
                        if blocks:
                            date_check_results = []
                            for block in blocks:
                                check_in = block.get("check_in", "")
                                # Extract date part from check_in
                                if isinstance(check_in, str):
                                    check_in_date = check_in.split("T")[0] if "T" in check_in else check_in
                                else:
                                    check_in_date = str(check_in)
                                
                                # Check if date is within range
                                in_range = start_date <= check_in_date <= end_date
                                date_check_results.append(in_range)
                                if not in_range:
                                    print(f"     Block check_in: {check_in_date} (outside range {start_date} - {end_date})")
                            
                            if all(date_check_results):
                                print(f"  ✅ All blocks have check_in within date range ({start_date} - {end_date})")
                            else:
                                failed_count = len([r for r in date_check_results if not r])
                                print(f"  ❌ {failed_count}/{len(blocks)} blocks have check_in outside date range")
                        else:
                            print(f"  ℹ️ No blocks found for date range")
                        
                        self.test_results.append({
                            "test": "Custom Date Range Filter",
                            "status": "PASSED" if not blocks or all(
                                start_date <= (block.get("check_in", "").split("T")[0] if "T" in block.get("check_in", "") else block.get("check_in", "")) <= end_date
                                for block in blocks
                            ) else "FAILED",
                            "response_time": f"{response_time:.1f}ms",
                            "blocks_count": len(blocks),
                            "total": total,
                            "start_date": start_date,
                            "end_date": end_date
                        })
                    else:
                        print(f"  ❌ Invalid response structure")
                        self.test_results.append({
                            "test": "Custom Date Range Filter",
                            "status": "FAILED",
                            "error": "Invalid response structure"
                        })
                else:
                    error_text = await response.text()
                    print(f"  ❌ HTTP {response.status}: {error_text}")
                    self.test_results.append({
                        "test": "Custom Date Range Filter",
                        "status": "FAILED",
                        "error": f"HTTP {response.status}"
                    })
                    
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            self.test_results.append({
                "test": "Custom Date Range Filter",
                "status": "FAILED",
                "error": str(e)
            })

    async def test_groups_blocks_combined_filters(self):
        """Test 6: GET /groups/blocks?status=definite&date_range=this_month - Status + tarih filtresi birlikte"""
        print("\n🏨 Test 6: Groups Blocks - Combined Filters (status + date_range)")
        print("Expected: Tüm kayıtlar hem status=definite hem de check_in bu ay olacak şekilde filtrelenmeli")
        
        current_month = datetime.now().strftime("%Y-%m")
        print(f"  Filters: status=definite AND date_range=this_month ({current_month})")
        
        try:
            url = f"{BACKEND_URL}/groups/blocks?status=definite&date_range=this_month"
            
            start_time = datetime.now()
            async with self.session.get(url, headers=self.get_headers()) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    if "blocks" in data and "total" in data:
                        blocks = data["blocks"]
                        total = data["total"]
                        
                        print(f"  ✅ HTTP 200 - Response time: {response_time:.1f}ms")
                        print(f"  ✅ Response structure correct: blocks ({len(blocks)} items), total ({total})")
                        
                        # Verify all blocks match both filters
                        if blocks:
                            status_check_results = []
                            date_check_results = []
                            
                            for block in blocks:
                                # Check status
                                status = block.get("status", "")
                                status_check_results.append(status == "definite")
                                
                                # Check date
                                check_in = block.get("check_in", "")
                                if isinstance(check_in, str):
                                    check_in_date = check_in.split("T")[0] if "T" in check_in else check_in
                                    check_in_month = check_in_date[:7] if len(check_in_date) >= 7 else ""
                                else:
                                    check_in_month = ""
                                
                                date_check_results.append(check_in_month == current_month)
                                
                                if status != "definite" or check_in_month != current_month:
                                    print(f"     Block status: {status}, check_in_month: {check_in_month}")
                            
                            status_passed = all(status_check_results)
                            date_passed = all(date_check_results)
                            
                            if status_passed and date_passed:
                                print(f"  ✅ All blocks match both filters (status=definite AND month={current_month})")
                            else:
                                if not status_passed:
                                    failed_status = len([r for r in status_check_results if not r])
                                    print(f"  ❌ {failed_status}/{len(blocks)} blocks have incorrect status")
                                if not date_passed:
                                    failed_date = len([r for r in date_check_results if not r])
                                    print(f"  ❌ {failed_date}/{len(blocks)} blocks have incorrect date")
                        else:
                            print(f"  ℹ️ No blocks found matching both filters")
                        
                        self.test_results.append({
                            "test": "Combined Filters (status + date_range)",
                            "status": "PASSED" if not blocks or (
                                all(block.get("status") == "definite" for block in blocks) and
                                all((block.get("check_in", "").split("T")[0][:7] if "T" in block.get("check_in", "") else block.get("check_in", "")[:7]) == current_month for block in blocks)
                            ) else "FAILED",
                            "response_time": f"{response_time:.1f}ms",
                            "blocks_count": len(blocks),
                            "total": total,
                            "status_filter": "definite",
                            "date_filter": current_month
                        })
                    else:
                        print(f"  ❌ Invalid response structure")
                        self.test_results.append({
                            "test": "Combined Filters (status + date_range)",
                            "status": "FAILED",
                            "error": "Invalid response structure"
                        })
                else:
                    error_text = await response.text()
                    print(f"  ❌ HTTP {response.status}: {error_text}")
                    self.test_results.append({
                        "test": "Combined Filters (status + date_range)",
                        "status": "FAILED",
                        "error": f"HTTP {response.status}"
                    })
                    
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            self.test_results.append({
                "test": "Combined Filters (status + date_range)",
                "status": "FAILED",
                "error": str(e)
            })

    async def run_all_tests(self):
        """Run all groups/blocks filter tests"""
        print("🚀 GROUPS BLOCKS ENDPOINT FILTER TESTING")
        print("Testing /api/groups/blocks endpoint with new filter parameters")
        print(f"Base URL: {BACKEND_URL}")
        print(f"Auth: {TEST_EMAIL} / {TEST_PASSWORD}")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Run all tests
        await self.test_groups_blocks_no_params()
        await self.test_groups_blocks_status_filter()
        await self.test_groups_blocks_date_range_today()
        await self.test_groups_blocks_date_range_this_month()
        await self.test_groups_blocks_custom_date_range()
        await self.test_groups_blocks_combined_filters()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 GROUPS BLOCKS FILTER TEST RESULTS")
        print("=" * 80)
        
        passed_tests = [r for r in self.test_results if r["status"] == "PASSED"]
        failed_tests = [r for r in self.test_results if r["status"] == "FAILED"]
        
        total_tests = len(self.test_results)
        passed_count = len(passed_tests)
        success_rate = (passed_count / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n📈 OVERALL RESULTS: {passed_count}/{total_tests} ({success_rate:.1f}%)")
        
        if success_rate == 100:
            print("🎉 EXCELLENT: All filter tests passed!")
        elif success_rate >= 80:
            print("✅ GOOD: Most filter tests passed")
        elif success_rate >= 50:
            print("⚠️ PARTIAL: Some filter tests failed")
        else:
            print("❌ CRITICAL: Most filter tests failed")
        
        print("\n📋 DETAILED RESULTS:")
        print("-" * 60)
        
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASSED" else "❌"
            test_name = result["test"]
            
            if result["status"] == "PASSED":
                response_time = result.get("response_time", "N/A")
                blocks_count = result.get("blocks_count", "N/A")
                print(f"{status_icon} {test_name}: {response_time}, {blocks_count} blocks")
            else:
                error = result.get("error", "Unknown error")
                print(f"{status_icon} {test_name}: {error}")
        
        print("\n🔍 TEST SCENARIOS COVERED:")
        print("1. ✓ Parametresiz çağrı - Tüm group_blocks kayıtları")
        print("2. ✓ Status filtresi - status=tentative")
        print("3. ✓ Tarih aralığı filtresi - date_range=today")
        print("4. ✓ Tarih aralığı filtresi - date_range=this_month")
        print("5. ✓ Custom tarih aralığı - date_range=custom&start_date&end_date")
        print("6. ✓ Kombine filtreler - status + date_range")
        
        print("\n📝 NOTES:")
        print("• All successful requests returned HTTP 200")
        print("• Response structure verified: {blocks: [...], total: number}")
        print("• Date filtering tested against check_in field (YYYY-MM-DD format)")
        print("• Status filtering tested for exact match")
        print("• Combined filters tested for AND logic")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = GroupsBlocksFilterTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())