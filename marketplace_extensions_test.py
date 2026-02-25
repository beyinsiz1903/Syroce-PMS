#!/usr/bin/env python3
"""
Test 4 New Marketplace Extensions for Wholesale Management
Testing 20 new endpoints for supplier management, GM approval workflow, 
warehouse stock tracking, and shipping & delivery tracking
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://hotel-pms-demo.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class MarketplaceExtensionsTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = {
            "supplier_management": {"passed": 0, "failed": 0, "details": []},
            "gm_approval": {"passed": 0, "failed": 0, "details": []},
            "warehouse_tracking": {"passed": 0, "failed": 0, "details": []},
            "shipping_delivery": {"passed": 0, "failed": 0, "details": []}
        }
        self.created_resources = {
            "supplier_ids": [],
            "warehouse_ids": [],
            "po_ids": [],
            "delivery_ids": []
        }

    def authenticate(self):
        """Authenticate with the backend"""
        print("🔐 Authenticating...")
        try:
            response = self.session.post(f"{BACKEND_URL}/auth/login", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data["access_token"]
                self.tenant_id = data["user"]["tenant_id"]
                self.user_id = data["user"]["id"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                })
                print(f"✅ Authentication successful - User: {data['user']['name']}")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False

    def log_test_result(self, category, endpoint, method, success, details=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "endpoint": f"{method} {endpoint}",
            "status": status,
            "details": details
        }
        self.test_results[category]["details"].append(result)
        if success:
            self.test_results[category]["passed"] += 1
        else:
            self.test_results[category]["failed"] += 1
        
        print(f"  {status}: {method} {endpoint} - {details}")

    def test_supplier_management(self):
        """Test Supplier Management with Credit Limits (6 endpoints)"""
        print("\n📋 Testing Supplier Management with Credit Limits...")
        
        # 1. POST /api/marketplace/suppliers (First supplier)
        try:
            response = self.session.post(f"{BACKEND_URL}/marketplace/suppliers", json={
                "supplier_name": "Hotel Supplies Ltd",
                "contact_person": "John Manager",
                "contact_email": "john@supplies.com",
                "contact_phone": "+1234567890",
                "credit_limit": 50000.0,
                "payment_terms": "Net 30",
                "status": "active"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                supplier_id = response.json().get('id')
                if supplier_id:
                    self.created_resources["supplier_ids"].append(supplier_id)
                details += f" - Supplier created: {response.json().get('supplier_name', 'N/A')}"
            self.log_test_result("supplier_management", "/marketplace/suppliers", "POST", success, details)
        except Exception as e:
            self.log_test_result("supplier_management", "/marketplace/suppliers", "POST", False, f"Error: {str(e)}")

        # 2. POST /api/marketplace/suppliers (Second supplier)
        try:
            response = self.session.post(f"{BACKEND_URL}/marketplace/suppliers", json={
                "supplier_name": "Linen Company",
                "contact_person": "Sarah Sales",
                "contact_email": "sarah@linen.com",
                "contact_phone": "+0987654321",
                "credit_limit": 25000.0,
                "payment_terms": "Net 15",
                "status": "active"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                supplier_id = response.json().get('id')
                if supplier_id:
                    self.created_resources["supplier_ids"].append(supplier_id)
                details += f" - Supplier created: {response.json().get('supplier_name', 'N/A')}"
            self.log_test_result("supplier_management", "/marketplace/suppliers (Linen)", "POST", success, details)
        except Exception as e:
            self.log_test_result("supplier_management", "/marketplace/suppliers (Linen)", "POST", False, f"Error: {str(e)}")

        # 3. GET /api/marketplace/suppliers (all suppliers)
        try:
            response = self.session.get(f"{BACKEND_URL}/marketplace/suppliers")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                suppliers = data.get('suppliers', []) if isinstance(data, dict) else data
                details += f" - Total suppliers: {len(suppliers)}"
            self.log_test_result("supplier_management", "/marketplace/suppliers", "GET", success, details)
        except Exception as e:
            self.log_test_result("supplier_management", "/marketplace/suppliers", "GET", False, f"Error: {str(e)}")

        # 4. GET /api/marketplace/suppliers?status=active (filtered)
        try:
            response = self.session.get(f"{BACKEND_URL}/marketplace/suppliers?status=active")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - Active filter"
            if success:
                data = response.json()
                suppliers = data.get('suppliers', []) if isinstance(data, dict) else data
                details += f" - Active suppliers: {len(suppliers)}"
            self.log_test_result("supplier_management", "/marketplace/suppliers?status=active", "GET", success, details)
        except Exception as e:
            self.log_test_result("supplier_management", "/marketplace/suppliers?status=active", "GET", False, f"Error: {str(e)}")

        # 5. PUT /api/marketplace/suppliers/{supplier_id}/credit
        if self.created_resources["supplier_ids"]:
            supplier_id = self.created_resources["supplier_ids"][0]
            try:
                response = self.session.put(f"{BACKEND_URL}/marketplace/suppliers/{supplier_id}/credit", json={
                    "credit_limit": 75000.0,
                    "payment_terms": "Net 45"
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                if success:
                    details += " - Credit limit updated to $75,000"
                self.log_test_result("supplier_management", f"/marketplace/suppliers/{supplier_id}/credit", "PUT", success, details)
            except Exception as e:
                self.log_test_result("supplier_management", f"/marketplace/suppliers/{supplier_id}/credit", "PUT", False, f"Error: {str(e)}")

            # 6. GET /api/marketplace/suppliers/{supplier_id}/credit-status
            try:
                response = self.session.get(f"{BACKEND_URL}/marketplace/suppliers/{supplier_id}/credit-status")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                if success:
                    data = response.json()
                    credit_limit = data.get('credit_limit', 0)
                    available_credit = data.get('available_credit', 0)
                    details += f" - Credit limit: ${credit_limit}, Available: ${available_credit}"
                self.log_test_result("supplier_management", f"/marketplace/suppliers/{supplier_id}/credit-status", "GET", success, details)
            except Exception as e:
                self.log_test_result("supplier_management", f"/marketplace/suppliers/{supplier_id}/credit-status", "GET", False, f"Error: {str(e)}")

    def test_gm_approval_workflow(self):
        """Test GM Approval Workflow (5 endpoints)"""
        print("\n✅ Testing GM Approval Workflow...")
        
        # First create a PO for testing approval workflow
        po_id_for_approval = None
        try:
            response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders", json={
                "supplier": "Hotel Supplies Ltd",
                "items": [{"product_name": "Test Product", "quantity": 10, "unit_price": 50.0}],
                "delivery_location": "main_warehouse",
                "expected_delivery_date": "2025-02-01"
            })
            if response.status_code in [200, 201] and response.json():
                po_id_for_approval = response.json().get('id')
                if po_id_for_approval:
                    self.created_resources["po_ids"].append(po_id_for_approval)
        except:
            pass
        
        # 1. POST /api/marketplace/purchase-orders/{po_id}/submit-for-approval
        if po_id_for_approval:
            try:
                response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders/{po_id_for_approval}/submit-for-approval")
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                if success:
                    details += " - PO submitted for GM approval"
                self.log_test_result("gm_approval", f"/marketplace/purchase-orders/{po_id_for_approval}/submit-for-approval", "POST", success, details)
            except Exception as e:
                self.log_test_result("gm_approval", f"/marketplace/purchase-orders/{po_id_for_approval}/submit-for-approval", "POST", False, f"Error: {str(e)}")

        # 2. GET /api/marketplace/approvals/pending
        try:
            response = self.session.get(f"{BACKEND_URL}/marketplace/approvals/pending")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                pending_approvals = data.get('pending_approvals', []) if isinstance(data, dict) else data
                details += f" - Pending approvals: {len(pending_approvals)}"
            self.log_test_result("gm_approval", "/marketplace/approvals/pending", "GET", success, details)
        except Exception as e:
            self.log_test_result("gm_approval", "/marketplace/approvals/pending", "GET", False, f"Error: {str(e)}")

        # 3. POST /api/marketplace/purchase-orders/{po_id}/approve
        if po_id_for_approval:
            try:
                response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders/{po_id_for_approval}/approve", json={
                    "approval_notes": "Approved by GM - urgent supplies needed"
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                if success:
                    details += " - PO approved by GM"
                self.log_test_result("gm_approval", f"/marketplace/purchase-orders/{po_id_for_approval}/approve", "POST", success, details)
            except Exception as e:
                self.log_test_result("gm_approval", f"/marketplace/purchase-orders/{po_id_for_approval}/approve", "POST", False, f"Error: {str(e)}")

        # 4. Create another PO for rejection testing
        po_id_for_rejection = None
        try:
            response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders", json={
                "supplier": "Test Supplier for Rejection",
                "items": [{"product_name": "Expensive Item", "quantity": 1, "unit_price": 10000.0}],
                "delivery_location": "test_warehouse",
                "expected_delivery_date": "2025-02-15"
            })
            if response.status_code in [200, 201] and response.json():
                po_id_for_rejection = response.json().get('id')
        except:
            pass
        
        # 5. POST /api/marketplace/purchase-orders/{po_id}/reject
        if po_id_for_rejection:
            try:
                response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders/{po_id_for_rejection}/reject", json={
                    "rejection_reason": "Budget exceeded for this quarter"
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                if success:
                    details += " - PO rejected by GM"
                self.log_test_result("gm_approval", f"/marketplace/purchase-orders/{po_id_for_rejection}/reject", "POST", success, details)
            except Exception as e:
                self.log_test_result("gm_approval", f"/marketplace/purchase-orders/{po_id_for_rejection}/reject", "POST", False, f"Error: {str(e)}")

        # 6. Verify approval workflow state transitions by checking PO status
        if po_id_for_approval:
            try:
                response = self.session.get(f"{BACKEND_URL}/marketplace/purchase-orders")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                if success:
                    data = response.json()
                    purchase_orders = data.get('purchase_orders', []) if isinstance(data, dict) else data
                    approved_po = next((po for po in purchase_orders if po.get('id') == po_id_for_approval), None)
                    if approved_po:
                        status = approved_po.get('status', 'unknown')
                        details += f" - Workflow verified: PO status is '{status}'"
                    else:
                        details += " - PO not found in list"
                self.log_test_result("gm_approval", "Workflow State Verification", "GET", success, details)
            except Exception as e:
                self.log_test_result("gm_approval", "Workflow State Verification", "GET", False, f"Error: {str(e)}")

    def test_warehouse_tracking(self):
        """Test Warehouse/Depot Stock Tracking (5 endpoints)"""
        print("\n🏭 Testing Warehouse/Depot Stock Tracking...")
        
        # 1. POST /api/marketplace/warehouses (Central Warehouse)
        try:
            response = self.session.post(f"{BACKEND_URL}/marketplace/warehouses", json={
                "warehouse_name": "Central Warehouse",
                "location": "Main Building",
                "capacity": 10000,
                "warehouse_type": "central"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                warehouse_id = response.json().get('id')
                if warehouse_id:
                    self.created_resources["warehouse_ids"].append(warehouse_id)
                details += f" - Warehouse created: {response.json().get('warehouse_name', 'N/A')}"
            self.log_test_result("warehouse_tracking", "/marketplace/warehouses", "POST", success, details)
        except Exception as e:
            self.log_test_result("warehouse_tracking", "/marketplace/warehouses", "POST", False, f"Error: {str(e)}")

        # 2. POST /api/marketplace/warehouses (Floor 3 Storage)
        try:
            response = self.session.post(f"{BACKEND_URL}/marketplace/warehouses", json={
                "warehouse_name": "Floor 3 Storage",
                "location": "Floor 3",
                "capacity": 5000,
                "warehouse_type": "regional"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                warehouse_id = response.json().get('id')
                if warehouse_id:
                    self.created_resources["warehouse_ids"].append(warehouse_id)
                details += f" - Warehouse created: {response.json().get('warehouse_name', 'N/A')}"
            self.log_test_result("warehouse_tracking", "/marketplace/warehouses (Floor 3)", "POST", success, details)
        except Exception as e:
            self.log_test_result("warehouse_tracking", "/marketplace/warehouses (Floor 3)", "POST", False, f"Error: {str(e)}")

        # 3. GET /api/marketplace/warehouses
        try:
            response = self.session.get(f"{BACKEND_URL}/marketplace/warehouses")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                warehouses = data.get('warehouses', []) if isinstance(data, dict) else data
                details += f" - Total warehouses: {len(warehouses)}"
            self.log_test_result("warehouse_tracking", "/marketplace/warehouses", "GET", success, details)
        except Exception as e:
            self.log_test_result("warehouse_tracking", "/marketplace/warehouses", "GET", False, f"Error: {str(e)}")

        # 4. GET /api/marketplace/warehouses/{warehouse_id}/inventory
        if self.created_resources["warehouse_ids"]:
            warehouse_id = self.created_resources["warehouse_ids"][0]
            try:
                response = self.session.get(f"{BACKEND_URL}/marketplace/warehouses/{warehouse_id}/inventory")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                if success:
                    data = response.json()
                    inventory_items = data.get('inventory', []) if isinstance(data, dict) else data
                    details += f" - Inventory items in warehouse: {len(inventory_items)}"
                self.log_test_result("warehouse_tracking", f"/marketplace/warehouses/{warehouse_id}/inventory", "GET", success, details)
            except Exception as e:
                self.log_test_result("warehouse_tracking", f"/marketplace/warehouses/{warehouse_id}/inventory", "GET", False, f"Error: {str(e)}")

        # 5. GET /api/marketplace/stock-summary
        try:
            response = self.session.get(f"{BACKEND_URL}/marketplace/stock-summary")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                total_items = data.get('total_items', 0)
                total_value = data.get('total_value', 0)
                details += f" - Stock summary: {total_items} items, ${total_value} value"
            self.log_test_result("warehouse_tracking", "/marketplace/stock-summary", "GET", success, details)
        except Exception as e:
            self.log_test_result("warehouse_tracking", "/marketplace/stock-summary", "GET", False, f"Error: {str(e)}")

    def test_shipping_delivery(self):
        """Test Shipping & Delivery Tracking (4 endpoints)"""
        print("\n🚚 Testing Shipping & Delivery Tracking...")
        
        # First, create a delivery for testing if we have a PO
        delivery_id = None
        if self.created_resources["po_ids"]:
            po_id = self.created_resources["po_ids"][0]
            try:
                response = self.session.post(f"{BACKEND_URL}/marketplace/deliveries", json={
                    "po_id": po_id,
                    "tracking_number": "TRK123456789",
                    "carrier": "Express Logistics",
                    "estimated_delivery": "2025-02-01"
                })
                if response.status_code in [200, 201] and response.json():
                    delivery_id = response.json().get('id')
                    if delivery_id:
                        self.created_resources["delivery_ids"].append(delivery_id)
            except:
                pass
        
        # If no delivery created, try to get existing deliveries
        if not delivery_id:
            try:
                deliveries_response = self.session.get(f"{BACKEND_URL}/marketplace/deliveries")
                if deliveries_response.status_code == 200:
                    deliveries_data = deliveries_response.json()
                    deliveries = deliveries_data.get('deliveries', []) if isinstance(deliveries_data, dict) else deliveries_data
                    if deliveries:
                        delivery_id = deliveries[0].get('id')
                        self.created_resources["delivery_ids"].append(delivery_id)
            except:
                pass

        # 1. PUT /api/marketplace/deliveries/{delivery_id}/update-status (first update)
        if delivery_id:
            try:
                response = self.session.put(f"{BACKEND_URL}/marketplace/deliveries/{delivery_id}/update-status", json={
                    "status": "in_transit",
                    "location": "Distribution Center",
                    "notes": "Departed from supplier"
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                if success:
                    details += " - Delivery status updated to 'in_transit'"
                self.log_test_result("shipping_delivery", f"/marketplace/deliveries/{delivery_id}/update-status", "PUT", success, details)
            except Exception as e:
                self.log_test_result("shipping_delivery", f"/marketplace/deliveries/{delivery_id}/update-status", "PUT", False, f"Error: {str(e)}")

            # 2. PUT /api/marketplace/deliveries/{delivery_id}/update-status (second update)
            try:
                response = self.session.put(f"{BACKEND_URL}/marketplace/deliveries/{delivery_id}/update-status", json={
                    "status": "delivered",
                    "location": "Central Warehouse",
                    "notes": "Successfully delivered and signed"
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                if success:
                    details += " - Delivery status updated to 'delivered'"
                self.log_test_result("shipping_delivery", f"/marketplace/deliveries/{delivery_id}/update-status (delivered)", "PUT", success, details)
            except Exception as e:
                self.log_test_result("shipping_delivery", f"/marketplace/deliveries/{delivery_id}/update-status (delivered)", "PUT", False, f"Error: {str(e)}")

            # 3. GET /api/marketplace/deliveries/{delivery_id}/tracking
            try:
                response = self.session.get(f"{BACKEND_URL}/marketplace/deliveries/{delivery_id}/tracking")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                if success:
                    data = response.json()
                    tracking_history = data.get('tracking_history', [])
                    current_status = data.get('current_status', 'unknown')
                    details += f" - Current status: {current_status}, History: {len(tracking_history)} events"
                self.log_test_result("shipping_delivery", f"/marketplace/deliveries/{delivery_id}/tracking", "GET", success, details)
            except Exception as e:
                self.log_test_result("shipping_delivery", f"/marketplace/deliveries/{delivery_id}/tracking", "GET", False, f"Error: {str(e)}")

        # 4. GET /api/marketplace/deliveries/in-transit
        try:
            response = self.session.get(f"{BACKEND_URL}/marketplace/deliveries/in-transit")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                in_transit_deliveries = data.get('deliveries', []) if isinstance(data, dict) else data
                details += f" - In-transit deliveries: {len(in_transit_deliveries)}"
            self.log_test_result("shipping_delivery", "/marketplace/deliveries/in-transit", "GET", success, details)
        except Exception as e:
            self.log_test_result("shipping_delivery", "/marketplace/deliveries/in-transit", "GET", False, f"Error: {str(e)}")

    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*80)
        print("🎯 MARKETPLACE EXTENSIONS TESTING SUMMARY")
        print("="*80)
        
        total_passed = 0
        total_failed = 0
        
        for category, results in self.test_results.items():
            passed = results["passed"]
            failed = results["failed"]
            total = passed + failed
            
            total_passed += passed
            total_failed += failed
            
            success_rate = (passed / total * 100) if total > 0 else 0
            status_icon = "✅" if success_rate >= 80 else "⚠️" if success_rate >= 60 else "❌"
            
            print(f"\n{status_icon} {category.upper().replace('_', ' ')}: {passed}/{total} ({success_rate:.1f}%)")
            
            # Show failed tests
            failed_tests = [detail for detail in results["details"] if "❌ FAIL" in detail["status"]]
            if failed_tests:
                print("   Failed endpoints:")
                for test in failed_tests[:3]:  # Show first 3 failures
                    print(f"     • {test['endpoint']} - {test['details']}")
                if len(failed_tests) > 3:
                    print(f"     • ... and {len(failed_tests) - 3} more")
        
        grand_total = total_passed + total_failed
        overall_success_rate = (total_passed / grand_total * 100) if grand_total > 0 else 0
        
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"   Total Endpoints Tested: {grand_total}")
        print(f"   Passed: {total_passed}")
        print(f"   Failed: {total_failed}")
        print(f"   Success Rate: {overall_success_rate:.1f}%")
        
        if overall_success_rate >= 90:
            print("   Status: 🟢 EXCELLENT - All systems operational")
        elif overall_success_rate >= 80:
            print("   Status: 🟡 GOOD - Minor issues detected")
        elif overall_success_rate >= 60:
            print("   Status: 🟠 FAIR - Several issues need attention")
        else:
            print("   Status: 🔴 POOR - Major issues require immediate attention")
        
        print("\n" + "="*80)

    def run_all_tests(self):
        """Run all marketplace extension tests"""
        print("🚀 Starting Marketplace Extensions Testing")
        print("Testing 20 new endpoints across 4 wholesale management features...")
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with testing.")
            return False
        
        # Run all test suites
        self.test_supplier_management()     # 6 endpoints
        self.test_gm_approval_workflow()    # 5 endpoints
        self.test_warehouse_tracking()      # 5 endpoints
        self.test_shipping_delivery()       # 4 endpoints
        
        # Print comprehensive summary
        self.print_summary()
        
        return True

def main():
    """Main function"""
    tester = MarketplaceExtensionsTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ Marketplace Extensions testing completed!")
    else:
        print("\n❌ Marketplace Extensions testing failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()