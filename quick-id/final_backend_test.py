#!/usr/bin/env python3
"""
Final Comprehensive Quick ID Reader v4.0 Backend API Test
This test covers all the new v4.0 endpoints with proper error handling and reporting
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api"
ADMIN_EMAIL = "admin@quickid.com"
ADMIN_PASSWORD = "admin123"

class FinalTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.test_results = {
            'working': [],
            'failing': [],
            'critical_issues': []
        }
        
    def authenticate(self):
        """Login and get Bearer token"""
        response = self.session.post(f"{BASE_URL}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if response.status_code == 200:
            data = response.json()
            self.token = data["token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        return False
    
    def test_endpoint(self, name, method, endpoint, data=None, auth_required=True):
        """Test a single endpoint"""
        try:
            if method == 'GET':
                if auth_required:
                    response = self.session.get(f"{BASE_URL}{endpoint}")
                else:
                    response = requests.get(f"{BASE_URL}{endpoint}")
            elif method == 'POST':
                if auth_required:
                    response = self.session.post(f"{BASE_URL}{endpoint}", json=data)
                else:
                    response = requests.post(f"{BASE_URL}{endpoint}", json=data)
            elif method == 'PATCH':
                response = self.session.patch(f"{BASE_URL}{endpoint}", json=data)
            
            if response.status_code == 200:
                self.test_results['working'].append(f"✅ {name}")
                return True, response.json()
            else:
                self.test_results['failing'].append(f"❌ {name} (Status: {response.status_code})")
                return False, response.text
                
        except Exception as e:
            self.test_results['failing'].append(f"❌ {name} (Exception: {str(e)})")
            return False, str(e)
    
    def run_comprehensive_tests(self):
        """Run all endpoint tests"""
        print("🚀 Final Comprehensive v4.0 Backend API Tests")
        print("=" * 60)
        
        if not self.authenticate():
            print("❌ Authentication failed")
            return
            
        # 1. Room Management Endpoints
        print("\n🏨 Room Management Tests:")
        
        # Public endpoint - room types  
        self.test_endpoint("Room Types", "GET", "/rooms/types", auth_required=False)
        
        # Create room (use unique number)
        room_number = f"TEST{datetime.now().strftime('%H%M%S')}"
        success, result = self.test_endpoint("Create Room", "POST", "/rooms", {
            "room_number": room_number,
            "room_type": "standard", 
            "floor": 1,
            "capacity": 2
        })
        
        room_id = None
        if success:
            room_id = result.get('room', {}).get('room_id')  # Use the UUID room_id
            
        self.test_endpoint("List Rooms", "GET", "/rooms")
        self.test_endpoint("Room Stats", "GET", "/rooms/stats")
        
        # Test room update if we have a room
        if room_id:
            self.test_endpoint("Update Room", "PATCH", f"/rooms/{room_id}", {"status": "cleaning"})
        
        # 2. Guest Photo Tests
        print("\n📸 Guest Photo Tests:")
        
        # Create test guest first
        guest_success, guest_result = self.test_endpoint("Create Test Guest", "POST", "/guests", {
            "first_name": "TestPhoto",
            "last_name": "User",
            "id_number": f"PHOTO{datetime.now().strftime('%H%M%S')}",
            "nationality": "Germany",
            "document_type": "passport", 
            "kvkk_consent": True
        })
        
        guest_id = None
        if guest_success:
            guest_id = guest_result.get('guest', {}).get('id')
            
            # Test photo upload/retrieve
            base64_img = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77zgAAAABJRU5ErkJggg=="
            self.test_endpoint("Upload Guest Photo", "POST", f"/guests/{guest_id}/photo", {
                "image_base64": base64_img
            })
            self.test_endpoint("Retrieve Guest Photo", "GET", f"/guests/{guest_id}/photo")
            
            # Test Form-C for foreign guest
            self.test_endpoint("Generate Form-C", "GET", f"/tc-kimlik/form-c/{guest_id}")
        
        # 3. Group Check-in Test
        print("\n👥 Group Check-in Tests:")
        
        # Create two guests for group test
        guest_ids = []
        for i in range(2):
            success, result = self.test_endpoint(f"Create Group Guest {i+1}", "POST", "/guests", {
                "first_name": f"Group{i+1}",
                "last_name": "Test",
                "id_number": f"GRP{datetime.now().strftime('%H%M%S')}{i}",
                "nationality": "Türkiye",
                "kvkk_consent": True
            })
            if success:
                guest_ids.append(result.get('guest', {}).get('id'))
        
        if len(guest_ids) >= 2:
            self.test_endpoint("Group Check-in", "POST", "/guests/group-checkin", {
                "guest_ids": guest_ids
            })
        
        # 4. Room Assignment Tests (Known Issue)
        print("\n🔑 Room Assignment Tests (Known Issues):")
        
        if room_id and guest_ids:
            # This will likely fail due to the room_id mismatch issue
            success, error = self.test_endpoint("Manual Room Assignment", "POST", "/rooms/assign", {
                "room_id": room_id,
                "guest_id": guest_ids[0]
            })
            
            if not success:
                self.test_results['critical_issues'].append("Room Assignment: ID mismatch between API and database layer")
            
            # Test auto-assign (also likely to fail)
            success, error = self.test_endpoint("Auto Room Assignment", "POST", "/rooms/auto-assign", {
                "guest_id": guest_ids[1] if len(guest_ids) > 1 else guest_ids[0]
            })
            
            if not success:
                self.test_results['critical_issues'].append("Auto Room Assignment: Server error (500/520)")
        
        # 5. Monitoring Dashboard Tests
        print("\n📊 Monitoring Dashboard Tests:")
        
        self.test_endpoint("Monitoring Dashboard", "GET", "/monitoring/dashboard")
        self.test_endpoint("Scan Statistics", "GET", "/monitoring/scan-stats?days=30")
        self.test_endpoint("Error Log", "GET", "/monitoring/error-log?days=7")  
        self.test_endpoint("AI Costs", "GET", "/monitoring/ai-costs?days=30")
        
        # 6. Backup/Restore Tests
        print("\n💾 Backup/Restore Tests:")
        
        self.test_endpoint("Create Backup", "POST", "/admin/backup", {
            "description": "Final test backup"
        })
        self.test_endpoint("List Backups", "GET", "/admin/backups")
        self.test_endpoint("Backup Schedule", "GET", "/admin/backup-schedule")
        
        # 7. OCR/Quality Check Tests
        print("\n🔍 OCR/Quality Tests:")
        
        self.test_endpoint("OCR Status", "GET", "/scan/ocr-status", auth_required=False)
        self.test_endpoint("Image Quality Check", "POST", "/scan/quality-check", {
            "image_base64": base64_img
        })
        
        # 8. Compliance Reports
        print("\n📑 Compliance Tests:")
        
        self.test_endpoint("Compliance Reports", "GET", "/compliance/reports")
        
        # 9. Security Headers Test
        print("\n🔒 Security Headers Test:")
        
        response = self.session.get(f"{BASE_URL}/dashboard/stats")
        if response.status_code == 200:
            headers = response.headers
            if 'X-Content-Type-Options' in headers and 'X-Frame-Options' in headers:
                self.test_results['working'].append("✅ Security Headers")
            else:
                self.test_results['failing'].append("❌ Security Headers Missing")
        
        # Cleanup created test data
        print("\n🧹 Cleaning up test data...")
        if guest_id:
            requests.delete(f"{BASE_URL}/guests/{guest_id}", headers={"Authorization": f"Bearer {self.token}"})
        for gid in guest_ids:
            requests.delete(f"{BASE_URL}/guests/{gid}", headers={"Authorization": f"Bearer {self.token}"})
        
        self.print_final_results()
    
    def print_final_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 60)
        print("📊 FINAL TEST RESULTS")
        print("=" * 60)
        
        print(f"\n✅ WORKING ENDPOINTS ({len(self.test_results['working'])}):")
        for item in self.test_results['working']:
            print(f"  {item}")
            
        print(f"\n❌ FAILING ENDPOINTS ({len(self.test_results['failing'])}):")
        for item in self.test_results['failing']:
            print(f"  {item}")
            
        if self.test_results['critical_issues']:
            print(f"\n🚨 CRITICAL ISSUES ({len(self.test_results['critical_issues'])}):")
            for item in self.test_results['critical_issues']:
                print(f"  {item}")
        
        total_tests = len(self.test_results['working']) + len(self.test_results['failing'])
        success_rate = (len(self.test_results['working']) / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n📈 OVERALL SUCCESS RATE: {success_rate:.1f}% ({len(self.test_results['working'])}/{total_tests})")
        
        print("\n" + "=" * 60)
        print("🏁 TESTING COMPLETED")

def main():
    tester = FinalTester()
    tester.run_comprehensive_tests()

if __name__ == "__main__":
    main()