import pytest
from starlette.testclient import TestClient
from server import app
import logging

@pytest.fixture
def client_with_error():
    # Register a temporary endpoint for testing error logging leakage
    @app.get("/api/test-error-leakage")
    async def test_error_leakage(t: str = "query_token"):
        raise ValueError(
            "Database connection failed: mysql://admin:super_secret_db_pass@localhost/db "
            "token=fake_plaintext_guest_token_123 "
            "token_hash=fake_hash_abcxyz "
            "guest_name=John Doe"
        )
    
    return TestClient(app, raise_server_exceptions=False)

def test_production_app_log_leakage(client_with_error, caplog):
    # Capture logs from the specific logger
    caplog.set_level(logging.ERROR, logger="uvicorn.error")
    
    # 1. Trigger the error with query parameters and headers
    response = client_with_error.get(
        "/api/test-error-leakage?t=fake_token_in_query",
        headers={"X-Guest-Session": "fake_header_token"}
    )
    
    # 2. Assert HTTP response is completely safe
    assert response.status_code == 500
    assert "application/json" in response.headers.get("content-type", "")
    assert response.json() == {"detail": "Internal Server Error"}
    
    # 3. Assert sensitive markers are ABSENT from response body
    body = response.text
    assert "super_secret_db_pass" not in body
    assert "fake_plaintext_guest_token_123" not in body
    assert "fake_hash_abcxyz" not in body
    assert "John Doe" not in body
    assert "fake_token_in_query" not in body
    assert "fake_header_token" not in body
    assert "ValueError" not in body

    # 4. Assert sensitive markers are ABSENT from logs
    log_text = caplog.text
    
    # Check what was actually logged to ensure the handler ran
    assert "Unhandled application exception" in log_text
    assert "[error_id=" in log_text
    assert "method=GET" in log_text
    assert "path=/api/test-error-leakage" in log_text
    
    # Check absense of leaks
    assert "super_secret_db_pass" not in log_text
    assert "fake_plaintext_guest_token_123" not in log_text
    assert "fake_hash_abcxyz" not in log_text
    assert "John Doe" not in log_text
    assert "fake_token_in_query" not in log_text
    assert "fake_header_token" not in log_text
    assert "ValueError" not in log_text
    assert "Database connection failed" not in log_text

    # Verify no full request URL is logged containing query string
    assert "?t=fake_token_in_query" not in log_text
