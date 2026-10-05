import asyncio
import base64
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from core.security import get_current_user
from routers import quick_id_proxy
from services import quick_id_embedded as embedded

app = FastAPI()
app.include_router(quick_id_proxy.router)
app.dependency_overrides[get_current_user] = lambda: type("User", (), {"email": "staff@example.test"})()
client = TestClient(app)


def _png_data_url() -> str:
    output = io.BytesIO()
    Image.new("RGB", (80, 50), "white").save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def test_decode_image_rejects_non_image_and_oversized_payload(monkeypatch):
    with pytest.raises(ValueError, match="Geçersiz veya bozuk görüntü"):
        embedded._decode_image(base64.b64encode(b"not-an-image").decode("ascii"))

    monkeypatch.setattr(embedded, "MAX_IMAGE_BYTES", 4)
    with pytest.raises(ValueError, match="en fazla"):
        embedded._decode_image(_png_data_url())


def test_provider_catalog_reflects_runtime_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(embedded, "_tesseract_available", lambda: True)

    catalog = {item["id"]: item for item in embedded.provider_catalog({"openai": "secret"})}

    assert catalog["gpt-4o-mini"]["available"] is True
    assert catalog["gemini-flash"]["available"] is False
    assert catalog["tesseract"]["available"] is True


def test_scan_uses_embedded_provider_without_persisting_image(monkeypatch):
    async def fake_openai(_image, _mime, _key, model):
        assert model == "gpt-4o-mini"
        return {
            "document_count": 1,
            "documents": [
                {
                    "is_valid": True,
                    "document_type": "passport",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "document_number": "P123456",
                    "birth_date": "1815-12-10",
                    "warnings": [],
                }
            ],
        }

    monkeypatch.setattr(embedded, "_openai_scan", fake_openai)
    monkeypatch.setattr(embedded, "provider_catalog", lambda _keys=None: [{"id": "gpt-4o-mini", "name": "GPT", "available": True, "cost": "provider"}])

    result = asyncio.run(
        embedded.scan_document(
            _png_data_url(),
            provider=None,
            smart_mode=True,
            api_keys={"openai": "secret"},
        )
    )

    assert result["mode"] == "embedded"
    assert result["documents"][0]["document_number"] == "P123456"
    assert "image_base64" not in str(result)


def test_parse_json_whitelists_and_bounds_provider_output():
    result = embedded._parse_json(
        '{"documents":[{"is_valid":true,"document_type":"passport","first_name":"Ada","document_number":"P123","raw_extracted_text":"secret","address":"' + ("x" * 700) + '"}]}'
    )

    document = result["documents"][0]
    assert "raw_extracted_text" not in document
    assert len(document["address"]) == 500


def test_proxy_uses_embedded_scanner_when_external_url_is_absent(monkeypatch):
    async def fake_keys():
        return {"openai": "secret", "gemini": "", "preferred_provider": "gpt-4o-mini"}

    async def fake_scan(image_base64, *, provider, smart_mode, api_keys):
        assert image_base64 == "image"
        assert provider == "gpt-4o-mini"
        assert smart_mode is True
        assert api_keys["openai"] == "secret"
        return {"success": True, "mode": "embedded", "documents": []}

    monkeypatch.setattr(quick_id_proxy, "QUICKID_URL", "")
    monkeypatch.setattr(quick_id_proxy, "QUICKID_MODE", "embedded")
    monkeypatch.setattr(quick_id_proxy, "QUICKID_EMBEDDED_ENABLED", True)
    monkeypatch.setattr(quick_id_proxy, "_resolve_api_keys", fake_keys)
    monkeypatch.setattr(quick_id_proxy, "embedded_scan_document", fake_scan)

    response = client.post("/api/quick-id/scan", json={"image_base64": "image"})

    assert response.status_code == 200
    assert response.json()["mode"] == "embedded"
