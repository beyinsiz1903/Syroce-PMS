"""Wave 9 — NPS / survey response one-per-booking-per-day guard.

Product decision: a single survey response per (survey, booking) per UTC day.
Prevents ballot-stuffing / duplicate NPS rows. Ad-hoc responses without a
booking_id are exempt (cannot be deduplicated). Contained to the single
submit insert path.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import domains.guest.experience_router.feedback as feedback_mod


class _Coll:
    def __init__(self, find_one_result=None):
        self._find_one_result = find_one_result
        self.find_one_queries = []
        self.inserts = []

    async def find_one(self, query, *a, **k):
        self.find_one_queries.append(query)
        return self._find_one_result

    async def insert_one(self, doc):
        self.inserts.append(doc)
        return SimpleNamespace(inserted_id="x")


def _user():
    return SimpleNamespace(tenant_id="t1")


def _req(booking_id="b1"):
    return SimpleNamespace(
        survey_id="s1",
        booking_id=booking_id,
        guest_name="Guest",
        guest_email="g@example.com",
        responses=[{"rating": 9}],
    )


def _db(surveys_result, responses_dup):
    surveys = _Coll(find_one_result=surveys_result)
    responses = _Coll(find_one_result=responses_dup)
    return SimpleNamespace(surveys=surveys, survey_responses=responses), surveys, responses


@pytest.mark.asyncio
async def test_duplicate_same_day_booking_rejected(monkeypatch):
    db, _, responses = _db({"id": "s1", "survey_name": "NPS"}, {"id": "existing"})
    monkeypatch.setattr(feedback_mod, "db", db)
    with pytest.raises(HTTPException) as exc:
        await feedback_mod.submit_survey_response(_req("b1"), current_user=_user())
    assert exc.value.status_code == 409
    assert responses.inserts == []
    # the dup query is tenant + survey + booking + day-range scoped
    q = responses.find_one_queries[0]
    assert q["tenant_id"] == "t1" and q["survey_id"] == "s1" and q["booking_id"] == "b1"
    assert "$gte" in q["submitted_at"] and "$lt" in q["submitted_at"]


@pytest.mark.asyncio
async def test_first_response_allowed(monkeypatch):
    db, _, responses = _db({"id": "s1", "survey_name": "NPS"}, None)
    monkeypatch.setattr(feedback_mod, "db", db)
    res = await feedback_mod.submit_survey_response(_req("b1"), current_user=_user())
    assert "response_id" in res
    assert len(responses.inserts) == 1


@pytest.mark.asyncio
async def test_no_booking_id_skips_dup_guard(monkeypatch):
    db, _, responses = _db({"id": "s1", "survey_name": "NPS"}, {"id": "would-block"})
    monkeypatch.setattr(feedback_mod, "db", db)
    res = await feedback_mod.submit_survey_response(_req(None), current_user=_user())
    assert "response_id" in res
    assert len(responses.inserts) == 1
    assert responses.find_one_queries == []  # guard skipped without booking_id
