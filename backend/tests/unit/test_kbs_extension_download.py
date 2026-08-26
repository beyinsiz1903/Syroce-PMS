from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import kbs


@pytest.mark.asyncio
async def test_download_uses_packaged_extension_archive(monkeypatch, tmp_path: Path):
    archive_path = tmp_path / "kbs.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("syroce-kbs-eklentisi/manifest.json", '{"manifest_version": 3}')
        archive.writestr("syroce-kbs-eklentisi/background.js", "void 0;")

    monkeypatch.setattr(kbs, "_kbs_extension_archive", lambda: archive_path)
    monkeypatch.setattr(kbs, "_kbs_extension_dir", lambda: tmp_path / "missing")

    response = await kbs.download_kbs_extension(SimpleNamespace(id="user-1"))

    assert response.media_type == "application/zip"
    assert response.headers["content-disposition"].endswith('"syroce-kbs-eklentisi.zip"')
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert "syroce-kbs-eklentisi/manifest.json" in archive.namelist()


@pytest.mark.asyncio
async def test_download_rejects_invalid_packaged_archive(monkeypatch, tmp_path: Path):
    archive_path = tmp_path / "broken.zip"
    archive_path.write_bytes(b"not-a-zip")
    monkeypatch.setattr(kbs, "_kbs_extension_archive", lambda: archive_path)

    with pytest.raises(HTTPException) as exc_info:
        await kbs.download_kbs_extension(SimpleNamespace(id="user-1"))

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_download_falls_back_to_source_tree(monkeypatch, tmp_path: Path):
    extension_dir = tmp_path / "extension"
    extension_dir.mkdir()
    (extension_dir / "manifest.json").write_text('{"manifest_version": 3}', encoding="utf-8")
    (extension_dir / "background.js").write_text("void 0;", encoding="utf-8")
    tests_dir = extension_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "ignored.js").write_text("throw new Error();", encoding="utf-8")

    monkeypatch.setattr(kbs, "_kbs_extension_archive", lambda: tmp_path / "missing.zip")
    monkeypatch.setattr(kbs, "_kbs_extension_dir", lambda: extension_dir)

    response = await kbs.download_kbs_extension(SimpleNamespace(id="user-1"))

    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert "syroce-kbs-eklentisi/manifest.json" in archive.namelist()
        assert all("/tests/" not in name for name in archive.namelist())
