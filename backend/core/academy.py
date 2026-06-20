"""Syroce Academy — training engine.

The GLOBAL default curriculum (courses, lessons, question bank WITH correct
answers) is system-owned and lives as content files under
`backend/academy_content/` (`_catalog.json` + lesson `.md`), mirroring the
`help_content` pattern. Because curriculum is never written into per-tenant
collections, enabling/seeding Academy can never mutate pilot tenant data
(pilot_drift = 0).

Per-user state lives in tenant-scoped collections:
  - academy_progress      (tenant_id, user_id, course_id)
  - academy_attempts      (tenant_id, user_id, course_id)
  - academy_certificates  (tenant_id, user_id, course_id)

Security invariants:
  - Correct answers (`answer_index`) live ONLY in `_catalog.json` and are NEVER
    included in any payload returned to the client.
  - Exam scoring is performed server-side only; a client-supplied score or
    pass flag is never trusted.
  - Every query and write is explicitly scoped by tenant_id + user_id.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

CONTENT_DIR = Path(__file__).parent.parent / "academy_content"
CATALOG_PATH = CONTENT_DIR / "_catalog.json"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,80}$")

# Roles that may view/take every course regardless of the course role list.
_ALL_ACCESS_ROLES = {"admin", "super_admin"}
# Roles allowed to read the management completion report.
MANAGER_ROLES = {"admin", "super_admin", "supervisor", "gm", "manager", "owner"}
# Roles allowed to AUTHOR (create/edit/delete) tenant-custom courses and to
# toggle built-in course visibility. ``supervisor`` may READ the report but is
# intentionally NOT an author.
ACADEMY_AUTHOR_ROLES = {"admin", "super_admin", "gm", "manager", "owner"}
# Whitelist of role audiences a course may target. Broader than ``UserRole``
# because tenants use additional role strings (gm/manager/owner/night_audit/
# revenue) that also appear in the system catalog. Guest/agency audiences are
# intentionally excluded — Academy is staff training.
ACADEMY_COURSE_ROLES = {
    "super_admin", "admin", "supervisor", "front_desk", "housekeeping",
    "sales", "finance", "procurement", "staff", "gm", "manager", "owner",
    "night_audit", "revenue",
}
# Tenant-custom course ids are namespaced so they can NEVER collide with or
# shadow a system catalog id (which must never start with this prefix).
CUSTOM_ID_PREFIX = "custom-"


def is_custom_course_id(course_id: Any) -> bool:
    return isinstance(course_id, str) and course_id.startswith(CUSTOM_ID_PREFIX)


def _norm_role(role: Any) -> str:
    return getattr(role, "value", str(role))


@lru_cache(maxsize=1)
def _load_catalog_cached(_mtime: float) -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {"version": 0, "courses": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_catalog() -> dict[str, Any]:
    """Load the GLOBAL default curriculum, cache-busted by file mtime."""
    try:
        mtime = CATALOG_PATH.stat().st_mtime
    except OSError:
        mtime = 0.0
    return _load_catalog_cached(mtime)


def _all_courses() -> list[dict[str, Any]]:
    return load_catalog().get("courses", [])


def get_course_raw(course_id: str) -> dict[str, Any] | None:
    """Return the raw course dict INCLUDING answers (server-side use only)."""
    return next((c for c in _all_courses() if c.get("id") == course_id), None)


def course_visible_to_role(course: dict[str, Any], role: str) -> bool:
    if role in _ALL_ACCESS_ROLES:
        return True
    return role in (course.get("roles") or [])


def read_lesson_body(slug: str) -> str:
    if not _SLUG_RE.match(slug):
        raise ValueError("Gecersiz ders kimligi")
    p = CONTENT_DIR / f"{slug}.md"
    try:
        p.resolve().relative_to(CONTENT_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Gecersiz ders kimligi") from exc
    if not p.exists():
        raise FileNotFoundError(slug)
    return p.read_text(encoding="utf-8")


def public_course_summary(course: dict[str, Any]) -> dict[str, Any]:
    """Course card view — no lessons body, no questions/answers."""
    return {
        "id": course.get("id"),
        "source": course.get("source") or "system",
        "title": course.get("title"),
        "department": course.get("department"),
        "department_label": course.get("department_label"),
        "summary": course.get("summary"),
        "draft": bool(course.get("draft", False)),
        "pass_threshold": course.get("pass_threshold", 70),
        "estimated_minutes": course.get("estimated_minutes"),
        "lesson_count": len(course.get("lessons") or []),
        "question_count": len(course.get("questions") or []),
        # True when a built-in (system) course carries a per-tenant content
        # override; always False for catalog defaults and tenant-custom courses.
        "customized": bool(course.get("customized", False)),
    }


def public_course_detail(course: dict[str, Any]) -> dict[str, Any]:
    """Course detail with lesson metadata + bodies. NEVER includes answers.

    System lessons load their body from a content `.md` file (path-guarded by
    ``read_lesson_body``); tenant-custom lessons carry an inline body_markdown
    and NEVER touch the filesystem.
    """
    is_custom = (
        course.get("_inline_bodies")
        or course.get("source") == "tenant"
        or is_custom_course_id(course.get("id"))
    )
    lessons = []
    for lesson in course.get("lessons") or []:
        if is_custom:
            slug = ""
            body = lesson.get("body_markdown") or ""
        else:
            slug = lesson.get("slug", "")
            try:
                body = read_lesson_body(slug)
            except (ValueError, FileNotFoundError):
                body = ""
        lessons.append({
            "id": lesson.get("id"),
            "title": lesson.get("title"),
            "slug": slug,
            "body_markdown": body,
        })
    detail = public_course_summary(course)
    detail["lessons"] = lessons
    return detail


def public_exam(course: dict[str, Any]) -> dict[str, Any]:
    """Exam payload for the client — options ONLY, answer_index stripped."""
    questions = []
    for q in course.get("questions") or []:
        questions.append({
            "id": q.get("id"),
            "prompt": q.get("prompt"),
            "options": list(q.get("options") or []),
        })
    return {
        "course_id": course.get("id"),
        "title": course.get("title"),
        "pass_threshold": course.get("pass_threshold", 70),
        "question_count": len(questions),
        "questions": questions,
    }


def score_exam(course: dict[str, Any], answers: dict[str, int]) -> dict[str, Any]:
    """Server-side scoring. `answers` maps question_id -> selected option index.

    The client never supplies a score or pass flag; both are computed here from
    the server-held answer key.
    """
    questions = course.get("questions") or []
    total = len(questions)
    correct = 0
    for q in questions:
        qid = q.get("id")
        try:
            selected = int(answers.get(qid)) if answers.get(qid) is not None else None
        except (TypeError, ValueError):
            selected = None
        if selected is not None and selected == q.get("answer_index"):
            correct += 1
    score = int(round((correct / total) * 100)) if total else 0
    threshold = int(course.get("pass_threshold", 70))
    return {
        "score": score,
        "correct": correct,
        "total": total,
        "passed": score >= threshold,
        "pass_threshold": threshold,
    }


# --------------------------------------------------------------------------- #
# Per-user state (tenant-scoped). All filters include tenant_id + user_id.    #
# --------------------------------------------------------------------------- #

def _db():
    from core.database import _raw_db
    return _raw_db


# --------------------------------------------------------------------------- #
# Tenant-custom courses + built-in visibility overrides (admin-authored).      #
#                                                                              #
# Custom courses live in the tenant-scoped `academy_courses` collection and    #
# carry their FULL content including `answer_index` + inline lesson            #
# `body_markdown`. They are merged with the system catalog at read time; the   #
# public_* projections still strip answers, so the student answer-secrecy      #
# guarantee is identical for system and custom courses. Built-in courses are   #
# never mutated per tenant — a tenant may only hide/show them through          #
# `academy_course_overrides` ({tenant_id, system_course_id, hidden}).          #
# --------------------------------------------------------------------------- #

def _with_source(course: dict[str, Any], source: str) -> dict[str, Any]:
    c = dict(course)
    c["source"] = source
    return c


async def _all_overrides(tenant_id: str) -> list[dict[str, Any]]:
    """All per-tenant built-in overrides (hidden flag and/or content)."""
    return await _db().academy_course_overrides.find(
        {"tenant_id": tenant_id}, {"_id": 0},
    ).to_list(1000)


async def _override_for(
    tenant_id: str, system_course_id: str,
) -> dict[str, Any] | None:
    return await _db().academy_course_overrides.find_one(
        {"tenant_id": tenant_id, "system_course_id": system_course_id},
        {"_id": 0},
    )


def _apply_system_override(
    base: dict[str, Any], content: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve a built-in course for a tenant, applying any per-tenant CONTENT
    override.

    With no override the catalog course (answers included, file-backed lesson
    bodies) is returned unchanged. An override is a FULL content replacement:
    the system ``id``/``source`` are ALWAYS server-set (never taken from the
    stored content), and the course switches to INLINE lesson bodies via the
    ``_inline_bodies`` marker. The catalog cache is never mutated — the replaced
    lists/values come from the override document, not the shared cache.
    """
    if not content:
        return _with_source(base, "system")
    merged = _with_source(base, "system")
    merged["title"] = content.get("title") or base.get("title")
    merged["department"] = content.get("department")
    merged["department_label"] = content.get("department_label")
    merged["summary"] = content.get("summary") or ""
    merged["roles"] = list(content.get("roles") or [])
    merged["pass_threshold"] = int(
        content.get("pass_threshold", base.get("pass_threshold", 70)),
    )
    merged["estimated_minutes"] = content.get("estimated_minutes")
    merged["lessons"] = [dict(l) for l in content.get("lessons") or []]
    merged["questions"] = [dict(q) for q in content.get("questions") or []]
    merged["customized"] = True
    merged["_inline_bodies"] = True
    return merged


