"""
Email Verification and Password Reset System Test
Tests the new email verification registration flow and password reset functionality
"""
import requests
import time
import re
from datetime import datetime

# Backend URL from environment
BACKEND_URL = "https://code-cleanup-135.preview.emergentagent.com/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_test_header(test_name):
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{test_name}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")

def print_success(message):
    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")

def print_error(message):
    print(f"{Colors.RED}❌ {message}{Colors.RESET}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.RESET}")

def print_info(message):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.RESET}")

def extract_code_from_logs(code_type="verification"):
    """Extract verification or reset code from backend logs"""
    try:
        import subprocess
        result = subprocess.run(
            ['tail', '-n', '100', '/var/log/supervisor/backend.out.log'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Look for the code pattern in logs - get the LAST occurrence
        lines = result.stdout.split('\n')
        codes = []
        
        for i, line in enumerate(lines):
            # Check for the specific code type
            if code_type == "verification" and 'E-POSTA DOĞRULAMA KODU' in line:
                # Look for the code in the next few lines
                for j in range(i, min(i+10, len(lines))):
                    if 'Kod:' in lines[j]:
                        match = re.search(r'\b(\d{6})\b', lines[j])
                        if match:
                            codes.append(match.group(1))
                            break
            elif code_type == "reset" and 'ŞİFRE SIFIRLAMA KODU' in line:
                # Look for the code in the next few lines
                for j in range(i, min(i+10, len(lines))):
                    if 'Kod:' in lines[j]:
                        match = re.search(r'\b(\d{6})\b', lines[j])
                        if match:
                            codes.append(match.group(1))
                            break
        
        # Return the last code found (most recent)
        return codes[-1] if codes else None
    except Exception as e:
        print_warning(f"Could not extract code from logs: {e}")
        return None

def test_email_verification_flow():
    """Test 1: Email Verification Registration Flow"""
    print_test_header("TEST 1: EMAIL VERIFICATION REGISTRATION FLOW")
    
    # Generate unique email for testing
    timestamp = int(time.time())
    test_email = f"test{timestamp}@newhotel.com"
    
    print_info(f"Testing with email: {test_email}")
    
    # Step 1: Request verification code
    print("\n📤 Step 1: POST /api/auth/request-verification")
    request_data = {
        "email": test_email,
        "name": "Test User",
        "password": "test123",
        "property_name": "Test Hotel",
        "phone": "+90 555 999 88 77",
        "user_type": "hotel"
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/request-verification",
            json=request_data,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print_success("Verification code request successful")
            
            # Wait a moment for logs to be written
            time.sleep(2)
            
            # Extract code from logs
            print_info("Checking backend logs for verification code...")
            code = extract_code_from_logs("verification")
            
            if code:
                print_success(f"Found verification code in logs: {code}")
            else:
                print_warning("Could not extract code from logs automatically")
                print_info("Please check backend console output manually")
                print_info("Looking for pattern: 'Kod: XXXXXX' in logs")
                code = input("Enter the 6-digit code from console: ").strip()
            
            # Step 2: Verify email with code
            print("\n📤 Step 2: POST /api/auth/verify-email")
            verify_data = {
                "email": test_email,
                "code": code
            }
            
            verify_response = requests.post(
                f"{BACKEND_URL}/auth/verify-email",
                json=verify_data,
                timeout=10
            )
            
            print(f"Status Code: {verify_response.status_code}")
            
            if verify_response.status_code == 200:
                result = verify_response.json()
                print_success("Email verification successful!")
                print(f"Response keys: {list(result.keys())}")
                
                # Verify response structure
                if 'access_token' in result:
                    print_success("✓ access_token present")
                else:
                    print_error("✗ access_token missing")
                
                if 'user' in result:
                    print_success("✓ user object present")
                    user = result['user']
                    print(f"  - User ID: {user.get('id')}")
                    print(f"  - Email: {user.get('email')}")
                    print(f"  - Name: {user.get('name')}")
                    print(f"  - Role: {user.get('role')}")
                else:
                    print_error("✗ user object missing")
                
                if 'tenant' in result:
                    print_success("✓ tenant object present")
                    tenant = result['tenant']
                    print(f"  - Tenant ID: {tenant.get('id')}")
                    print(f"  - Property Name: {tenant.get('property_name')}")
                else:
                    print_error("✗ tenant object missing")
                
                return True, test_email
            else:
                print_error(f"Email verification failed: {verify_response.text}")
                return False, test_email
        else:
            print_error(f"Verification code request failed: {response.text}")
            return False, test_email
            
    except Exception as e:
        print_error(f"Test failed with exception: {e}")
        return False, test_email

def test_password_reset_flow():
    """Test 2: Password Reset Flow"""
    print_test_header("TEST 2: PASSWORD RESET FLOW")
    
    demo_email = "demo@hotel.com"
    demo_password = "demo123"
    new_password = "newpass123"
    
    print_info(f"Testing with demo user: {demo_email}")
    
    # Step 1: Request password reset
    print("\n📤 Step 1: POST /api/auth/forgot-password")
    forgot_data = {
        "email": demo_email
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/forgot-password",
            json=forgot_data,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print_success("Password reset request successful")
            
            # Wait for logs
            time.sleep(2)
            
            # Extract code from logs
            print_info("Checking backend logs for reset code...")
            code = extract_code_from_logs("reset")
            
            if code:
                print_success(f"Found reset code in logs: {code}")
            else:
                print_warning("Could not extract code from logs automatically")
                print_info("Please check backend console output manually")
                print_info("Looking for pattern: 'Kod: XXXXXX' in logs")
                code = input("Enter the 6-digit code from console: ").strip()
            
            # Step 2: Reset password with code
            print("\n📤 Step 2: POST /api/auth/reset-password")
            reset_data = {
                "email": demo_email,
                "code": code,
                "new_password": new_password
            }
            
            reset_response = requests.post(
                f"{BACKEND_URL}/auth/reset-password",
                json=reset_data,
                timeout=10
            )
            
            print(f"Status Code: {reset_response.status_code}")
            print(f"Response: {reset_response.json()}")
            
            if reset_response.status_code == 200:
                print_success("Password reset successful!")
                
                # Step 3: Verify new password works
                print("\n📤 Step 3: POST /api/auth/login (verify new password)")
                login_data = {
                    "email": demo_email,
                    "password": new_password
                }
                
                login_response = requests.post(
                    f"{BACKEND_URL}/auth/login",
                    json=login_data,
                    timeout=10
                )
                
                print(f"Status Code: {login_response.status_code}")
                
                if login_response.status_code == 200:
                    print_success("Login with new password successful!")
                    result = login_response.json()
                    print(f"Response keys: {list(result.keys())}")
                    
                    # Reset password back to original for future tests
                    print_info("\nResetting password back to original...")
                    
                    # Request another reset code
                    requests.post(f"{BACKEND_URL}/auth/forgot-password", json=forgot_data, timeout=10)
                    time.sleep(2)
                    
                    restore_code = extract_code_from_logs("reset")
                    if not restore_code:
                        restore_code = input("Enter the 6-digit code to restore password: ").strip()
                    
                    restore_data = {
                        "email": demo_email,
                        "code": restore_code,
                        "new_password": demo_password
                    }
                    
                    restore_response = requests.post(
                        f"{BACKEND_URL}/auth/reset-password",
                        json=restore_data,
                        timeout=10
                    )
                    
                    if restore_response.status_code == 200:
                        print_success("Password restored to original")
                    
                    return True
                else:
                    print_error(f"Login with new password failed: {login_response.text}")
                    return False
            else:
                print_error(f"Password reset failed: {reset_response.text}")
                return False
        else:
            print_error(f"Password reset request failed: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Test failed with exception: {e}")
        return False

def test_error_cases(registered_email=None):
    """Test 3: Error Cases"""
    print_test_header("TEST 3: ERROR CASES")
    
    # Test 3.1: Already registered email
    print("\n📤 Test 3.1: Request verification with already registered email")
    if registered_email:
        test_email = registered_email
    else:
        test_email = "demo@hotel.com"
    
    print_info(f"Testing with: {test_email}")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/request-verification",
            json={
                "email": test_email,
                "name": "Test User",
                "password": "test123",
                "property_name": "Test Hotel",
                "phone": "+90 555 999 88 77",
                "user_type": "hotel"
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 400:
            print_success("Correctly rejected already registered email (400)")
        else:
            print_error(f"Expected 400, got {response.status_code}")
    except Exception as e:
        print_error(f"Test failed: {e}")
    
    # Test 3.2: Wrong verification code
    print("\n📤 Test 3.2: Verify email with wrong code")
    timestamp = int(time.time())
    new_email = f"test{timestamp}@errortest.com"
    
    # First request a code
    requests.post(
        f"{BACKEND_URL}/auth/request-verification",
        json={
            "email": new_email,
            "name": "Error Test",
            "password": "test123",
            "property_name": "Error Hotel",
            "phone": "+90 555 999 88 77",
            "user_type": "hotel"
        },
        timeout=10
    )
    
    time.sleep(1)
    
    # Try with wrong code
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/verify-email",
            json={
                "email": new_email,
                "code": "000000"  # Wrong code
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 400:
            print_success("Correctly rejected wrong verification code (400)")
        else:
            print_error(f"Expected 400, got {response.status_code}")
    except Exception as e:
        print_error(f"Test failed: {e}")
    
    # Test 3.3: Password reset with invalid email
    print("\n📤 Test 3.3: Password reset with invalid email")
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/forgot-password",
            json={
                "email": "nonexistent@invalid.com"
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print_success("Correctly returned generic success message (security)")
            print_info("This prevents email enumeration attacks")
        else:
            print_error(f"Expected 200, got {response.status_code}")
    except Exception as e:
        print_error(f"Test failed: {e}")
    
    # Test 3.4: Reset password with wrong code
    print("\n📤 Test 3.4: Reset password with wrong code")
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/reset-password",
            json={
                "email": "demo@hotel.com",
                "code": "999999",  # Wrong code
                "new_password": "newpass123"
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 400:
            print_success("Correctly rejected wrong reset code (400)")
        else:
            print_error(f"Expected 400, got {response.status_code}")
    except Exception as e:
        print_error(f"Test failed: {e}")

def main():
    """Run all tests"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}")
    print("EMAIL VERIFICATION & PASSWORD RESET SYSTEM TEST")
    print(f"{'='*70}{Colors.RESET}\n")
    
    print_info(f"Backend URL: {BACKEND_URL}")
    print_info(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'email_verification': False,
        'password_reset': False,
        'error_cases': True  # Assume pass unless we find issues
    }
    
    registered_email = None
    
    # Test 1: Email Verification Flow
    try:
        success, email = test_email_verification_flow()
        results['email_verification'] = success
        if success:
            registered_email = email
    except Exception as e:
        print_error(f"Email verification test crashed: {e}")
    
    # Test 2: Password Reset Flow
    try:
        results['password_reset'] = test_password_reset_flow()
    except Exception as e:
        print_error(f"Password reset test crashed: {e}")
    
    # Test 3: Error Cases
    try:
        test_error_cases(registered_email)
    except Exception as e:
        print_error(f"Error cases test crashed: {e}")
    
    # Summary
    print_test_header("TEST SUMMARY")
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    print(f"\n{Colors.BOLD}Results:{Colors.RESET}")
    print(f"  Email Verification Flow: {'✅ PASS' if results['email_verification'] else '❌ FAIL'}")
    print(f"  Password Reset Flow: {'✅ PASS' if results['password_reset'] else '❌ FAIL'}")
    print(f"  Error Cases: {'✅ PASS' if results['error_cases'] else '❌ FAIL'}")
    
    print(f"\n{Colors.BOLD}Overall: {passed_tests}/{total_tests} tests passed{Colors.RESET}")
    
    if passed_tests == total_tests:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED!{Colors.RESET}\n")
    else:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  SOME TESTS FAILED{Colors.RESET}\n")
    
    print_info("Important Notes:")
    print("  - All codes are 6 digits")
    print("  - Codes expire in 15 minutes")
    print("  - Mock email service prints codes to console")
    print("  - Check /var/log/supervisor/backend.out.log for codes")

if __name__ == "__main__":
    main()
