import base64
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from domains.pms.mobile_router.maintenance import _decode_maintenance_photo


def _one_pixel_png_base64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_maintenance_photo_is_canonicalized_after_magic_byte_validation():
    photo_url, content_type = _decode_maintenance_photo(
        f"data:image/svg+xml;base64,{_one_pixel_png_base64()}"
    )

    assert content_type == "image/png"
    assert photo_url.startswith("data:image/png;base64,")


def test_maintenance_photo_rejects_non_base64_payload():
    with pytest.raises(HTTPException, match="valid Base64"):
        _decode_maintenance_photo("not-a-photo")