def _safe_lesson_body(slug: str) -> str:
    try:
        return read_lesson_body(slug or "")
    except (ValueError, FileNotFoundError):
        return ""


async def _custom_courses(tenant_id: str) -> list[dict[str, Any]]:
    rows = await _db().academy_courses.find(
        {"tenant_id": tenant_id}, {"_id": 0},
    ).to_list(1000)
    return [_with_source(r, "tenant") for r in rows]


async def resolve_course(
    tenant_id: str, course_id: str, *,
    include_hidden: bool = False, include_draft: bool = False,
) -> dict[str, Any] | None:
    """Resolve a single course (system or tenant-custom) for ``tenant_id``.

    Returns the RAW course dict (answers included — server-side use only) or
    ``None``. A hidden system course (or a draft custom course) resolves to
    ``None`` on the student path unless the matching include flag is set
    (manager/report use). System course drafts are NOT filtered here — that
    matches the prior student behavior.
    """
    if is_custom_course_id(course_id):
        row = await _db().academy_courses.find_one(
            {"tenant_id": tenant_id, "id": course_id}, {"_id": 0},
        )
        if not row:
            return None
        if row.get("draft") and not include_draft:
            return None
        return _with_source(row, "tenant")
    course = get_course_raw(course_id)
    if not course:
        return None
    ov = await _override_for(tenant_id, course_id)
    if ov and ov.get("hidden") and not include_hidden:
        return None
    return _apply_system_override(course, (ov or {}).get("content"))


