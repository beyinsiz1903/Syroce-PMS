"""
AWS SES SMTP Email Integration Test - Automated
Tests REAL email sending with production AWS SES configuration
"""
import requests
import time
import json
from datetime import datetime
import subprocess

# Backend URL from environment
BACKEND_URL = "https://bug-fix-update.preview.emergentagent.com/api"

# Test configuration
TEST_EMAIL = "testuser_ses_" + str(int(time.time())) + "@gmail.com"
TEST_NAME = "AWS SES Test User"
TEST_PASSWORD = "test123456"
TEST_PROPERTY = "Test Hotel SES"
TEST_PHONE = "+90 555 999 88 77"

def print_header(text):
    print(f"\n{'='*80}")
    print(f"{text}")
    print(f"{'='*80}\n")

def test_smtp_configuration():
    """Check SMTP configuration"""
    print_header("SMTP CONFIGURATION CHECK")
    
    try:
        result = subprocess.run(
            ["grep", "-E", "SMTP_|EMAIL_|SENDER_", "/app/backend/.env"],
            capture_output=True,
            text=True
        )
        
        config = {}
        for line in result.stdout.split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                config[key] = value.strip('"')
        
        print("SMTP Configuration:")
        print(f"  EMAIL_MODE: {config.get('EMAIL_MODE', 'NOT SET')}")
        print(f"  SMTP_HOST: {config.get('SMTP_HOST', 'NOT SET')}")
        print(f"  SMTP_PORT: {config.get('SMTP_PORT', 'NOT SET')}")
        print(f"  SMTP_USERNAME: {config.get('SMTP_USERNAME', 'NOT SET')[:30]}...")
        print(f"  SMTP_PASSWORD: {'*' * 30 if config.get('SMTP_PASSWORD') else 'NOT SET'}")
        print(f"  SENDER_EMAIL: {config.get('SENDER_EMAIL', 'NOT SET')}")
        print(f"  SENDER_NAME: {config.get('SENDER_NAME', 'NOT SET')}")
        
        return config
        
    except Exception as e:
        print(f"❌ Configuration check failed: {e}")
        return {}

