import os
import time
import pytest
import jwt
import sys
import base64
import json
from datetime import timedelta
from importlib import import_module

def reload_security_module():
    if "core.security" in sys.modules:
        del sys.modules["core.security"]
    import core.security
    return sys.modules["core.security"]

@pytest.fixture(autouse=True)
def reset_jwt_secret():
    original = os.environ.get("JWT_SECRET")
    yield
    if original is None:
        os.environ.pop("JWT_SECRET", None)
    else:
        os.environ["JWT_SECRET"] = original

def test_omni_sec_ut_001_no_secret_fails():
    """OMNI-SEC-UT-001: JWT_SECRET yoksa uygulama başlamamalı"""
    os.environ.pop("JWT_SECRET", None)
    
    with pytest.raises(RuntimeError) as exc_info:
        reload_security_module()
    
    assert "must be configured and contain at least 32 characters" in str(exc_info.value)

def test_omni_sec_ut_002_short_secret_fails():
    """OMNI-SEC-UT-002: JWT_SECRET 32 karakterden kısaysa uygulama başlamamalı"""
    os.environ["JWT_SECRET"] = "short-secret"
    
    with pytest.raises(RuntimeError) as exc_info:
        reload_security_module()
    
    assert "must be configured and contain at least 32 characters" in str(exc_info.value)

def test_omni_sec_ut_003_valid_secret_works():
    """OMNI-SEC-UT-003: Geçerli secret ile token oluşturma ve çözme çalışmalı"""
    os.environ["JWT_SECRET"] = "this-is-a-valid-secret-that-is-long-enough"
    sec = reload_security_module()
    
    token = sec.create_token(user_id="test_user", tenant_id="test_tenant")
    
    decoded = jwt.decode(token, sec.JWT_SECRET, algorithms=[sec.JWT_ALGORITHM])
    assert decoded["user_id"] == "test_user"
    assert decoded["tenant_id"] == "test_tenant"

def test_omni_sec_ut_004_invalid_secret_fails():
    """OMNI-SEC-UT-004: Başka secret ile üretilen token reddedilmeli"""
    os.environ["JWT_SECRET"] = "this-is-a-valid-secret-that-is-long-enough"
    sec = reload_security_module()
    
    payload = {"user_id": "test_user", "tenant_id": "test_tenant"}
    token = jwt.encode(payload, "this-is-another-valid-secret-that-is-long-enough", algorithm="HS256")
    
    with pytest.raises(jwt.exceptions.InvalidSignatureError):
        jwt.decode(token, sec.JWT_SECRET, algorithms=[sec.JWT_ALGORITHM])

def test_omni_sec_ut_005_expired_token_fails():
    """OMNI-SEC-UT-005: Süresi dolmuş token 401 dönmeli"""
    os.environ["JWT_SECRET"] = "this-is-a-valid-secret-that-is-long-enough"
    sec = reload_security_module()
    
    # create a token manually that is already expired
    import datetime
    payload = {
        "user_id": "test_user", 
        "tenant_id": "test_tenant",
        "exp": datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1)
    }
    token = jwt.encode(payload, sec.JWT_SECRET, algorithm="HS256")
    
    with pytest.raises(jwt.exceptions.ExpiredSignatureError):
        jwt.decode(token, sec.JWT_SECRET, algorithms=[sec.JWT_ALGORITHM])

def test_omni_sec_ut_006_tenant_isolation():
    """OMNI-SEC-UT-006: Token içindeki tenant değiştirilerek yapılan erişim reddedilmeli"""
    os.environ["JWT_SECRET"] = "this-is-a-valid-secret-that-is-long-enough"
    sec = reload_security_module()
    
    token = sec.create_token(user_id="test_user", tenant_id="tenant_a")
    
    # Alter token payload
    parts = token.split(".")
    padding = '=' * (-len(parts[1]) % 4)
    new_payload = json.loads(base64.urlsafe_b64decode(parts[1] + padding).decode())
    new_payload["tenant_id"] = "tenant_b"
    
    parts[1] = base64.urlsafe_b64encode(json.dumps(new_payload).encode()).decode().rstrip("=")
    altered_token = ".".join(parts)
    
    # Decoding altered token must fail due to signature invalidation
    with pytest.raises(jwt.exceptions.InvalidSignatureError):
        jwt.decode(altered_token, sec.JWT_SECRET, algorithms=[sec.JWT_ALGORITHM])
