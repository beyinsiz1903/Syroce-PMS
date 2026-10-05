from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import domains.hr.router as hr


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def skip(self, _value):
        return self

    def limit(self, _value):
        return self

    def __aiter__(self):
        async def rows():
            for row in self.rows:
                yield row
        return rows()


@pytest.mark.asyncio
async def test_system_users_include_staff_and_decrypt_pii(monkeypatch):
    encrypted = {
        "id": "user-1",
        "name": "QA Çalışan",
        "email": "SYR1:ciphertext",
        "phone": "SYR1:ciphertext",
        "role": "staff",
        "created_at": "2026-09-08T00:00:00+00:00",
    }
    users = SimpleNamespace(
        count_documents=AsyncMock(return_value=1),
        find=lambda *_args, **_kwargs: _Cursor([encrypted]),
    )
    monkeypatch.setattr(hr, "db", SimpleNamespace(users=users))
    monkeypatch.setattr(
        hr,
        "decrypt_user_doc",
        lambda row: {**row, "email": "qa.employee@syroce.com", "phone": "+905551234567"},
    )
    monkeypatch.setattr(hr, "_user_has_hr_op", lambda *_args: True)

    result = await hr.get_staff_list(
        source="users",
        page=1,
        limit=50,
        current_user=SimpleNamespace(id="manager", email="manager@syroce.com", role="supervisor", tenant_id="qa"),
        _perm=None,
    )

    assert "staff" in users.count_documents.await_args.args[0]["role"]["$in"]
    assert result["staff"][0]["email"] == "qa.employee@syroce.com"
    assert result["staff"][0]["phone"] == "+905551234567"