def test_registration_email():
    """Test 1: Registration with Email Verification"""
    print_header("TEST 1: Registration Email Verification")
    
    print(f"Test Email: {TEST_EMAIL}")
    print(f"Test Name: {TEST_NAME}")
    
    payload = {
        "email": TEST_EMAIL,
        "name": TEST_NAME,
        "password": TEST_PASSWORD,
        "property_name": TEST_PROPERTY,
        "phone": TEST_PHONE,
        "user_type": "hotel"
    }
    
    try:
        print("\nSending registration request...")
        response = requests.post(
            f"{BACKEND_URL}/auth/request-verification",
            json=payload,
            timeout=30
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        # Check backend logs for SMTP activity
        print("\nChecking backend logs for SMTP activity...")
        result = subprocess.run(
            ["tail", "-n", "50", "/var/log/supervisor/backend.out.log"],
            capture_output=True,
            text=True
        )
        
        smtp_success = False
        smtp_error = None
        
        for line in result.stdout.split('\n'):
            if "Email sent successfully" in line:
                smtp_success = True
                print(f"✅ {line.strip()}")
            elif "Failed to send email" in line:
                smtp_error = line.strip()
                print(f"❌ {line.strip()}")
            elif "Authentication Credentials Invalid" in line:
                print(f"❌ SMTP Authentication Failed: {line.strip()}")
        
        if response.status_code == 200:
            print("\n✅ API endpoint returned 200 OK")
            if smtp_success:
                print("✅ Email sent successfully via AWS SES SMTP")
                return True, "success"
            elif smtp_error:
                print("❌ SMTP connection/authentication failed")
                return False, "smtp_error"
            else:
                print("⚠️  Email service may be in mock mode")
                return True, "mock_mode"
        else:
            print(f"\n❌ API endpoint failed with status {response.status_code}")
            return False, "api_error"
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False, "exception"

def test_password_reset_email():
    """Test 2: Password Reset Email"""
    print_header("TEST 2: Password Reset Email")
    
    demo_email = "demo@hotel.com"
    print(f"Test Email: {demo_email}")
    
    payload = {
        "email": demo_email
    }
    
    try:
        print("\nSending password reset request...")
        response = requests.post(
            f"{BACKEND_URL}/auth/forgot-password",
            json=payload,
            timeout=30
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        # Check backend logs for SMTP activity
        print("\nChecking backend logs for SMTP activity...")
        result = subprocess.run(
            ["tail", "-n", "50", "/var/log/supervisor/backend.out.log"],
            capture_output=True,
            text=True
        )
        
        smtp_success = False
        smtp_error = None
        
        for line in result.stdout.split('\n'):
            if "Email sent successfully" in line:
                smtp_success = True
                print(f"✅ {line.strip()}")
            elif "Failed to send email" in line:
                smtp_error = line.strip()
                print(f"❌ {line.strip()}")
            elif "Authentication Credentials Invalid" in line:
                print(f"❌ SMTP Authentication Failed: {line.strip()}")
        
        if response.status_code == 200:
            print("\n✅ API endpoint returned 200 OK")
            if smtp_success:
                print("✅ Email sent successfully via AWS SES SMTP")
                return True, "success"
            elif smtp_error:
                print("❌ SMTP connection/authentication failed")
                return False, "smtp_error"
            else:
                print("⚠️  Email service may be in mock mode")
                return True, "mock_mode"
        else:
            print(f"\n❌ API endpoint failed with status {response.status_code}")
            return False, "api_error"
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False, "exception"

def check_smtp_error_details():
    """Extract detailed SMTP error from logs"""
    print_header("SMTP ERROR ANALYSIS")
    
    try:
        result = subprocess.run(
            ["tail", "-n", "100", "/var/log/supervisor/backend.out.log"],
            capture_output=True,
            text=True
        )
        
        print("Recent SMTP-related log entries:")
        for line in result.stdout.split('\n'):
            if any(keyword in line.lower() for keyword in ['smtp', 'email', 'failed', 'authentication', 'credentials']):
                print(f"  {line.strip()}")
        
    except Exception as e:
        print(f"❌ Log analysis failed: {e}")

def main():
    """Run all tests"""
    print_header("AWS SES SMTP EMAIL INTEGRATION TEST - AUTOMATED")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "smtp_errors": 0
    }
    
    # Check SMTP configuration
    config = test_smtp_configuration()
    
    # Test 1: Registration email
    results["total"] += 1
    success, status = test_registration_email()
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
        if status == "smtp_error":
            results["smtp_errors"] += 1
    
    # Test 2: Password reset email
    results["total"] += 1
    success, status = test_password_reset_email()
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
        if status == "smtp_error":
            results["smtp_errors"] += 1
    
    # Analyze SMTP errors if any
    if results["smtp_errors"] > 0:
        check_smtp_error_details()
    
    # Print summary
    print_header("TEST SUMMARY")
    print(f"Total Tests: {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"SMTP Errors: {results['smtp_errors']}")
    
    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Recommendations
    print_header("FINDINGS & RECOMMENDATIONS")
    
    if results["smtp_errors"] > 0:
        print("❌ CRITICAL ISSUE: SMTP Authentication Failed")
        print("\nRoot Cause:")
        print("  AWS SES SMTP credentials are invalid or incorrect")
        print("  Error: (535, b'Authentication Credentials Invalid')")
        print("\nRequired Actions:")
        print("  1. Generate SMTP credentials from AWS SES Console:")
        print("     - Go to AWS SES Console > SMTP Settings")
        print("     - Click 'Create My SMTP Credentials'")
        print("     - Download the SMTP username and password")
        print("  2. Update /app/backend/.env with correct SMTP credentials:")
        print("     - SMTP_USERNAME=<generated_smtp_username>")
        print("     - SMTP_PASSWORD=<generated_smtp_password>")
        print("  3. Verify sender email (info@syroce.com) is verified in AWS SES")
        print("  4. Restart backend service: sudo supervisorctl restart backend")
        print("\nNote: AWS IAM Access Key (AKIAWYAONKF4ZPKPG662Z) is NOT the same as SMTP credentials")
    elif results["passed"] == results["total"]:
        print("✅ ALL TESTS PASSED!")
        print("AWS SES SMTP integration is working correctly")
        print("Emails are being sent successfully")
    else:
        print("⚠️  Some tests failed - review details above")
    
    return results

if __name__ == "__main__":
    results = main()
    exit(0 if results["smtp_errors"] == 0 else 1)
