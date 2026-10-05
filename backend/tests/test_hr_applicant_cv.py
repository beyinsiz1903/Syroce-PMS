import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from starlette.datastructures import UploadFile

import domains.hr.router as hr


class _ListCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


class _GridIn:
    def __init__(self):
        self._id = ObjectId()
        self.content = b""

    async def write(self, content):
        self.content = content

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_finance_applicant_list_hides_cv_fields(monkeypatch):
    applicants = SimpleNamespace(find=lambda *_args, **_kwargs: _ListCursor([{
        "id": "a1",
        "status": "new",
        "cv_url": "https://files.example/cv.pdf",
        "cv_document_id": "doc1",
        "cv_filename": "cv.pdf",
    }]))
    monkeypatch.setattr(hr, "db", SimpleNamespace(job_applicants=applicants))
    monkeypatch.setattr(hr, "_user_has_hr_op", lambda *_args: False)

    result = await hr.list_applicants(
        "job1",
        current_user=SimpleNamespace(tenant_id="qa", role="finance"),
        _perm=None,
    )

    assert result["items"][0]["cv_url"] is None
    assert result["items"][0]["cv_document_id"] is None
    assert result["items"][0]["cv_filename"] is None


@pytest.mark.asyncio
async def test_applicant_cv_upload_is_tenant_scoped_and_stored(monkeypatch):
    grid_in = _GridIn()
    bucket = SimpleNamespace(open_upload_stream=lambda *_args, **_kwargs: grid_in)
    job_applicants = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "a1", "job_id": "j1"}),
        update_one=AsyncMock(),
    )
    applicant_documents = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(hr, "db", SimpleNamespace(
        job_applicants=job_applicants,
        applicant_documents=applicant_documents,
    ))
    monkeypatch.setattr(hr, "_get_hr_docs_bucket", lambda: bucket)
    monkeypatch.setattr(hr, "validate_document_bytes", lambda content, **_kwargs: "application/pdf")
    file = UploadFile(filename="qa-cv.pdf", file=io.BytesIO(b"%PDF-qa"))
    file.headers = {"content-type": "application/pdf"}

    result = await hr.upload_applicant_cv(
        "a1",
        file,
        current_user=SimpleNamespace(tenant_id="qa", id="manager", role="supervisor"),
        _perm=None,
    )

    assert job_applicants.find_one.await_args.args[0] == {"tenant_id": "qa", "id": "a1"}
    assert grid_in.content == b"%PDF-qa"
    stored = applicant_documents.insert_one.await_args.args[0]
    assert stored["tenant_id"] == "qa" and stored["applicant_id"] == "a1"
    assert result["document"]["filename"] == "qa-cv.pdf"
