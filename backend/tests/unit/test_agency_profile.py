"""Agency portal users manage their own name and password."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.security import hash_password, verify_password
from routers import agency_onboarding as onboarding


class _Users:
    def __init__(self, rows):
        self.rows = rows

    async def find_one(self, query, *_a, **_k):
        return next((dict(r) for r in self.rows if all(r.get(k) == v for k, v in query.items())), None)

    async def update_one(self, query, update):
        for row in self.rows:
            if all(row.get(k) == v for k, v in query.items()):
                row.update(update["$set"])
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


AGENCY = {"agency_id": "a1", "user": {"id": "u1", "name": "Test Yetkili", "email": "x@example.com"}, "impersonation": None}
REQUEST = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})


@pytest.fixture
def users(monkeypatch):
    store = _Users([{"id": "u1", "agency_id": "a1", "name": "Test Yetkili", "hashed_password": hash_password("EskiSifre1234")}])
    monkeypatch.setattr(onboarding, "get_system_db", lambda: SimpleNamespace(users=store, marketplace_audit_logs=SimpleNamespace(insert_one=AsyncMock())))
    import importlib

    monkeypatch.setattr(importlib.import_module("security.auth_throttle"), "enforce", AsyncMock())
    monkeypatch.setattr(importlib.import_module("core.security"), "invalidate_user_doc_cache", lambda _uid: None)
    return store


@pytest.mark.asyncio
async def test_user_renames_themself(users):
    assert (await onboarding.update_profile(onboarding.ProfileUpdate(name="  Ayşe Yılmaz "), AGENCY))["name"] == "Ayşe Yılmaz"
    assert users.rows[0]["name"] == "Ayşe Yılmaz"


@pytest.mark.asyncio
async def test_password_change_rules(users):
    change = lambda current, new: onboarding.change_password(  # noqa: E731
        onboarding.PasswordChange(current_password=current, new_password=new), REQUEST, AGENCY)
    with pytest.raises(HTTPException) as wrong:
        await change("Yanlis", "YeniSifre12345")
    assert wrong.value.status_code == 400
    with pytest.raises(HTTPException) as weak:
        await change("EskiSifre1234", "zayifsifre12")
    assert weak.value.status_code == 422

    result = await change("EskiSifre1234", "YeniSifre12345")
    assert result["token"]
    row = users.rows[0]
    assert verify_password("YeniSifre12345", row["hashed_password"]) and row["tokens_invalid_before"] > 0


@pytest.mark.asyncio
async def test_superadmin_preview_cannot_change_profile(users):
    preview = {**AGENCY, "impersonation": {"active": True}}
    with pytest.raises(HTTPException) as exc:
        await onboarding.update_profile(onboarding.ProfileUpdate(name="Başkası"), preview)
    assert exc.value.status_code == 403
    assert (await onboarding.get_profile(preview))["can_edit"] is False