async def list_courses_for(
    tenant_id: str, role: str, *,
    include_hidden: bool = False, include_draft: bool = False,
) -> list[dict[str, Any]]:
    """Merged, role-filtered course list (system + tenant-custom) as raw dicts.

    System courses respect per-tenant hide overrides; custom drafts are excluded
    from the student view. Role visibility is applied here so callers can
    project the result directly.
    """
    overrides = {r["system_course_id"]: r for r in await _all_overrides(tenant_id)}
    out: list[dict[str, Any]] = []
    for c in _all_courses():
        ov = overrides.get(c.get("id"))
        if ov and ov.get("hidden") and not include_hidden:
            continue
        # Apply the content override BEFORE the role check: an override can
        # change a course's role visibility.
        merged = _apply_system_override(c, ov.get("content") if ov else None)
        if not course_visible_to_role(merged, role):
            continue
        out.append(merged)
    for c in await _custom_courses(tenant_id):
        if c.get("draft") and not include_draft:
            continue
        if not course_visible_to_role(c, role):
            continue
        out.append(c)
    return out


# --- Author (manager) CRUD over tenant-custom courses ---------------------- #

def _normalize_course_content(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce a validated author payload into the stored content shape.

    Lessons/questions keep any existing id (so in-flight learner progress, keyed
    by lesson id, survives an edit) and otherwise get a fresh namespaced id.
    Input is assumed already validated by the router's Pydantic models.
    """
    lessons = []
    for l in data.get("lessons") or []:
        lid = (str(l.get("id") or "").strip()) or ("l-" + uuid.uuid4().hex[:10])
        lessons.append({
            "id": lid,
            "title": l.get("title") or "",
            "body_markdown": l.get("body_markdown") or "",
        })
    questions = []
    for q in data.get("questions") or []:
        qid = (str(q.get("id") or "").strip()) or ("q-" + uuid.uuid4().hex[:10])
        questions.append({
            "id": qid,
            "prompt": q.get("prompt") or "",
            "options": [str(o) for o in (q.get("options") or [])],
            "answer_index": int(q.get("answer_index", 0)),
        })
    return {
        "title": data.get("title") or "",
        "department": data.get("department") or None,
        "department_label": data.get("department_label") or None,
        "summary": data.get("summary") or "",
        "roles": list(data.get("roles") or []),
        "draft": bool(data.get("draft", True)),
        "pass_threshold": int(data.get("pass_threshold", 70)),
        "estimated_minutes": data.get("estimated_minutes"),
        "lessons": lessons,
        "questions": questions,
    }


async def list_author_courses(tenant_id: str) -> list[dict[str, Any]]:
    """All tenant-custom courses (raw, answers included) for the admin view."""
    rows = await _db().academy_courses.find(
        {"tenant_id": tenant_id}, {"_id": 0},
    ).sort("updated_at", -1).to_list(1000)
    return [_with_source(r, "tenant") for r in rows]


async def get_author_course(tenant_id: str, course_id: str) -> dict[str, Any] | None:
    """A single tenant-custom course (raw, answers included) or ``None``."""
    if not is_custom_course_id(course_id):
        return None
    row = await _db().academy_courses.find_one(
        {"tenant_id": tenant_id, "id": course_id}, {"_id": 0},
    )
    return _with_source(row, "tenant") if row else None


async def create_author_course(
    tenant_id: str, author_id: str | None, data: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    content = _normalize_course_content(data)
    doc = {
        "id": CUSTOM_ID_PREFIX + uuid.uuid4().hex[:12],
        "tenant_id": tenant_id,
        "source": "tenant",
        **content,
        "created_by": author_id,
        "updated_by": author_id,
        "created_at": now,
        "updated_at": now,
    }
    await _db().academy_courses.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_author_course(
    tenant_id: str, author_id: str | None, course_id: str, data: dict[str, Any],
) -> dict[str, Any] | None:
    if not is_custom_course_id(course_id):
        return None
    now = datetime.now(UTC)
    content = _normalize_course_content(data)
    res = await _db().academy_courses.update_one(
        {"tenant_id": tenant_id, "id": course_id},
        {"$set": {**content, "updated_by": author_id, "updated_at": now}},
    )
    if getattr(res, "matched_count", 0) == 0:
        return None
    return await get_author_course(tenant_id, course_id)


async def delete_author_course(tenant_id: str, course_id: str) -> bool:
    """HARD delete a tenant-custom course. Earned certificates denormalize the
    course title so they remain valid; orphaned progress rows simply stop
    resolving in the report (already skipped for unknown courses)."""
    if not is_custom_course_id(course_id):
        return False
    res = await _db().academy_courses.delete_one(
        {"tenant_id": tenant_id, "id": course_id},
    )
    return getattr(res, "deleted_count", 0) > 0


# --- Built-in (system) course per-tenant visibility ------------------------ #

async def set_system_course_hidden(
    tenant_id: str, system_course_id: str, hidden: bool,
) -> bool:
    """Toggle per-tenant visibility of a BUILT-IN course. Returns ``False`` if
    the id is not a known system course (custom ids are rejected here)."""
    if is_custom_course_id(system_course_id) or get_course_raw(system_course_id) is None:
        return False
    now = datetime.now(UTC)
    await _db().academy_course_overrides.update_one(
        {"tenant_id": tenant_id, "system_course_id": system_course_id},
        {
            "$set": {"hidden": bool(hidden), "updated_at": now},
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "system_course_id": system_course_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return True


async def list_system_courses_for(tenant_id: str) -> list[dict[str, Any]]:
    """Built-in course summaries + current hidden flag, for the admin
    visibility panel. No answers."""
    overrides = {r["system_course_id"]: r for r in await _all_overrides(tenant_id)}
    out = []
    for c in _all_courses():
        ov = overrides.get(c.get("id"), {})
        merged = _apply_system_override(c, ov.get("content"))
        summary = public_course_summary(merged)
        summary["hidden"] = bool(ov.get("hidden"))
        out.append(summary)
    return out


async def get_system_course_for_edit(
    tenant_id: str, system_course_id: str,
) -> dict[str, Any] | None:
    """Full editable view of a BUILT-IN course for an author (answers included).

    Returns the per-tenant content override if one exists; otherwise the default
    catalog content with each lesson body resolved from its file into an inline
    ``body_markdown`` so the editor can edit it. Lesson/question ids are kept so
    a saved edit round-trips them (in-flight learner progress survives). Returns
    ``None`` for custom or unknown ids. AUTHOR-ONLY surface — never project to a
    student-facing route (the answer key is present).
    """
    if is_custom_course_id(system_course_id):
        return None
    base = get_course_raw(system_course_id)
    if not base:
        return None
    ov = await _override_for(tenant_id, system_course_id)
    content = (ov or {}).get("content")
    if content:
        return _apply_system_override(base, content)
    course = _with_source(base, "system")
    course["lessons"] = [
        {
            "id": l.get("id"),
            "title": l.get("title"),
            "body_markdown": _safe_lesson_body(l.get("slug", "")),
        }
        for l in base.get("lessons") or []
    ]
    course["questions"] = [dict(q) for q in base.get("questions") or []]
    course["customized"] = False
    course["_inline_bodies"] = True
    return course


async def set_system_course_content(
    tenant_id: str, author_id: str | None,
    system_course_id: str, data: dict[str, Any],
) -> dict[str, Any] | None:
    """Store a per-tenant CONTENT override for a built-in course (lessons + exam).

    The catalog file is NEVER touched. The visibility (``hidden``) flag in the
    same override document is preserved. Returns the resolved editable course, or
    ``None`` if the id is not a known built-in course.
    """
    if is_custom_course_id(system_course_id) or get_course_raw(system_course_id) is None:
        return None
    now = datetime.now(UTC)
    content = _normalize_course_content(data)
    content.pop("draft", None)  # built-in overrides are always live.
    await _db().academy_course_overrides.update_one(
        {"tenant_id": tenant_id, "system_course_id": system_course_id},
        {
            "$set": {
                "content": content,
                "content_updated_by": author_id,
                "content_updated_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "system_course_id": system_course_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return await get_system_course_for_edit(tenant_id, system_course_id)


async def reset_system_course(tenant_id: str, system_course_id: str) -> bool:
    """Remove a per-tenant CONTENT override, reverting to the catalog default.

    Any visibility (``hidden``) state on the same document is kept. Idempotent:
    resetting an un-customized (or never-overridden) course is a no-op that still
    returns ``True``; only an unknown/custom id returns ``False``.
    """
    if is_custom_course_id(system_course_id) or get_course_raw(system_course_id) is None:
        return False
    await _db().academy_course_overrides.update_one(
        {"tenant_id": tenant_id, "system_course_id": system_course_id},
        {
            "$unset": {
                "content": "",
                "content_updated_by": "",
                "content_updated_at": "",
            },
            "$set": {"updated_at": datetime.now(UTC)},
        },
    )
    return True


def _compute_status(progress: dict[str, Any] | None, lesson_count: int) -> str:
    if not progress:
        return "not_started"
    if progress.get("passed"):
        return "passed"
    if progress.get("attempts", 0) > 0:
        return "failed"
    if progress.get("completed_lessons"):
        return "in_progress"
    return "not_started"


async def get_progress(tenant_id: str, user_id: str, course_id: str) -> dict[str, Any] | None:
    return await _db().academy_progress.find_one(
        {"tenant_id": tenant_id, "user_id": user_id, "course_id": course_id},
        {"_id": 0},
    )


async def get_all_progress(tenant_id: str, user_id: str) -> dict[str, dict[str, Any]]:
    rows = await _db().academy_progress.find(
        {"tenant_id": tenant_id, "user_id": user_id}, {"_id": 0},
    ).to_list(500)
    return {r["course_id"]: r for r in rows}


async def mark_lesson_complete(
    tenant_id: str, user_id: str, course: dict[str, Any], lesson_id: str,
) -> dict[str, Any]:
    valid_ids = {l.get("id") for l in (course.get("lessons") or [])}
    if lesson_id not in valid_ids:
        raise ValueError("Ders bulunamadi")
    now = datetime.now(UTC)
    await _db().academy_progress.update_one(
        {"tenant_id": tenant_id, "user_id": user_id, "course_id": course["id"]},
        {
            "$addToSet": {"completed_lessons": lesson_id},
            "$set": {"updated_at": now},
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "course_id": course["id"],
                "passed": False,
                "best_score": 0,
                "attempts": 0,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return await get_progress(tenant_id, user_id, course["id"]) or {}


async def record_attempt(
    tenant_id: str,
    user_id: str,
    user_name: str,
    course: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Persist an exam attempt, update best score, and issue a certificate on
    first pass. Returns {result, certificate?}."""
    now = datetime.now(UTC)
    course_id = course["id"]
    attempt = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "course_id": course_id,
        "score": result["score"],
        "correct": result["correct"],
        "total": result["total"],
        "passed": result["passed"],
        "created_at": now,
    }
    await _db().academy_attempts.insert_one(dict(attempt))

    existing = await get_progress(tenant_id, user_id, course_id)
    best = max(result["score"], (existing or {}).get("best_score", 0))
    already_passed = bool((existing or {}).get("passed"))
    passed_now = already_passed or result["passed"]
    await _db().academy_progress.update_one(
        {"tenant_id": tenant_id, "user_id": user_id, "course_id": course_id},
        {
            "$set": {
                "best_score": best,
                "passed": passed_now,
                "last_score": result["score"],
                "updated_at": now,
            },
            "$inc": {"attempts": 1},
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "course_id": course_id,
                "completed_lessons": [],
                "created_at": now,
            },
        },
        upsert=True,
    )

    certificate = None
    if result["passed"]:
        certificate = await _issue_certificate(
            tenant_id, user_id, user_name, course, result["score"],
        )
    return {"result": result, "certificate": certificate}


