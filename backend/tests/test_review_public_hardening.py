"""Task #318 — Misafir Yorumu Halka Açık Yüzey Sertleştirme.

Kapsam (production-scoped, halka açık + PII hassas):
- survey_responses: gün-bazlı tekil oyun DB-seviyesi race guard'ı (DuplicateKeyError -> 409)
  + vote_day partial-unique alanının yalnız booking_id varken yazılması.
- guest_reviews: davet başına tek yorum (invite_token DB zırhı) — DuplicateKeyError -> 410,
  claim pending'e GERİ ALINMAZ (davet zaten kullanılmış), submitted'a uzlaştırılır.
- Halka açık GET/POST: IP-bazlı rate-limit (429), payload boyut sınırı (413).
- Tenant izolasyonu: yorumun tenant'ı client'tan DEĞİL invite dokümanından türetilir.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import domains.guest.experience_router.feedback as feedback_mod

# Gerçek ensure fonksiyonu referansı (autouse fixture onu no-op'larken bile
# index retry davranışını doğrudan test edebilmek için).
_REAL_ENSURE = feedback_mod._ensure_single_vote_indexes


# ---- fakes ---------------------------------------------------------------

class _SurveyResponsesColl:
    def __init__(self, dup=None, insert_exc=None):
        self._dup = dup
        self._insert_exc = insert_exc
        self.inserts = []

    async def find_one(self, query, *a, **k):
        return self._dup

    async def insert_one(self, doc):
        if self._insert_exc:
            raise self._insert_exc
        self.inserts.append(doc)
        return SimpleNamespace(inserted_id="x")


class _Surveys:
    def __init__(self, survey):
        self._survey = survey

    async def find_one(self, query, *a, **k):
        return self._survey


class _InviteColl:
    def __init__(self, pre=None, claim=None):
        self._pre = pre
        self._claim = claim
        self.updates = []

    async def find_one(self, query, *a, **k):
        return self._pre

    async def find_one_and_update(self, query, update, *a, **k):
        return self._claim

    async def update_one(self, query, update, *a, **k):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)


class _ReviewColl:
    def __init__(self, insert_exc=None):
        self._insert_exc = insert_exc
        self.inserts = []

    async def insert_one(self, doc):
        if self._insert_exc:
            raise self._insert_exc
        self.inserts.append(doc)
        return SimpleNamespace(inserted_id="r")


class _Cache:
    def __init__(self, value):
        self.value = value

    def incr_with_ttl(self, key, ttl):
        return self.value


def _user():
    return SimpleNamespace(tenant_id="t1")


def _survey_req(booking_id="b1"):
    return SimpleNamespace(
        survey_id="s1",
        booking_id=booking_id,
        guest_name="Guest",
        guest_email="g@example.com",
        responses=[{"rating": 9}],
    )


def _request(host="203.0.113.7", content_length=None, xff=None):
    headers = {}
    if content_length is not None:
        headers["content-length"] = str(content_length)
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers)


def _future():
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) + timedelta(days=5)).isoformat()


@pytest.fixture(autouse=True)
def _skip_index_ensure(monkeypatch):
    async def _noop():
        return None
    monkeypatch.setattr(feedback_mod, "_ensure_single_vote_indexes", _noop)
    # Rate-limit'i varsayılan olarak serbest bırak (1 <= limit)
    monkeypatch.setattr(feedback_mod, "_cache", _Cache(1))


# ---- survey_responses DB race guard --------------------------------------

@pytest.mark.asyncio
async def test_survey_duplicatekey_returns_409(monkeypatch):
    """find_one pre-check geçse bile eşzamanlı ikinci yazım partial-unique
    index'e takılır -> DuplicateKeyError -> 409 (skip-as-pass YOK)."""
    responses = _SurveyResponsesColl(dup=None, insert_exc=DuplicateKeyError("dup"))
    db = SimpleNamespace(surveys=_Surveys({"id": "s1", "survey_name": "NPS"}),
                         survey_responses=responses)
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.submit_survey_response(_survey_req("b1"), current_user=_user())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_survey_vote_day_written_when_booking_present(monkeypatch):
    responses = _SurveyResponsesColl(dup=None)
    db = SimpleNamespace(surveys=_Surveys({"id": "s1", "survey_name": "NPS"}),
                         survey_responses=responses)
    monkeypatch.setattr(feedback_mod, "db", db)
    await feedback_mod.submit_survey_response(_survey_req("b1"), current_user=_user())
    assert len(responses.inserts) == 1
    assert "vote_day" in responses.inserts[0]


