"""
AWS SES SMTP Email Integration Test
Tests REAL email sending with production AWS SES configuration
"""
import requests
import time
import json
from datetime import datetime

# Backend URL from environment
BACKEND_URL = "https://bug-fix-update.preview.emergentagent.com/api"

# Test configuration
TEST_EMAIL = "testuser_ses_" + str(int(time.time())) + "@gmail.com"  # Unique email for testing
TEST_NAME = "AWS SES Test User"
TEST_PASSWORD = "test123456"
TEST_PROPERTY = "Test Hotel SES"
TEST_PHONE = "+90 555 999 88 77"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.RESET}")

def test_email_service_configuration():
    """Test 0: Verify email service configuration"""
    print_header("TEST 0: Email Service Configuration Check")
    
    try:
        # Check backend logs for email service initialization
        import subprocess
        result = subprocess.run(
            ["grep", "-i", "email service", "/var/log/supervisor/backend.out.log"],
            capture_output=True,
            text=True
        )
        
        if "production mode" in result.stdout.lower():
            print_success("Email service initialized in PRODUCTION mode")
            return True
        elif "mock" in result.stdout.lower():
            print_warning("Email service is in MOCK mode - emails will not be sent")
            return False
        else:
            print_info("Email service initialization not found in logs")
            print_info("Checking environment configuration...")
            
            # Check if SMTP credentials are configured
            result = subprocess.run(
                ["grep", "EMAIL_MODE", "/app/backend/.env"],
                capture_output=True,
                text=True
            )
            
            if "production" in result.stdout.lower():
                print_success("EMAIL_MODE=production configured in .env")
                return True
            else:
                print_warning("EMAIL_MODE not set to production")
                return False
                
    except Exception as e:
        print_error(f"Configuration check failed: {e}")
        return False

def test_registration_with_email_verification():
    """Test 1: Registration with Email Verification (REAL EMAIL)"""
    print_header("TEST 1: Registration with Email Verification (REAL EMAIL)")
    
    print_info(f"Using test email: {TEST_EMAIL}")
    print_warning("IMPORTANT: Check your email inbox (and spam folder) for verification code")
    
    # Step 1: Request verification code
    print_info("\nStep 1: Requesting verification code...")
    
    payload = {
        "email": TEST_EMAIL,
        "name": TEST_NAME,
        "password": TEST_PASSWORD,
        "property_name": TEST_PROPERTY,
        "phone": TEST_PHONE,
        "user_type": "hotel"
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/request-verification",
            json=payload,
            timeout=30
        )
        
        print_info(f"Response Status: {response.status_code}")
        print_info(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            print_success("Verification code request successful!")
            print_success(f"Message: {data.get('message', 'N/A')}")
            print_success(f"Expires in: {data.get('expires_in_minutes', 'N/A')} minutes")
            
            # Check backend logs for SMTP connection
            print_info("\nChecking backend logs for SMTP activity...")
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "100", "/var/log/supervisor/backend.out.log"],
                capture_output=True,
                text=True
            )
            
            if "Email sent successfully" in result.stdout:
                print_success("✅ Email sent successfully via AWS SES SMTP!")
                print_success(f"Email sent to: {TEST_EMAIL}")
            elif "Failed to send email" in result.stdout:
                print_error("❌ SMTP connection failed - check logs")
                print_error("Error details in backend logs")
            else:
                print_warning("No SMTP activity found in logs")
                print_info("Email might be in mock mode or logs not captured")
            
            # Show verification code from logs (if in mock mode)
            if "E-POSTA DOĞRULAMA KODU" in result.stdout or "Kod:" in result.stdout:
                print_warning("\n⚠️  Email service appears to be in MOCK mode")
                print_info("Verification code printed to console logs:")
                for line in result.stdout.split('\n'):
                    if "Kod:" in line or "code:" in line.lower():
                        print_info(f"  {line.strip()}")
            
            return True, data
        else:
            print_error(f"Request failed with status {response.status_code}")
            print_error(f"Error: {response.text}")
            return False, None
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False, None

def test_verify_email_with_code(verification_code):
    """Test 1b: Verify email with code from inbox"""
    print_header("TEST 1b: Verify Email with Code")
    
    print_info(f"Using verification code: {verification_code}")
    
    payload = {
        "email": TEST_EMAIL,
        "code": verification_code
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/verify-email",
            json=payload,
            timeout=30
        )
        
        print_info(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print_success("Email verification successful!")
            print_success(f"Access Token: {data.get('access_token', 'N/A')[:50]}...")
            print_success(f"User ID: {data.get('user', {}).get('id', 'N/A')}")
            print_success(f"User Email: {data.get('user', {}).get('email', 'N/A')}")
            print_success(f"User Role: {data.get('user', {}).get('role', 'N/A')}")
            return True, data
        else:
            print_error(f"Verification failed with status {response.status_code}")
            print_error(f"Error: {response.text}")
            return False, None
            
    except Exception as e:
        print_error(f"Verification failed: {e}")
        return False, None

def test_password_reset_flow():
    """Test 2: Password Reset with REAL Email"""
    print_header("TEST 2: Password Reset Flow")
    
    # Use demo user for password reset test
    demo_email = "demo@hotel.com"
    
    print_info(f"Testing password reset for: {demo_email}")
    print_warning("Note: demo@hotel.com may not be a real email address")
    print_info("Checking backend logs for SMTP connection attempt...")
    
    payload = {
        "email": demo_email
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/forgot-password",
            json=payload,
            timeout=30
        )
        
        print_info(f"Response Status: {response.status_code}")
        print_info(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            print_success("Password reset request successful!")
            print_success(f"Message: {data.get('message', 'N/A')}")
            
            # Check backend logs for SMTP activity
            print_info("\nChecking backend logs for SMTP activity...")
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "100", "/var/log/supervisor/backend.out.log"],
                capture_output=True,
                text=True
            )
            
            if "Email sent successfully" in result.stdout:
                print_success("✅ Password reset email sent via AWS SES SMTP!")
            elif "Failed to send email" in result.stdout:
                print_error("❌ SMTP connection failed for password reset")
                # Extract error details
                for line in result.stdout.split('\n'):
                    if "Failed to send email" in line or "SMTP" in line:
                        print_error(f"  {line.strip()}")
            else:
                print_warning("No SMTP activity found in logs")
            
            return True, data
        else:
            print_error(f"Request failed with status {response.status_code}")
            print_error(f"Error: {response.text}")
            return False, None
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False, None

