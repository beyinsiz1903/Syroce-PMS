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
        "title": course.get("title"),
        "department": course.get("department"),
        "department_label": course.get("department_label"),
        "summary": course.get("summary"),
        "draft": bool(course.get("draft", False)),
        "pass_threshold": course.get("pass_threshold", 70),
        "estimated_minutes": course.get("estimated_minutes"),
        "lesson_count": len(course.get("lessons") or []),
        "question_count": len(course.get("questions") or []),
    }


def public_course_detail(course: dict[str, Any]) -> dict[str, Any]:
    """Course detail with lesson metadata + bodies. NEVER includes answers."""
    lessons = []
    for lesson in course.get("lessons") or []:
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
    courses = _all_courses()
    course_by_id = {c["id"]: c for c in courses}

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
