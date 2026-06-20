"""Syroce Academy — staff training, server-scored exams, certificates.

All endpoints are tenant-scoped and gated by the `academy` add-on module
(`require_module("academy")`). The management report carries an additional
role guard. Curriculum (with correct answers) is system-owned content; the
answer key never leaves the server and exam scores are computed server-side.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from core import academy
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger("academy")

router = APIRouter(
    prefix="/api/academy",
    tags=["academy"],
    dependencies=[Depends(require_module("academy"))],
)


def _require_tenant(user: User) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Otel hesabi gerekli")
    return user.tenant_id


def _norm_role(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


class ExamSubmission(BaseModel):
    # Maps question_id -> selected option index. A client-supplied score or
    # pass flag is intentionally NOT part of this contract.
    answers: dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Student endpoints                                                            #
# --------------------------------------------------------------------------- #

@router.get("/courses")
async def list_courses(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_tenant(current_user)
    role = _norm_role(current_user)
    progress = await academy.get_all_progress(tenant_id, current_user.id)
    items = []
    for course in await academy.list_courses_for(tenant_id, role):
        summary = academy.public_course_summary(course)
        p = progress.get(course["id"])
        summary["progress"] = {
            "status": academy._compute_status(p, summary["lesson_count"]),
            "lessons_completed": len((p or {}).get("completed_lessons") or []),
            "best_score": (p or {}).get("best_score", 0),
            "passed": bool((p or {}).get("passed")),
            "attempts": (p or {}).get("attempts", 0),
        }
        items.append(summary)
    return {"count": len(items), "items": items}


async def _visible_course_or_404(
    tenant_id: str, course_id: str, current_user: User,
) -> dict:
    """Resolve a system OR tenant-custom course the caller's role may view.

    Hidden system courses and draft custom courses resolve to ``None`` (-> 404),
    and a role the course does not target also yields 404 — identical 404 for
    every "not for you" reason so existence is never leaked.
    """
    course = await academy.resolve_course(tenant_id, course_id)
    role = _norm_role(current_user)
    if not course or not academy.course_visible_to_role(course, role):
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return course


@router.get("/courses/{course_id}")
async def get_course(
    course_id: str, current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant(current_user)
    course = await _visible_course_or_404(tenant_id, course_id, current_user)
    detail = academy.public_course_detail(course)
    p = await academy.get_progress(tenant_id, current_user.id, course_id)
    detail["progress"] = {
        "status": academy._compute_status(p, detail["lesson_count"]),
        "completed_lessons": (p or {}).get("completed_lessons") or [],
        "best_score": (p or {}).get("best_score", 0),
        "passed": bool((p or {}).get("passed")),
        "attempts": (p or {}).get("attempts", 0),
    }
    return detail


@router.post("/courses/{course_id}/lessons/{lesson_id}/complete")
async def complete_lesson(
    course_id: str, lesson_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant(current_user)
    course = await _visible_course_or_404(tenant_id, course_id, current_user)
    try:
        progress = await academy.mark_lesson_complete(
            tenant_id, current_user.id, course, lesson_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lesson_count = len(course.get("lessons") or [])
    return {
        "ok": True,
        "completed_lessons": progress.get("completed_lessons") or [],
        "lesson_count": lesson_count,
    }


@router.get("/courses/{course_id}/exam")
async def get_exam(
    course_id: str, current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant(current_user)
    course = await _visible_course_or_404(tenant_id, course_id, current_user)
    # Answer key is stripped here — only prompts + options are returned.
    return academy.public_exam(course)


@router.post("/courses/{course_id}/exam/submit")
async def submit_exam(
    course_id: str, submission: ExamSubmission,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant(current_user)
    course = await _visible_course_or_404(tenant_id, course_id, current_user)
    # Scoring is server-side ONLY; submission carries answers, never a score.
    result = academy.score_exam(course, submission.answers)
    outcome = await academy.record_attempt(
        tenant_id, current_user.id, current_user.name, course, result,
    )
    return outcome


@router.get("/certificates")
async def list_certificates(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_tenant(current_user)
    items = await academy.get_certificates(tenant_id, current_user.id)
    return {"count": len(items), "items": items}


@router.get("/certificates/{cert_id}/pdf")
async def download_certificate(
    cert_id: str, current_user: User = Depends(get_current_user),
):
    tenant_id = _require_tenant(current_user)
    cert = await academy.get_certificate(tenant_id, current_user.id, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Sertifika bulunamadi")
    try:
        pdf = academy.render_certificate_pdf(cert)
    except (ImportError, OSError) as exc:
        logger.error("[Academy PDF] weasyprint unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="PDF olusturucu (weasyprint) bu ortamda kullanilamiyor.",
        ) from exc
    except Exception as exc:
        logger.exception("[Academy PDF] render failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"PDF olusturulamadi: {type(exc).__name__}",
        ) from exc
    filename = f"sertifika-{cert.get('verification_code', cert_id)}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Manager report                                                               #
# --------------------------------------------------------------------------- #

@router.get("/admin/report")
async def admin_report(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_tenant(current_user)
    role = _norm_role(current_user)
    if role not in academy.MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Bu rapor icin yetkiniz yok")
    return await academy.get_tenant_report(tenant_id)


# --------------------------------------------------------------------------- #
# Manager authoring — tenant-custom course CRUD + built-in visibility.        #
#                                                                              #
# These endpoints are author-only (`_require_author`). The editor view DOES    #
# include the answer key + inline lesson bodies because the manager OWNS that  #
# content; the answer key is never exposed on any student-facing endpoint.     #
# --------------------------------------------------------------------------- #

_MAX_LESSON_BODY = 50_000
_MAX_OPTION_LEN = 500


class LessonInput(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    body_markdown: str = Field(default="", max_length=_MAX_LESSON_BODY)


class QuestionInput(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    prompt: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=8)
    answer_index: int = Field(ge=0)

    @field_validator("options")
    @classmethod
    def _clean_options(cls, v: list[str]) -> list[str]:
        cleaned = [str(o).strip() for o in v]
        if any(not o for o in cleaned):
            raise ValueError("Secenekler bos olamaz")
        if any(len(o) > _MAX_OPTION_LEN for o in cleaned):
            raise ValueError("Secenek cok uzun")
        return cleaned

    @model_validator(mode="after")
    def _answer_in_range(self):
        if self.answer_index >= len(self.options):
            raise ValueError("Dogru cevap secenek araliginda olmali")
        return self


class CourseInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=80)
    department_label: str | None = Field(default=None, max_length=120)
    summary: str = Field(default="", max_length=2000)
    roles: list[str] = Field(default_factory=list, max_length=20)
    draft: bool = True
    pass_threshold: int = Field(default=70, ge=1, le=100)
    estimated_minutes: int | None = Field(default=None, ge=0, le=100_000)
    lessons: list[LessonInput] = Field(default_factory=list, max_length=100)
    questions: list[QuestionInput] = Field(default_factory=list, max_length=200)

    @field_validator("roles")
    @classmethod
    def _clean_roles(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for r in v:
            rr = str(r).strip()
            if rr not in academy.ACADEMY_COURSE_ROLES:
                raise ValueError(f"Gecersiz rol: {rr}")
            if rr not in cleaned:
                cleaned.append(rr)
        return cleaned

    @model_validator(mode="after")
    def _publish_requires_content(self):
        if not self.draft:
            if not self.lessons:
                raise ValueError("Yayinlamak icin en az 1 ders gerekli")
            if not self.questions:
                raise ValueError("Yayinlamak icin en az 1 soru gerekli")
        return self


class VisibilityInput(BaseModel):
    hidden: bool


class SystemCourseContentInput(BaseModel):
    """Per-tenant CONTENT override for a BUILT-IN course.

    Mirrors ``CourseInput`` minus ``draft`` — built-in overrides are always live,
    so at least one lesson and one question are ALWAYS required (no draft state).
    """
    title: str = Field(min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=80)
    department_label: str | None = Field(default=None, max_length=120)
    summary: str = Field(default="", max_length=2000)
    roles: list[str] = Field(default_factory=list, max_length=20)
    pass_threshold: int = Field(default=70, ge=1, le=100)
    estimated_minutes: int | None = Field(default=None, ge=0, le=100_000)
    lessons: list[LessonInput] = Field(min_length=1, max_length=100)
    questions: list[QuestionInput] = Field(min_length=1, max_length=200)

    @field_validator("roles")
    @classmethod
    def _clean_roles(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for r in v:
            rr = str(r).strip()
            if rr not in academy.ACADEMY_COURSE_ROLES:
                raise ValueError(f"Gecersiz rol: {rr}")
            if rr not in cleaned:
                cleaned.append(rr)
        return cleaned


def _require_author(current_user: User) -> str:
    tenant_id = _require_tenant(current_user)
    if _norm_role(current_user) not in academy.ACADEMY_AUTHOR_ROLES:
        raise HTTPException(status_code=403, detail="Bu islem icin yetkiniz yok")
    return tenant_id


def _admin_course_detail(course: dict) -> dict:
    """Full editor view of a tenant-custom course — INCLUDES the answer key and
    inline lesson bodies (author-only surface)."""
    detail = academy.public_course_summary(course)
    detail["lessons"] = [
        {
            "id": l.get("id"),
            "title": l.get("title"),
            "body_markdown": l.get("body_markdown") or "",
        }
        for l in course.get("lessons") or []
    ]
    detail["questions"] = [
        {
            "id": q.get("id"),
            "prompt": q.get("prompt"),
            "options": list(q.get("options") or []),
            "answer_index": q.get("answer_index"),
        }
        for q in course.get("questions") or []
    ]
    return detail


@router.get("/admin/courses")
async def admin_list_courses(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_author(current_user)
    # List view strips answers (summary only); the editor fetches full detail.
    items = [
        academy.public_course_summary(c)
        for c in await academy.list_author_courses(tenant_id)
    ]
    return {"count": len(items), "items": items}


@router.post("/admin/courses")
async def admin_create_course(
    payload: CourseInput, current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_author(current_user)
    course = await academy.create_author_course(
        tenant_id, current_user.id, payload.model_dump(),
    )
    return _admin_course_detail(course)


@router.get("/admin/courses/{course_id}")
async def admin_get_course(
    course_id: str, current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_author(current_user)
    course = await academy.get_author_course(tenant_id, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return _admin_course_detail(course)


@router.put("/admin/courses/{course_id}")
async def admin_update_course(
    course_id: str, payload: CourseInput,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_author(current_user)
    course = await academy.update_author_course(
        tenant_id, current_user.id, course_id, payload.model_dump(),
    )
    if not course:
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return _admin_course_detail(course)


@router.delete("/admin/courses/{course_id}")
async def admin_delete_course(
    course_id: str, current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_author(current_user)
    if not await academy.delete_author_course(tenant_id, course_id):
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return {"ok": True}


@router.get("/admin/system-courses")
async def admin_list_system_courses(
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_author(current_user)
    items = await academy.list_system_courses_for(tenant_id)
    return {"count": len(items), "items": items}


@router.put("/admin/system-courses/{course_id}/visibility")
async def admin_set_system_visibility(
    course_id: str, payload: VisibilityInput,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_author(current_user)
    if not await academy.set_system_course_hidden(
        tenant_id, course_id, payload.hidden,
    ):
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return {"ok": True, "hidden": payload.hidden}


@router.get("/admin/system-courses/{course_id}/content")
async def admin_get_system_content(
    course_id: str, current_user: User = Depends(get_current_user),
) -> dict:
    """Editor view of a built-in course (default merged with any per-tenant
    override). Author-only — INCLUDES the answer key + inline lesson bodies."""
    tenant_id = _require_author(current_user)
    course = await academy.get_system_course_for_edit(tenant_id, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return _admin_course_detail(course)


@router.put("/admin/system-courses/{course_id}/content")
async def admin_set_system_content(
    course_id: str, payload: SystemCourseContentInput,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Store a per-tenant CONTENT override for a built-in course. The catalog
    file is never touched; the course id (and thus learner progress) is kept."""
    tenant_id = _require_author(current_user)
    course = await academy.set_system_course_content(
        tenant_id, current_user.id, course_id, payload.model_dump(),
    )
    if not course:
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return _admin_course_detail(course)


@router.delete("/admin/system-courses/{course_id}/content")
async def admin_reset_system_content(
    course_id: str, current_user: User = Depends(get_current_user),
) -> dict:
    """Reset a built-in course to its catalog default (remove the content
    override). Any per-tenant visibility (hidden) state is preserved."""
    tenant_id = _require_author(current_user)
    if not await academy.reset_system_course(tenant_id, course_id):
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return {"ok": True}
