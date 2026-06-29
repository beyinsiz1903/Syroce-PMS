import os
from unittest.mock import patch
import pytest

from security.env_guard import enforce_production_safety_gate

@pytest.fixture
def clean_env():
    # A base environment containing required secrets so tests don't fail
    # on the basic secret check unless intentionally triggering it.
    return {
        "JWT_SECRET": "a_strong_production_secret_key_that_is_safe",
        "CM_MASTER_KEY_CURRENT": "a_strong_field_encryption_key_safe",
        "ALLOWED_ORIGINS": "https://app.syroce.com",
    }

def test_production_with_testing_flag_fails(clean_env):
    clean_env["ENV"] = "production"
    clean_env["TESTING"] = "1"
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run production with TESTING=1"):
            enforce_production_safety_gate()

def test_production_with_localhost_origin_fails(clean_env):
    clean_env["ENV"] = "production"
    clean_env["ALLOWED_ORIGINS"] = "https://app.syroce.com, http://localhost:3000"
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run production with dangerous ALLOWED_ORIGINS"):
            enforce_production_safety_gate()

def test_production_with_debug_fails(clean_env):
    clean_env["ENV"] = "production"
    clean_env["DEBUG"] = "true"
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run production with DEBUG=True"):
            enforce_production_safety_gate()

def test_production_with_empty_secret_fails(clean_env):
    clean_env["ENV"] = "production"
    clean_env["JWT_SECRET"] = ""  # Intentionally empty
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run production with missing, empty, or default JWT_SECRET"):
            enforce_production_safety_gate()

def test_production_with_dummy_secret_fails(clean_env):
    clean_env["ENV"] = "production"
    clean_env["CM_MASTER_KEY_CURRENT"] = "changeme"
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run production with missing, empty, or default CM_MASTER_KEY_CURRENT"):
            enforce_production_safety_gate()

def test_production_with_allowed_origins_unset_fails(clean_env):
    clean_env["ENV"] = "production"
    del clean_env["ALLOWED_ORIGINS"]
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run production without ALLOWED_ORIGINS explicitly set"):
            enforce_production_safety_gate()

def test_staging_with_cookie_secure_false_fails(clean_env):
    clean_env["ENV"] = "staging"
    clean_env["COOKIE_SECURE"] = "false"
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run staging with COOKIE_SECURE disabled"):
            enforce_production_safety_gate()

def test_development_allows_localhost_and_testing(clean_env):
    clean_env["ENV"] = "development"
    clean_env["ALLOWED_ORIGINS"] = "http://localhost:3000"
    clean_env["TESTING"] = "1"
    clean_env["COOKIE_SECURE"] = "false"
    clean_env["DEBUG"] = "true"
    
    # Should not raise any error
    with patch.dict(os.environ, clean_env, clear=True):
        enforce_production_safety_gate()

def test_test_environment_is_exempt(clean_env):
    clean_env["ENV"] = "test"
    clean_env["TESTING"] = "1"
    
    # Should not raise any error
    with patch.dict(os.environ, clean_env, clear=True):
        enforce_production_safety_gate()

def test_production_safe_env_passes(clean_env):
    clean_env["ENV"] = "production"
    clean_env["COOKIE_SECURE"] = "true"
    clean_env["ALLOWED_ORIGINS"] = "https://app.syroce.com, https://api.syroce.com"
    clean_env["DEBUG"] = "false"
    
    # Should not raise any error
    with patch.dict(os.environ, clean_env, clear=True):
        enforce_production_safety_gate()

def test_production_demo_password_fails(clean_env):
    clean_env["ENV"] = "production"
    clean_env["DEMO_PASSWORD"] = "some_password"
    
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(RuntimeError, match="Cannot run production with DEMO_PASSWORD set"):
            enforce_production_safety_gate()
