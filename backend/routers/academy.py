"""Syroce Academy — staff training, server-scored exams, certificates.

All endpoints are tenant-scoped and gated by the `academy` add-on module
(`require_module("academy")`). The management report carries an additional
role guard. Curriculum (with correct answers) is system-owned content; the
answer key never leaves the server and exam scores are computed server-side.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

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
    for course in academy.load_catalog().get("courses", []):
        if not academy.course_visible_to_role(course, role):
            continue
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


def _visible_course_or_404(course_id: str, current_user: User) -> dict:
    course = academy.get_course_raw(course_id)
    role = _norm_role(current_user)
    if not course or not academy.course_visible_to_role(course, role):
        raise HTTPException(status_code=404, detail="Kurs bulunamadi")
    return course


@router.get("/courses/{course_id}")
async def get_course(
    course_id: str, current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant(current_user)
    course = _visible_course_or_404(course_id, current_user)
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
    course = _visible_course_or_404(course_id, current_user)
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
    _require_tenant(current_user)
    course = _visible_course_or_404(course_id, current_user)
    # Answer key is stripped here — only prompts + options are returned.
    return academy.public_exam(course)


@router.post("/courses/{course_id}/exam/submit")
async def submit_exam(
    course_id: str, submission: ExamSubmission,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant(current_user)
    course = _visible_course_or_404(course_id, current_user)
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
