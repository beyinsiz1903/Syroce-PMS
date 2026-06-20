"""Task #628 — Syroce Academy server-scoring & answer-secrecy security tests.

These cases lock down the engine/route security invariants documented in
``backend/core/academy.py`` and ``backend/routers/academy.py`` so a regression
is caught before it ships:

  1. ``GET /api/academy/courses/{id}/exam`` NEVER leaks ``answer_index``.
  2. The submit endpoint ignores any client-supplied ``score``/``passed`` and
     recomputes both server-side from the server-held answer key.
  3. Tenant isolation — one tenant cannot read another tenant's progress or
     certificates; the manager report is strictly tenant-scoped.
  4. The manager report carries a role guard (non-manager → 403).
  5. Concurrent exam submission keeps certificate issuance idempotent (the
     unique-index race resolves to the single winning row).

This is a router/engine unit test against in-memory fake Mongo collections —
it does not require a running backend or live DB, matching the
``test_procurement_credit_limit.py`` / ``test_inventory_transfer_unit_guard.py``
patterns.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from core import academy
from routers.academy import router as academy_router

COURSE_ID = "reception-temelleri"
# Server-held answer key for COURSE_ID (mirrors academy_content/_catalog.json).
CORRECT = {"q1": 1, "q2": 1, "q3": 2, "q4": 1, "q5": 2}
WRONG = {"q1": 0, "q2": 0, "q3": 0, "q4": 0, "q5": 0}


# ── In-memory fake Mongo ──────────────────────────────────────────────


def _matches(doc: dict, query: dict) -> bool:
    for key, val in query.items():
        if isinstance(val, dict) and "$in" in val:
            if doc.get(key) not in val["$in"]:
                return False
        elif doc.get(key) != val:
            return False
    return True


def _apply_update(doc: dict, update: dict, *, include_set_on_insert: bool) -> None:
    for key, val in update.get("$set", {}).items():
        doc[key] = val
    for key, val in update.get("$inc", {}).items():
        doc[key] = doc.get(key, 0) + val
    for key, val in update.get("$addToSet", {}).items():
        arr = doc.setdefault(key, [])
        if val not in arr:
            arr.append(val)
    if include_set_on_insert:
        for key, val in update.get("$setOnInsert", {}).items():
            doc.setdefault(key, val)


class _Cursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def sort(self, key, direction):
        self._rows.sort(key=lambda d: d.get(key), reverse=direction < 0)
        return self

    async def to_list(self, n):
        return [dict(r) for r in self._rows[:n]]

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    """Minimal async Mongo collection honouring tenant/user filters.

    ``unique_keys`` enforces a unique index so the certificate race test
    exercises the real DuplicateKeyError resolution path. ``yield_on_io``
    inserts an ``await asyncio.sleep(0)`` so two coroutines interleave their
    find_one/insert_one calls under ``asyncio.gather`` (simulating a true
    double-submit race).
    """

    def __init__(self, *, unique_keys: tuple[str, ...] | None = None,
                 yield_on_io: bool = False):
        self.docs: list[dict] = []
        self.unique_keys = unique_keys
        self.yield_on_io = yield_on_io

    async def find_one(self, query, projection=None):
        if self.yield_on_io:
            await asyncio.sleep(0)
        for d in self.docs:
            if _matches(d, query):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        return _Cursor([dict(d) for d in self.docs if _matches(d, query)])

    async def insert_one(self, doc):
        if self.yield_on_io:
            await asyncio.sleep(0)
        if self.unique_keys:
            key = tuple(doc.get(k) for k in self.unique_keys)
            for d in self.docs:
                if tuple(d.get(k) for k in self.unique_keys) == key:
                    raise DuplicateKeyError("duplicate key")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                _apply_update(d, update, include_set_on_insert=False)
                return SimpleNamespace(matched_count=1, modified_count=1,
                                       upserted_id=None)
        if upsert:
            newdoc: dict = {}
            for key, val in update.get("$setOnInsert", {}).items():
                newdoc[key] = val
            _apply_update(newdoc, update, include_set_on_insert=False)
            self.docs.append(newdoc)
            return SimpleNamespace(matched_count=0, modified_count=0,
                                   upserted_id=newdoc.get("id"))
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)


class FakeDB:
    def __init__(self, *, unique_certs: bool = False, yield_certs: bool = False):
        self.academy_progress = FakeCollection()
        self.academy_attempts = FakeCollection()
        self.academy_certificates = FakeCollection(
            unique_keys=("tenant_id", "user_id", "course_id") if unique_certs else None,
            yield_on_io=yield_certs,
        )
        self.users = FakeCollection()


# ── Fixtures / helpers ────────────────────────────────────────────────


def _user(*, uid="u1", tenant="t1", role="front_desk", name="Tester"):
    return SimpleNamespace(id=uid, tenant_id=tenant, role=role, name=name)


def _build_client(monkeypatch, fake_db, user):
    monkeypatch.setattr(academy, "_db", lambda: fake_db)

    from core.security import get_current_user

    app = FastAPI()
    app.include_router(academy_router)

    async def _fake_user():
        return user

    async def _noop():
        return None

    app.dependency_overrides[get_current_user] = _fake_user
    # Router-level require_module("academy") guard → no-op for the unit test.
    app.dependency_overrides[academy_router.dependencies[0].dependency] = _noop
    return TestClient(app)


# ── 1. Answer-secrecy: exam payload never carries answer_index ─────────


def test_exam_payload_strips_answer_index(monkeypatch):
    client = _build_client(monkeypatch, FakeDB(), _user())
    r = client.get(f"/api/academy/courses/{COURSE_ID}/exam")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["course_id"] == COURSE_ID
    assert body["question_count"] == 5
    assert body["questions"], "exam should expose questions"
    for q in body["questions"]:
        assert set(q.keys()) == {"id", "prompt", "options"}, q
        assert "answer_index" not in q
    # Defence in depth: the serialized payload must not mention the key at all.
    assert "answer_index" not in r.text


def test_public_exam_helper_omits_answers_even_with_answers_present():
    """Unit guard on the engine helper itself (independent of the route)."""
    course = academy.get_course_raw(COURSE_ID)
    assert course is not None
    # Sanity: the raw course really does hold the secret key.
    assert all("answer_index" in q for q in course["questions"])
    exam = academy.public_exam(course)
    for q in exam["questions"]:
        assert "answer_index" not in q


# ── 2. Server-side scoring: client score/passed are ignored ───────────


def test_submit_ignores_client_score_and_recomputes(monkeypatch):
    fake_db = FakeDB()
    client = _build_client(monkeypatch, fake_db, _user())
    # All-wrong answers, but the client lies about a perfect pass.
    r = client.post(
        f"/api/academy/courses/{COURSE_ID}/exam/submit",
        json={"answers": WRONG, "score": 100, "passed": True, "correct": 5},
    )
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["score"] == 0
    assert result["correct"] == 0
    assert result["passed"] is False
    # Persisted attempt reflects the server score, not the client's lie.
    assert len(fake_db.academy_attempts.docs) == 1
    assert fake_db.academy_attempts.docs[0]["score"] == 0
    assert fake_db.academy_attempts.docs[0]["passed"] is False
    # No certificate is issued for a failing attempt.
    assert fake_db.academy_certificates.docs == []


def test_submit_passes_and_issues_certificate_on_real_score(monkeypatch):
    fake_db = FakeDB()
    client = _build_client(monkeypatch, fake_db, _user())
    # Correct answers but the client lies the OTHER way (claims a fail).
    r = client.post(
        f"/api/academy/courses/{COURSE_ID}/exam/submit",
        json={"answers": CORRECT, "score": 0, "passed": False},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["result"]["score"] == 100
    assert payload["result"]["passed"] is True
    assert payload["certificate"] is not None
    assert payload["certificate"]["score"] == 100
    assert len(fake_db.academy_certificates.docs) == 1


# ── 3. Tenant isolation ───────────────────────────────────────────────


def test_certificates_are_tenant_scoped(monkeypatch):
    fake_db = FakeDB()
    # A certificate belonging to tenant t1.
    fake_db.academy_certificates.docs.append({
        "id": "cert-t1", "tenant_id": "t1", "user_id": "u1",
        "course_id": COURSE_ID, "issued_at": 1,
    })
    # Attacker authenticated for a DIFFERENT tenant, same user_id.
    client = _build_client(monkeypatch, fake_db, _user(tenant="t2"))
    r = client.get("/api/academy/certificates")
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []

    # The owning tenant DOES see it.
    client2 = _build_client(monkeypatch, fake_db, _user(tenant="t1"))
    r2 = client2.get("/api/academy/certificates")
    assert r2.status_code == 200, r2.text
    assert [c["id"] for c in r2.json()["items"]] == ["cert-t1"]


def test_certificate_pdf_cross_tenant_is_404(monkeypatch):
    fake_db = FakeDB()
    fake_db.academy_certificates.docs.append({
        "id": "cert-t1", "tenant_id": "t1", "user_id": "u1",
        "course_id": COURSE_ID, "issued_at": 1, "verification_code": "X",
    })
    client = _build_client(monkeypatch, fake_db, _user(tenant="t2", role="admin"))
    r = client.get("/api/academy/certificates/cert-t1/pdf")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_tenant_report_excludes_other_tenants(monkeypatch):
    fake_db = FakeDB()
    monkeypatch.setattr(academy, "_db", lambda: fake_db)
    for tid, uid in (("t1", "u1"), ("t2", "u2")):
        fake_db.academy_progress.docs.append({
            "tenant_id": tid, "user_id": uid, "course_id": COURSE_ID,
            "passed": True, "best_score": 90, "attempts": 1,
            "completed_lessons": ["karsilama"],
        })
        fake_db.users.docs.append({
            "id": uid, "tenant_id": tid, "name": f"User {uid}", "role": "front_desk",
        })
    report = await academy.get_tenant_report("t1")
    assert report["summary"]["enrollments"] == 1
    assert [row["user_id"] for row in report["rows"]] == ["u1"]


# ── 4. Manager report role guard ──────────────────────────────────────


@pytest.mark.parametrize("role", ["front_desk", "housekeeping", "waiter"])
def test_admin_report_denies_non_manager_roles(monkeypatch, role):
    client = _build_client(monkeypatch, FakeDB(), _user(role=role))
    r = client.get("/api/academy/admin/report")
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("role", ["admin", "gm", "supervisor", "manager"])
def test_admin_report_allows_manager_roles(monkeypatch, role):
    client = _build_client(monkeypatch, FakeDB(), _user(role=role))
    r = client.get("/api/academy/admin/report")
    assert r.status_code == 200, r.text
    assert "summary" in r.json()


# ── 5. Concurrent submission → idempotent certificate (unique index) ──


@pytest.mark.asyncio
async def test_concurrent_certificate_issuance_is_idempotent(monkeypatch):
    """Two simultaneous passing submits must yield exactly ONE certificate.

    ``yield_certs`` forces both coroutines to read (find_one → None) before
    either inserts, so the second insert hits the unique index and raises
    DuplicateKeyError; the engine must resolve that to the winning row.
    """
    fake_db = FakeDB(unique_certs=True, yield_certs=True)
    monkeypatch.setattr(academy, "_db", lambda: fake_db)
    course = academy.get_course_raw(COURSE_ID)

    cert_a, cert_b = await asyncio.gather(
        academy._issue_certificate("t1", "u1", "User", course, 100),
        academy._issue_certificate("t1", "u1", "User", course, 100),
    )
    # Exactly one persisted row, both callers see the same certificate.
    assert len(fake_db.academy_certificates.docs) == 1
    assert cert_a["id"] == cert_b["id"]
    assert cert_a["id"] == fake_db.academy_certificates.docs[0]["id"]


@pytest.mark.asyncio
async def test_certificate_issuance_is_idempotent_on_repeat(monkeypatch):
    """A re-pass (or replay) returns the original certificate, never a new one."""
    fake_db = FakeDB(unique_certs=True)
    monkeypatch.setattr(academy, "_db", lambda: fake_db)
    course = academy.get_course_raw(COURSE_ID)

    first = await academy._issue_certificate("t1", "u1", "User", course, 80)
    second = await academy._issue_certificate("t1", "u1", "User", course, 95)
    assert first["id"] == second["id"]
    # Original score is preserved — a later pass does not overwrite it.
    assert second["score"] == 80
    assert len(fake_db.academy_certificates.docs) == 1


# ── 6. score_exam edge cases: invalid / missing answers + boundaries ───
#
# ``score_exam`` is a pure server-side function that coerces each supplied
# answer to ``int`` and silently treats anything it cannot use (None, missing
# key, non-numeric string, type errors) as "unanswered" → counted wrong. These
# defensive behaviours were previously untested, so a regression (e.g. a
# missing answer accidentally scoring as correct) could ship silently. The
# tests below build synthetic courses so the answer key and threshold are fully
# controlled — the real 5-question course cannot land on an exact 70 boundary.


def _synthetic_course(answer_key: dict[str, int], *, threshold: int = 70,
                      course_id: str = "syn-course") -> dict:
    """Build a minimal course dict for ``score_exam`` unit tests.

    ``answer_key`` maps question_id -> the correct option index. Every question
    is given four options so any 0..3 index is a valid (but possibly wrong)
    selection.
    """
    return {
        "id": course_id,
        "title": "Synthetic",
        "pass_threshold": threshold,
        "questions": [
            {"id": qid, "prompt": f"Soru {qid}",
             "options": ["a", "b", "c", "d"], "answer_index": idx}
            for qid, idx in answer_key.items()
        ],
    }


def test_score_exam_missing_and_null_answers_count_wrong():
    """A missing key or an explicit ``None`` answer is treated as unanswered."""
    course = _synthetic_course({"q1": 0, "q2": 1, "q3": 2, "q4": 3})
    # q1 correct, q2 omitted entirely, q3 explicitly None, q4 wrong index.
    result = academy.score_exam(course, {"q1": 0, "q3": None, "q4": 0})
    assert result["total"] == 4
    assert result["correct"] == 1
    assert result["score"] == 25
    assert result["passed"] is False


def test_score_exam_empty_answers_dict_scores_zero():
    course = _synthetic_course({"q1": 0, "q2": 1})
    result = academy.score_exam(course, {})
    assert result["correct"] == 0
    assert result["score"] == 0
    assert result["passed"] is False


def test_score_exam_numeric_string_answers_are_coerced():
    """A numeric string ("1") is coerced via ``int()`` and can score correct."""
    course = _synthetic_course({"q1": 1, "q2": 2})
    result = academy.score_exam(course, {"q1": "1", "q2": "2"})
    assert result["correct"] == 2
    assert result["score"] == 100
    assert result["passed"] is True


def test_score_exam_non_numeric_string_counts_wrong():
    """A non-numeric string raises ValueError internally → counted wrong."""
    course = _synthetic_course({"q1": 1, "q2": 2})
    result = academy.score_exam(course, {"q1": "abc", "q2": "1"})
    assert result["correct"] == 0
    assert result["score"] == 0
    assert result["passed"] is False


def test_score_exam_unhashable_type_answer_counts_wrong():
    """A non-coercible type (list) raises TypeError internally → counted wrong."""
    course = _synthetic_course({"q1": 1})
    result = academy.score_exam(course, {"q1": [1]})
    assert result["correct"] == 0
    assert result["score"] == 0


def test_score_exam_out_of_range_index_counts_wrong():
    """Indices outside the option range never match a correct answer_index."""
    course = _synthetic_course({"q1": 1, "q2": 2})
    result = academy.score_exam(course, {"q1": 99, "q2": -1})
    assert result["correct"] == 0
    assert result["score"] == 0
    assert result["passed"] is False


def test_score_exam_no_questions_returns_zero_and_not_passed():
    """A course with zero questions scores 0 and must NOT pass (total=0 guard)."""
    course = _synthetic_course({})  # default threshold 70
    result = academy.score_exam(course, {"q1": 0})
    assert result["total"] == 0
    assert result["correct"] == 0
    assert result["score"] == 0
    assert result["passed"] is False


def test_score_exam_exact_threshold_passes():
    """A score landing exactly on ``pass_threshold`` is a pass (>= comparison)."""
    key = {f"q{i}": (i % 4) for i in range(10)}
    course = _synthetic_course(key, threshold=70)
    items = list(key.items())
    answers = {qid: idx for qid, idx in items[:7]}              # 7 correct
    answers.update({qid: (idx + 1) % 4 for qid, idx in items[7:]})  # 3 wrong
    result = academy.score_exam(course, answers)
    assert result["correct"] == 7
    assert result["score"] == 70
    assert result["pass_threshold"] == 70
    assert result["passed"] is True


def test_score_exam_just_below_threshold_fails():
    """One mark below the threshold must fail, proving the boundary is tight."""
    key = {f"q{i}": (i % 4) for i in range(10)}
    course = _synthetic_course(key, threshold=70)
    items = list(key.items())
    answers = {qid: idx for qid, idx in items[:6]}              # 6 correct
    answers.update({qid: (idx + 1) % 4 for qid, idx in items[6:]})  # 4 wrong
    result = academy.score_exam(course, answers)
    assert result["correct"] == 6
    assert result["score"] == 60
    assert result["passed"] is False


def test_score_exam_string_pass_threshold_is_coerced():
    """A catalog ``pass_threshold`` stored as a string still compares correctly."""
    key = {f"q{i}": (i % 4) for i in range(10)}
    course = _synthetic_course(key, threshold=70)
    course["pass_threshold"] = "70"  # simulate a stringly-typed catalog value
    answers = {qid: idx for qid, idx in key.items()}  # all correct → 100
    result = academy.score_exam(course, answers)
    assert result["pass_threshold"] == 70
    assert result["passed"] is True