async def _issue_certificate(
    tenant_id: str, user_id: str, user_name: str,
    course: dict[str, Any], score: int,
) -> dict[str, Any]:
    """Idempotent per (tenant, user, course). System-issued only — never on
    direct client demand. Returns the certificate record (no _id)."""
    db = _db()
    existing = await db.academy_certificates.find_one(
        {"tenant_id": tenant_id, "user_id": user_id, "course_id": course["id"]},
        {"_id": 0},
    )
    if existing:
        return existing
    now = datetime.now(UTC)
    cert = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "course_id": course["id"],
        "course_title": course.get("title"),
        "department_label": course.get("department_label"),
        "user_name": user_name,
        "score": score,
        "verification_code": _make_verification_code(),
        "issued_at": now,
    }
    try:
        await db.academy_certificates.insert_one(dict(cert))
    except Exception:
        # Concurrent issuance — return the row that won the race.
        won = await db.academy_certificates.find_one(
            {"tenant_id": tenant_id, "user_id": user_id, "course_id": course["id"]},
            {"_id": 0},
        )
        if won:
            return won
        raise
    return cert


def _make_verification_code() -> str:
    return "SYR-ACAD-" + uuid.uuid4().hex[:10].upper()


# Verification codes are globally-unique, opaque capability tokens
# (`SYR-ACAD-` + 10 uppercase hex chars). They are printed on the PDF and act
# as the bearer secret for the public verification surface.
VERIFICATION_CODE_RE = re.compile(r"^SYR-ACAD-[0-9A-F]{10}$")