@pytest.mark.asyncio
async def test_survey_vote_day_absent_without_booking(monkeypatch):
    responses = _SurveyResponsesColl(dup=None)
    db = SimpleNamespace(surveys=_Surveys({"id": "s1", "survey_name": "NPS"}),
                         survey_responses=responses)
    monkeypatch.setattr(feedback_mod, "db", db)
    await feedback_mod.submit_survey_response(_survey_req(None), current_user=_user())
    assert len(responses.inserts) == 1
    assert "vote_day" not in responses.inserts[0]


# ---- public GET: rate-limit ----------------------------------------------

@pytest.mark.asyncio
async def test_public_get_rate_limited(monkeypatch):
    monkeypatch.setattr(feedback_mod, "_cache", _Cache(999))  # limit aşıldı
    db = SimpleNamespace(review_invites=_InviteColl(pre={"token": "a" * 32}))
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.get_review_invite_public("a" * 32, request=_request())
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_public_get_rate_limit_fail_open(monkeypatch):
    """Cache erişilemez (sayaç=0) -> fail-open: talep işlenir (lookup'a düşer)."""
    monkeypatch.setattr(feedback_mod, "_cache", _Cache(0))
    invite = {"token": "a" * 32, "status": "pending", "expires_at": _future(),
              "hotel_name": "H", "guest_name": "G"}
    db = SimpleNamespace(review_invites=_InviteColl(pre=invite))
    monkeypatch.setattr(feedback_mod, "db", db)
    res = await feedback_mod.get_review_invite_public("a" * 32, request=_request())
    assert res["hotel_name"] == "H"


# ---- public POST: payload size + rate-limit ------------------------------

@pytest.mark.asyncio
async def test_public_post_body_too_large(monkeypatch):
    db = SimpleNamespace(review_invites=_InviteColl())
    monkeypatch.setattr(feedback_mod, "db", db)
    big = feedback_mod._PUBLIC_MAX_BODY_BYTES + 1
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.submit_review_public(
            "a" * 32, {"rating": 5}, request=_request(content_length=big)
        )
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_public_post_rate_limited(monkeypatch):
    monkeypatch.setattr(feedback_mod, "_cache", _Cache(999))
    db = SimpleNamespace(review_invites=_InviteColl())
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.submit_review_public(
            "a" * 32, {"rating": 5}, request=_request()
        )
    assert exc.value.status_code == 429


# ---- public POST: tenant binding + DB zırhı ------------------------------

@pytest.mark.asyncio
async def test_public_post_happy_path_binds_invite_tenant(monkeypatch):
    """Yorumun tenant'ı client'tan DEĞİL invite dokümanından gelir; review'a
    invite_token yazılır; davet submitted'a geçer."""
    token = "a" * 32
    pre = {"status": "pending", "expires_at": _future()}
    claim = {"_id": "oid1", "tenant_id": "tenantX", "guest_name": "Ada",
             "booking_id": "bk9"}
    invites = _InviteColl(pre=pre, claim=claim)
    reviews = _ReviewColl()
    db = SimpleNamespace(review_invites=invites, guest_reviews=reviews)
    monkeypatch.setattr(feedback_mod, "db", db)
    res = await feedback_mod.submit_review_public(
        token, {"rating": 4, "comment": "iyi", "guest_name": "Hacker"},
        request=_request(),
    )
    assert res["success"] is True
    assert len(reviews.inserts) == 1
    doc = reviews.inserts[0]
    assert doc["tenant_id"] == "tenantX"        # client değil, invite'tan
    assert doc["invite_token"] == token          # DB zırhı alanı
    # davet submitted'a işaretlendi
    assert any(u[1]["$set"].get("status") == "submitted" for u in invites.updates)


