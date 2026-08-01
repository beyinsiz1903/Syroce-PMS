import asyncio
import logging
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from server import app

class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_records = []
    def emit(self, record):
        self.log_records.append(record.getMessage())

def run_tests():
    logger_hr = logging.getLogger("domains.channel_manager.providers.hotelrunner_security")
    logger_hw = logging.getLogger("domains.channel_manager.providers.hotelrunner_webhook")
    logger_qid = logging.getLogger("quick_id_proxy")
    
    handler = ListHandler()
    logger_hr.addHandler(handler)
    logger_hw.addHandler(handler)
    logger_qid.addHandler(handler)
    logger_hr.setLevel(logging.INFO)
    logger_hw.setLevel(logging.INFO)
    logger_qid.setLevel(logging.INFO)

    try:
        with patch.dict("os.environ", {
            "HOTELRUNNER_WEBHOOK_SECRET": "super-secret-hr-webhook",
            "HOTELRUNNER_CALLBACK_SECRET": "super-secret-hr-callback",
            "QUICKID_SERVICE_KEY": "super-secret-qid-key"
        }):
            client = TestClient(app)
            
            headers = {
                "X-HotelRunner-Signature": "sha256=invalid-signature-12345",
                "X-HotelRunner-Timestamp": "1234567890",
                "X-Tenant-ID": "tenant-id-full-uuid-123",
                "X-Request-ID": "test-req-id"
            }
            
            async def fake_lookup(hint):
                return {"hr_id": "hr-123", "tenant_id": "tenant-id-full-uuid-123"}
            
            import domains.channel_manager.providers.hotelrunner_security as hsec
            with patch.object(hsec, "_lookup_signing_connection", new=fake_lookup):
                client.post("/api/channel-manager/hotelrunner/callback", headers=headers, json={"hotel_id": "hr-123"})
            
            token = "long-token-1234567890abcdef"
            class MockResponse:
                status_code = 200
                def json(self): return {}
            async def mock_get(*args, **kwargs):
                return MockResponse()
            
            with patch.object(httpx.AsyncClient, "get", new=mock_get):
                client.get(f"/api/quick-id/precheckin/{token}/info", headers={"X-Request-ID": "test-req-qid"})
            
            logs = "\n".join(handler.log_records)
            
            assert "super-secret-hr-webhook" not in logs, "Webhook secret leaked!"
            assert "super-secret-hr-callback" not in logs, "Callback secret leaked!"
            assert "invalid-signature-12345" not in logs, "Signature leaked!"
            assert "super-secret-qid-key" not in logs, "Quick-ID key leaked!"
            assert token not in logs, "Full token leaked!"
            assert "tenant-id-full-uuid-123" not in logs, "Full tenant ID leaked!"
            
            print("Tests passed successfully! No secrets found in logs.")
            # Verify that our DIAG logs actually appeared
            assert "[DIAG] [test-req-id]" in logs, "HR Diag logs missing"
            assert "[DIAG] [test-req-qid]" in logs, "QID Diag logs missing"
            print("Diagnostics confirmed working.")
            
    finally:
        logger_hr.removeHandler(handler)
        logger_hw.removeHandler(handler)
        logger_qid.removeHandler(handler)

if __name__ == "__main__":
    run_tests()