def _mask_name(name: Any) -> str | None:
    """'John Doe' -> 'J*** D***' (recipient privacy on the public surface)."""
    if not name:
        return None
    parts = [p for p in str(name).strip().split() if p]
    if not parts:
        return None
    return " ".join(p[0] + "***" for p in parts)


async def get_certificate_by_code(code: str) -> dict[str, Any] | None:
    """Cross-tenant lookup of a certificate by its globally-unique verification
    code. The code itself is the bearer capability — no tenant context exists on
    the public verification path, so this reads the raw db with an explicit,
    exact-match filter (no enumeration: the code is opaque + format-validated).
    """
    if not code or not VERIFICATION_CODE_RE.match(code):
        return None
    return await _db().academy_certificates.find_one(
        {"verification_code": code}, {"_id": 0},
    )


def public_certificate_view(cert: dict[str, Any]) -> dict[str, Any]:
    """Minimal, PII-minimized public verification view of a certificate.

    Returns only what a third party (audit, HR) needs to confirm authenticity:
    course, department, issue date, validity, and a MASKED recipient name. No
    user_id, tenant_id, score, e-mail, or other identifiers are exposed.
    """
    issued = cert.get("issued_at")
    if isinstance(issued, datetime):
        issued_str = issued.date().isoformat()
    else:
        issued_str = str(issued or "")[:10]
    return {
        "valid": True,
        "verification_code": cert.get("verification_code"),
        "course_title": cert.get("course_title"),
        "department_label": cert.get("department_label"),
        "issued_at": issued_str,
        "recipient_name": _mask_name(cert.get("user_name")),
    }