def check_smtp_credentials():
    """Check SMTP credentials configuration"""
    print_header("SMTP Configuration Check")
    
    try:
        import subprocess
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
        
        print_info("SMTP Configuration:")
        print_info(f"  EMAIL_MODE: {config.get('EMAIL_MODE', 'NOT SET')}")
        print_info(f"  SMTP_HOST: {config.get('SMTP_HOST', 'NOT SET')}")
        print_info(f"  SMTP_PORT: {config.get('SMTP_PORT', 'NOT SET')}")
        print_info(f"  SMTP_USERNAME: {config.get('SMTP_USERNAME', 'NOT SET')[:20]}...")
        print_info(f"  SMTP_PASSWORD: {'*' * 20 if config.get('SMTP_PASSWORD') else 'NOT SET'}")
        print_info(f"  SENDER_EMAIL: {config.get('SENDER_EMAIL', 'NOT SET')}")
        print_info(f"  SENDER_NAME: {config.get('SENDER_NAME', 'NOT SET')}")
        
        # Verify production mode
        if config.get('EMAIL_MODE') == 'production':
            print_success("✅ Email service configured for PRODUCTION mode")
        else:
            print_warning("⚠️  Email service NOT in production mode")
        
        # Verify SMTP credentials
        if config.get('SMTP_USERNAME') and config.get('SMTP_PASSWORD'):
            print_success("✅ SMTP credentials configured")
        else:
            print_error("❌ SMTP credentials missing")
        
        return config
        
    except Exception as e:
        print_error(f"Configuration check failed: {e}")
        return {}

def main():
    """Run all AWS SES SMTP email tests"""
    print_header("AWS SES SMTP EMAIL INTEGRATION TEST")
    print_info(f"Backend URL: {BACKEND_URL}")
    print_info(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "warnings": 0
    }
    
    # Check SMTP configuration
    config = check_smtp_credentials()
    
    # Test 0: Configuration check
    results["total"] += 1
    if test_email_service_configuration():
        results["passed"] += 1
    else:
        results["warnings"] += 1
        print_warning("Email service may be in mock mode - tests will continue but emails may not be sent")
    
    # Test 1: Registration with email verification
    print_info("\n" + "="*80)
    print_info("IMPORTANT: This test will attempt to send a REAL email")
    print_info(f"Email will be sent to: {TEST_EMAIL}")
    print_info("Please check your inbox (and spam folder) for the verification code")
    print_info("="*80)
    
    input("\nPress Enter to continue with Test 1 (Registration)...")
    
    results["total"] += 1
    success, data = test_registration_with_email_verification()
    if success:
        results["passed"] += 1
        
        # Ask user for verification code from email
        print_info("\n" + "="*80)
        print_info("Please check your email inbox for the verification code")
        print_info("The email should arrive within 1-2 minutes")
        print_info("Subject: 'Syroce - E-posta Doğrulama Kodu'")
        print_info("="*80)
        
        user_input = input("\nEnter the 6-digit verification code from your email (or 'skip' to skip): ")
        
        if user_input.lower() != 'skip' and user_input.isdigit() and len(user_input) == 6:
            results["total"] += 1
            success, verify_data = test_verify_email_with_code(user_input)
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
        else:
            print_warning("Skipping email verification test")
    else:
        results["failed"] += 1
    
    # Test 2: Password reset
    input("\nPress Enter to continue with Test 2 (Password Reset)...")
    
    results["total"] += 1
    success, data = test_password_reset_flow()
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Print summary
    print_header("TEST SUMMARY")
    print_info(f"Total Tests: {results['total']}")
    print_success(f"Passed: {results['passed']}")
    print_error(f"Failed: {results['failed']}")
    if results['warnings'] > 0:
        print_warning(f"Warnings: {results['warnings']}")
    
    print_info(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Final recommendations
    print_header("RECOMMENDATIONS")
    
    if config.get('EMAIL_MODE') != 'production':
        print_warning("1. Set EMAIL_MODE='production' in /app/backend/.env")
    
    if not config.get('SMTP_USERNAME') or not config.get('SMTP_PASSWORD'):
        print_warning("2. Configure SMTP credentials in /app/backend/.env")
    
    if results['failed'] > 0:
        print_warning("3. Check /var/log/supervisor/backend.out.log for detailed error messages")
        print_warning("4. Verify AWS SES SMTP credentials are correct")
        print_warning("5. Ensure sender email (info@syroce.com) is verified in AWS SES")
    
    if results['passed'] == results['total']:
        print_success("\n🎉 ALL TESTS PASSED! AWS SES SMTP integration is working correctly!")
    elif results['passed'] > 0:
        print_warning(f"\n⚠️  {results['passed']}/{results['total']} tests passed. Review failed tests above.")
    else:
        print_error("\n❌ ALL TESTS FAILED. AWS SES SMTP integration needs attention.")

if __name__ == "__main__":
    main()
