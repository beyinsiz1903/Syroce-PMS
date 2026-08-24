import os
import pytest
from fastapi import HTTPException
from unittest.mock import patch
from domains.admin.router.stress import _gates

def test_gates_valid_stress_tid():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123", "E2E_ALLOW_DESTRUCTIVE_STRESS": "true"}):
        result = _gates("stress-123")
        assert result["target_matches_stress_tid"] is True
        assert result["env_stress_tid_present"] is True

def test_gates_valid_pos_tid():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123", "E2E_ALLOW_DESTRUCTIVE_STRESS": "true"}):
        result = _gates("pos-123")
        assert result["target_matches_stress_tid"] is True

def test_gates_random_tenant_rejected():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123"}):
        with pytest.raises(HTTPException) as exc:
            _gates("random-456")
        assert exc.value.status_code == 403
        assert "not an allowed stress tenant" in str(exc.value.detail)

def test_gates_empty_tenant_rejected():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123"}):
        with pytest.raises(HTTPException) as exc:
            _gates("")
        assert exc.value.status_code == 403
        assert "not an allowed stress tenant" in str(exc.value.detail)

def test_gates_empty_tenant_rejected_when_pos_env_missing():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123"}, clear=True):
        with pytest.raises(HTTPException) as exc:
            _gates("")
        assert exc.value.status_code == 403
        assert "not an allowed stress tenant" in str(exc.value.detail)
