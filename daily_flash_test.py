#!/usr/bin/env python3
"""
Daily Flash Report PDF and Email Export Testing
Testing the newly implemented endpoints:
- GET /api/reports/daily-flash-pdf
- POST /api/reports/email-daily-flash
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://bug-fix-update.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class DailyFlashReportTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = {
            "pdf_export": {"passed": 0, "failed": 0, "details": []},
            "email_export": {"passed": 0, "failed": 0, "details": []}
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
                self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
                print(f"✅ Authentication successful - User: {data['user']['name']}")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False

    def test_pdf_export_unauthorized(self):
        """Test PDF export without authentication - should return 401"""
        print("\n📄 Testing PDF export without authentication...")
        try:
            # Remove auth header temporarily
            headers = self.session.headers.copy()
            del self.session.headers["Authorization"]
            
            response = self.session.get(f"{BACKEND_URL}/reports/daily-flash-pdf")
            
            # Restore auth header
            self.session.headers = headers
            
            if response.status_code == 401:
                print("✅ PDF export correctly returns 401 without authentication")
                self.test_results["pdf_export"]["passed"] += 1
                self.test_results["pdf_export"]["details"].append("✅ Unauthorized access properly blocked")
                return True
            else:
                print(f"❌ PDF export should return 401, got {response.status_code}")
                self.test_results["pdf_export"]["failed"] += 1
                self.test_results["pdf_export"]["details"].append(f"❌ Expected 401, got {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ PDF unauthorized test error: {str(e)}")
            self.test_results["pdf_export"]["failed"] += 1
            self.test_results["pdf_export"]["details"].append(f"❌ Test error: {str(e)}")
            return False

    def test_pdf_export_authorized(self):
        """Test PDF export with valid authentication - should return 200 with PDF content"""
        print("\n📄 Testing PDF export with authentication...")
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/daily-flash-pdf")
            
            if response.status_code == 200:
                # Check response headers
                content_type = response.headers.get('content-type', '')
                content_disposition = response.headers.get('content-disposition', '')
                
                print(f"✅ PDF export successful - Status: {response.status_code}")
                print(f"   Content-Type: {content_type}")
                print(f"   Content-Disposition: {content_disposition}")
                print(f"   Content Length: {len(response.content)} bytes")
                
                # Verify headers
                if 'application/pdf' in content_type:
                    print("✅ Correct Content-Type for PDF")
                    self.test_results["pdf_export"]["passed"] += 1
                else:
                    print(f"⚠️  Content-Type is {content_type}, expected application/pdf")
                
                if 'attachment' in content_disposition and 'daily-flash' in content_disposition:
                    print("✅ Correct Content-Disposition header")
                    self.test_results["pdf_export"]["passed"] += 1
                else:
                    print(f"⚠️  Content-Disposition: {content_disposition}")
                
                # Check if content exists
                if len(response.content) > 0:
                    print("✅ PDF content generated successfully")
                    self.test_results["pdf_export"]["passed"] += 1
                    self.test_results["pdf_export"]["details"].append("✅ PDF export working with proper headers and content")
                else:
                    print("❌ PDF content is empty")
                    self.test_results["pdf_export"]["failed"] += 1
                    self.test_results["pdf_export"]["details"].append("❌ PDF content is empty")
                
                return True
            else:
                print(f"❌ PDF export failed: {response.status_code} - {response.text}")
                self.test_results["pdf_export"]["failed"] += 1
                self.test_results["pdf_export"]["details"].append(f"❌ PDF export failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ PDF export test error: {str(e)}")
            self.test_results["pdf_export"]["failed"] += 1
            self.test_results["pdf_export"]["details"].append(f"❌ Test error: {str(e)}")
            return False

    def test_email_export_no_recipients(self):
        """Test email export without recipients - should return 400"""
        print("\n📧 Testing email export without recipients...")
        try:
            response = self.session.post(f"{BACKEND_URL}/reports/email-daily-flash", json={})
            
            if response.status_code == 400:
                print("✅ Email export correctly returns 400 without recipients")
                self.test_results["email_export"]["passed"] += 1
                self.test_results["email_export"]["details"].append("✅ Validation working - requires recipients")
                return True
            else:
                print(f"❌ Email export should return 400, got {response.status_code}")
                self.test_results["email_export"]["failed"] += 1
                self.test_results["email_export"]["details"].append(f"❌ Expected 400, got {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Email no recipients test error: {str(e)}")
            self.test_results["email_export"]["failed"] += 1
            self.test_results["email_export"]["details"].append(f"❌ Test error: {str(e)}")
            return False

    def test_email_export_with_recipients(self):
        """Test email export with valid recipients - should return 200 with success message"""
        print("\n📧 Testing email export with recipients...")
        try:
            test_recipients = ["manager@hotel.com", "gm@hotel.com"]
            response = self.session.post(f"{BACKEND_URL}/reports/email-daily-flash", json={
                "recipients": test_recipients
            })
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Email export successful - Status: {response.status_code}")
                print(f"   Response: {json.dumps(data, indent=2)}")
                
                # Verify response structure
                if data.get('success') == True:
                    print("✅ Success flag is True")
                    self.test_results["email_export"]["passed"] += 1
                else:
                    print("❌ Success flag is not True")
                    self.test_results["email_export"]["failed"] += 1
                
                if data.get('recipients') == test_recipients:
                    print("✅ Recipients list matches")
                    self.test_results["email_export"]["passed"] += 1
                else:
                    print(f"❌ Recipients mismatch: expected {test_recipients}, got {data.get('recipients')}")
                    self.test_results["email_export"]["failed"] += 1
                
                if 'SMTP configuration' in data.get('note', ''):
                    print("✅ SMTP configuration note present")
                    self.test_results["email_export"]["passed"] += 1
                else:
                    print("⚠️  SMTP configuration note missing")
                
                self.test_results["email_export"]["details"].append("✅ Email export working with proper response structure")
                return True
            else:
                print(f"❌ Email export failed: {response.status_code} - {response.text}")
                self.test_results["email_export"]["failed"] += 1
                self.test_results["email_export"]["details"].append(f"❌ Email export failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Email export test error: {str(e)}")
            self.test_results["email_export"]["failed"] += 1
            self.test_results["email_export"]["details"].append(f"❌ Test error: {str(e)}")
            return False

    def test_email_export_unauthorized(self):
        """Test email export without authentication - should return 401"""
        print("\n📧 Testing email export without authentication...")
        try:
            # Remove auth header temporarily
            headers = self.session.headers.copy()
            del self.session.headers["Authorization"]
            
            response = self.session.post(f"{BACKEND_URL}/reports/email-daily-flash", json={
                "recipients": ["test@example.com"]
            })
            
            # Restore auth header
            self.session.headers = headers
            
            if response.status_code == 401:
                print("✅ Email export correctly returns 401 without authentication")
                self.test_results["email_export"]["passed"] += 1
                self.test_results["email_export"]["details"].append("✅ Unauthorized access properly blocked")
                return True
            else:
                print(f"❌ Email export should return 401, got {response.status_code}")
                self.test_results["email_export"]["failed"] += 1
                self.test_results["email_export"]["details"].append(f"❌ Expected 401, got {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Email unauthorized test error: {str(e)}")
            self.test_results["email_export"]["failed"] += 1
            self.test_results["email_export"]["details"].append(f"❌ Test error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all Daily Flash Report tests"""
        print("🚀 Starting Daily Flash Report Export Testing")
        print("=" * 60)
        
        # Authenticate first
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Run PDF tests
        print("\n📄 PDF EXPORT TESTS")
        print("-" * 30)
        self.test_pdf_export_unauthorized()
        self.test_pdf_export_authorized()
        
        # Run Email tests
        print("\n📧 EMAIL EXPORT TESTS")
        print("-" * 30)
        self.test_email_export_unauthorized()
        self.test_email_export_no_recipients()
        self.test_email_export_with_recipients()
        
        # Print summary
        self.print_summary()
        
        return True

    def print_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 60)
        print("📊 DAILY FLASH REPORT TESTING SUMMARY")
        print("=" * 60)
        
        total_passed = 0
        total_failed = 0
        
        for category, results in self.test_results.items():
            passed = results["passed"]
            failed = results["failed"]
            total_passed += passed
            total_failed += failed
            
            print(f"\n{category.upper().replace('_', ' ')}:")
            print(f"  ✅ Passed: {passed}")
            print(f"  ❌ Failed: {failed}")
            
            if results["details"]:
                print("  Details:")
                for detail in results["details"]:
                    print(f"    {detail}")
        
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"  ✅ Total Passed: {total_passed}")
        print(f"  ❌ Total Failed: {total_failed}")
        print(f"  📈 Success Rate: {(total_passed/(total_passed+total_failed)*100):.1f}%" if (total_passed+total_failed) > 0 else "0.0%")
        
        if total_failed == 0:
            print("\n🎉 ALL TESTS PASSED! Daily Flash Report export endpoints are working correctly.")
        else:
            print(f"\n⚠️  {total_failed} test(s) failed. Please review the issues above.")

def main():
    """Main function to run the tests"""
    tester = DailyFlashReportTester()
    success = tester.run_all_tests()
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()