@pytest.mark.asyncio
async def test_public_post_duplicate_review_returns_410_no_rollback(monkeypatch):
    """guest_reviews DuplicateKeyError -> 410; claim pending'e GERİ ALINMAZ,
    submitted'a uzlaştırılır."""
    token = "a" * 32
    pre = {"status": "pending", "expires_at": _future()}
    claim = {"_id": "oid1", "tenant_id": "tenantX", "guest_name": "Ada"}
    invites = _InviteColl(pre=pre, claim=claim)
    reviews = _ReviewColl(insert_exc=DuplicateKeyError("dup"))
    db = SimpleNamespace(review_invites=invites, guest_reviews=reviews)
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.submit_review_public(token, {"rating": 5}, request=_request())
    assert exc.value.status_code == 410
    statuses = [u[1]["$set"].get("status") for u in invites.updates]
    assert "submitted" in statuses
    assert "pending" not in statuses  # geri alma YOK


@pytest.mark.asyncio
async def test_public_post_lost_claim_returns_410(monkeypatch):
    """Atomik claim başka istek tarafından alınmış (find_one_and_update None) -> 410."""
    token = "a" * 32
    pre = {"status": "pending", "expires_at": _future()}
    invites = _InviteColl(pre=pre, claim=None)
    db = SimpleNamespace(review_invites=invites, guest_reviews=_ReviewColl())
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.submit_review_public(token, {"rating": 5}, request=_request())
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_public_post_transient_error_rolls_back_to_pending(monkeypatch):
    """Geçici (non-duplicate) hata -> claim pending'e geri alınır, hata yeniden fırlatılır."""
    token = "a" * 32
    pre = {"status": "pending", "expires_at": _future()}
    claim = {"_id": "oid1", "tenant_id": "tenantX", "guest_name": "Ada"}
    invites = _InviteColl(pre=pre, claim=claim)
    reviews = _ReviewColl(insert_exc=RuntimeError("db down"))
    db = SimpleNamespace(review_invites=invites, guest_reviews=reviews)
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(RuntimeError):
        await feedback_mod.submit_review_public(token, {"rating": 5}, request=_request())
    statuses = [u[1]["$set"].get("status") for u in invites.updates]
    assert "pending" in statuses  # retry için geri alındı


# ---- token validation (badge: invalid -> 400) ----------------------------

@pytest.mark.asyncio
async def test_index_ensure_not_marked_ready_on_failure(monkeypatch):
    """Index kurulumu başarısızsa READY bayrağı SET EDİLMEZ → bir sonraki
    istekte tekrar denenir (invariant üzerinde fake-green YOK)."""
    class _FailColl:
        async def create_index(self, *a, **k):
            raise RuntimeError("index build failed")

    db = SimpleNamespace(survey_responses=_FailColl(), guest_reviews=_FailColl())
    monkeypatch.setattr(feedback_mod, "db", db)
    monkeypatch.setattr(feedback_mod, "_SINGLE_VOTE_INDEX_READY", False)
    # autouse fixture ensure'u no-op'lar; burada GERÇEK fonksiyonu test ediyoruz
    await _REAL_ENSURE()
    assert feedback_mod._SINGLE_VOTE_INDEX_READY is False


@pytest.mark.asyncio
async def test_public_post_invalid_token_400(monkeypatch):
    db = SimpleNamespace(review_invites=_InviteColl())
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.submit_review_public("BADTOKEN", {"rating": 5}, request=_request())
    assert exc.value.status_code == 400
