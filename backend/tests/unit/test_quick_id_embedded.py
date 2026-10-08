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


def test_tesseract_parser_reads_bilingual_turkish_id_labels_from_following_lines():
    text = """TÜRKİYE CUMHURİYETİ KİMLİK KARTI
T.C. Kimlik No / TR Identity No
12345678901
Soyadı / Surname
YILMAZ
Adı / Given Name(s)
ALİ CAN
Doğum Tarihi / Date of Birth   Cinsiyeti / Gender
15.08.1992                     E / M
Seri No / Document No
A12B34567
Uyruğu / Nationality
T.C. / TUR
Son Geçerlilik / Valid Until
01.09.2033
"""

    document = embedded._parse_tesseract_text(text)

    assert document["is_valid"] is True
    assert document["first_name"] == "ALİ CAN"
    assert document["last_name"] == "YILMAZ"
    assert document["id_number"] == "12345678901"
    assert document["birth_date"] == "1992-08-15"
    assert document["expiry_date"] == "2033-09-01"


def test_tesseract_parser_removes_bilingual_heading_from_inline_value():
    text = """T.C. Kimlik No / TR Identity No 12345678901
Soyadı / Surname YILMAZ
Adı / Given Name(s) ALİ CAN
15.08.1992
"""

    document = embedded._parse_tesseract_text(text)

    assert document["first_name"] == "ALİ CAN"
    assert document["last_name"] == "YILMAZ"
    assert document["is_valid"] is True


def test_scan_maps_local_ocr_recognition_failure_to_validation_error(monkeypatch):
    async def unreadable(_image):
        raise ValueError("Kimlik alanları güvenilir biçimde okunamadı")

    monkeypatch.setattr(embedded, "_tesseract_scan", unreadable)
    monkeypatch.setattr(
        embedded,
        "provider_catalog",
        lambda _keys=None: [{"id": "tesseract", "name": "Tesseract", "available": True, "cost": 0}],
    )

    with pytest.raises(ValueError, match="güvenilir"):
        asyncio.run(
            embedded.scan_document(
                _png_data_url(),
                provider=None,
                smart_mode=True,
                api_keys={},
            )
        )


def test_tesseract_preprocessing_crops_and_rectifies_identity_card():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    canvas = np.full((700, 1000, 3), 55, dtype=np.uint8)
    card = np.full((360, 570, 3), 238, dtype=np.uint8)
    cv2.rectangle(card, (5, 5), (565, 355), (15, 15, 15), 8)
    cv2.putText(card, "TURKIYE CUMHURIYETI KIMLIK KARTI", (35, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2)
    cv2.putText(card, "12345678901", (45, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.25, (20, 20, 20), 3)
    source = np.float32([[0, 0], [569, 0], [569, 359], [0, 359]])
    destination = np.float32([[180, 130], [820, 80], [860, 560], [130, 610]])
    transformed = cv2.warpPerspective(card, cv2.getPerspectiveTransform(source, destination), (1000, 700))
    mask = cv2.warpPerspective(np.full((360, 570), 255, dtype=np.uint8), cv2.getPerspectiveTransform(source, destination), (1000, 700))
    canvas[mask > 0] = transformed[mask > 0]
    ok, encoded = cv2.imencode(".jpg", canvas)
    assert ok

    prepared = embedded._prepare_tesseract_image(encoded.tobytes())

    assert prepared.width > prepared.height
    assert 1.35 < prepared.width / prepared.height < 1.85
    assert prepared.mode == "L"
    assert np.asarray(prepared).std() > 20


def test_tesseract_preprocessing_falls_back_when_opencv_fails(monkeypatch):
    monkeypatch.setattr(
        embedded,
        "_prepare_tesseract_image_opencv",
        lambda _image: (_ for _ in ()).throw(RuntimeError("native library unavailable")),
    )
    image_bytes, _ = embedded._decode_image(_png_data_url())

    prepared = embedded._prepare_tesseract_image(image_bytes)

    assert prepared.mode == "L"
    assert prepared.size == (116, 86)


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


def test_proxy_returns_422_when_embedded_ocr_cannot_read_the_card(monkeypatch):
    async def fake_keys():
        return {"openai": "", "gemini": "", "preferred_provider": None}

    async def unreadable_scan(*_args, **_kwargs):
        raise ValueError("Kimlik alanları güvenilir biçimde okunamadı")

    monkeypatch.setattr(quick_id_proxy, "QUICKID_MODE", "embedded")
    monkeypatch.setattr(quick_id_proxy, "QUICKID_EMBEDDED_ENABLED", True)
    monkeypatch.setattr(quick_id_proxy, "_resolve_api_keys", fake_keys)
    monkeypatch.setattr(quick_id_proxy, "embedded_scan_document", unreadable_scan)

    response = client.post("/api/quick-id/scan", json={"image_base64": "image"})

    assert response.status_code == 422
    assert "güvenilir" in response.json()["detail"]