async def get_certificates(tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    return await _db().academy_certificates.find(
        {"tenant_id": tenant_id, "user_id": user_id}, {"_id": 0},
    ).sort("issued_at", -1).to_list(200)


async def get_certificate(tenant_id: str, user_id: str, cert_id: str) -> dict[str, Any] | None:
    return await _db().academy_certificates.find_one(
        {"tenant_id": tenant_id, "user_id": user_id, "id": cert_id}, {"_id": 0},
    )


async def get_tenant_report(tenant_id: str) -> dict[str, Any]:
    """Manager report: per-department / per-user completion, pass/fail, scores.

    Strictly tenant-scoped. Reads users + per-user academy state for this tenant
    only; curriculum metadata comes from the GLOBAL catalog.
    """
    db = _db()
    overrides = {r["system_course_id"]: r for r in await _all_overrides(tenant_id)}
    course_by_id: dict[str, dict[str, Any]] = {
        c["id"]: _apply_system_override(c, overrides.get(c["id"], {}).get("content"))
        for c in _all_courses()
    }
    # Tenant-custom courses provide metadata for their own progress rows; a
    # hard-deleted custom course simply won't resolve (its rows are skipped).
    for c in await _custom_courses(tenant_id):
        course_by_id[c["id"]] = c

    progress_rows = await db.academy_progress.find(
        {"tenant_id": tenant_id}, {"_id": 0},
    ).to_list(5000)
    cert_rows = await db.academy_certificates.find(
        {"tenant_id": tenant_id}, {"_id": 0},
    ).to_list(5000)
    cert_set = {(c["user_id"], c["course_id"]) for c in cert_rows}

    # Resolve user display info (tenant-scoped).
    user_ids = {p["user_id"] for p in progress_rows}
    users: dict[str, dict[str, Any]] = {}
    if user_ids:
        async for u in db.users.find(
            {"tenant_id": tenant_id, "id": {"$in": list(user_ids)}},
            {"_id": 0, "id": 1, "name": 1, "role": 1},
        ):
            users[u["id"]] = u

    rows: list[dict[str, Any]] = []
    for p in progress_rows:
        course = course_by_id.get(p["course_id"])
        if not course:
            continue
        u = users.get(p["user_id"], {})
        lesson_count = len(course.get("lessons") or [])
        completed = len(p.get("completed_lessons") or [])
        rows.append({
            "user_id": p["user_id"],
            "user_name": u.get("name") or "—",
            "role": _norm_role(u.get("role")) if u.get("role") else None,
            "department_label": course.get("department_label"),
            "course_id": p["course_id"],
            "course_title": course.get("title"),
            "lessons_completed": completed,
            "lesson_count": lesson_count,
            "status": _compute_status(p, lesson_count),
            "best_score": p.get("best_score", 0),
            "passed": bool(p.get("passed")),
            "attempts": p.get("attempts", 0),
            "has_certificate": (p["user_id"], p["course_id"]) in cert_set,
        })

    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    summary = {
        "enrollments": total,
        "passed": passed,
        "failed": sum(1 for r in rows if r["status"] == "failed"),
        "in_progress": sum(1 for r in rows if r["status"] == "in_progress"),
        "certificates": len(cert_rows),
        "pass_rate": int(round((passed / total) * 100)) if total else 0,
    }

    # Per-department rollup.
    dept: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = r["department_label"] or "—"
        bucket = dept.setdefault(d, {"department_label": d, "enrollments": 0, "passed": 0})
        bucket["enrollments"] += 1
        if r["passed"]:
            bucket["passed"] += 1

    return {
        "summary": summary,
        "departments": list(dept.values()),
        "rows": rows,
    }


def render_certificate_pdf(cert: dict[str, Any]) -> bytes:
    """Render a certificate record to a PDF via WeasyPrint.

    Import-time native-lib failures surface as a caller-handled error so the
    route can return 503 (operator-actionable) instead of a 500 that pages
    Sentry.
    """
    from weasyprint import HTML  # noqa: PLC0415  (lazy: native libs at import)

    issued = cert.get("issued_at")
    if isinstance(issued, datetime):
        issued_str = issued.strftime("%d.%m.%Y")
    else:
        issued_str = str(issued or "")[:10]
    html = _certificate_html(cert, issued_str)
    return HTML(string=html).write_pdf()


def _esc(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _verification_base_url() -> str:
    """Public frontend base for the certificate verification surface."""
    import os
    candidates = [
        os.environ.get("FRONTEND_URL"),
        os.environ.get("PUBLIC_APP_URL"),
        os.environ.get("REPLIT_DEV_DOMAIN") and f"https://{os.environ['REPLIT_DEV_DOMAIN']}",
    ]
    return next((c for c in candidates if c), "").rstrip("/")


def _certificate_html(cert: dict[str, Any], issued_str: str) -> str:
    code = cert.get("verification_code") or ""
    base = _verification_base_url()
    qr_data_uri = ""
    if base:
        verify_url = f"{base}/sertifika-dogrula/{code}"
        verify_line = f"Dogrula: {_esc(verify_url)}"
        try:
            from core.security import generate_qr_code
            qr_data_uri = generate_qr_code(verify_url)
        except Exception:
            qr_data_uri = ""
    else:
        verify_line = f"Dogrulama Kodu: {_esc(code)}"
    return _certificate_html_impl(cert, issued_str, verify_line, qr_data_uri)


def _certificate_html_impl(
    cert: dict[str, Any],
    issued_str: str,
    verify_line: str,
    qr_data_uri: str = "",
) -> str:
    qr_block = (
        f'<img class="qr" src="{qr_data_uri}" alt="QR" />' if qr_data_uri else ""
    )
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8" />
<style>
  @page {{ size: A4 landscape; margin: 18mm; }}
  body {{ font-family: "Helvetica Neue", Arial, sans-serif; color: #0f172a; }}
  .frame {{ border: 3px solid #0f172a; padding: 28mm 24mm; text-align: center; height: 100%; }}
  .brand {{ font-size: 14px; letter-spacing: 3px; text-transform: uppercase; color: #475569; }}
  h1 {{ font-size: 34px; margin: 18px 0 4px; }}
  .sub {{ font-size: 15px; color: #475569; margin-bottom: 26px; }}
  .name {{ font-size: 30px; font-weight: 700; margin: 8px 0; }}
  .course {{ font-size: 20px; margin: 10px 0; }}
  .meta {{ margin-top: 26px; font-size: 14px; color: #334155; }}
  .meta span {{ display: inline-block; margin: 0 14px; }}
  .code {{ margin-top: 22px; font-size: 12px; letter-spacing: 1px; color: #64748b; }}
  .qr {{ margin-top: 18px; width: 30mm; height: 30mm; }}
</style>
</head>
<body>
  <div class="frame">
    <div class="brand">Syroce Academy</div>
    <h1>Basari Sertifikasi</h1>
    <div class="sub">Bu belge asagidaki egitimin basariyla tamamlandigini onaylar.</div>
    <div class="name">{_esc(cert.get('user_name'))}</div>
    <div class="course">{_esc(cert.get('course_title'))}</div>
    <div class="sub">Departman: {_esc(cert.get('department_label'))}</div>
    <div class="meta">
      <span>Puan: <strong>{_esc(cert.get('score'))}</strong></span>
      <span>Tarih: <strong>{_esc(issued_str)}</strong></span>
    </div>
    {qr_block}
    <div class="code">{verify_line}</div>
  </div>
</body>
</html>"""
