"""
feedback

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.schemas import (
    CreateDepartmentFeedbackRequest,
    CreateSurveyRequest,
    ExternalReviewWebhookRequest,
    SubmitSurveyResponseRequest,
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW

DEFAULT_UPSELL_PRICES = {
    "early_checkin": 25.00,
    "late_checkout": 35.00,
    "airport_transfer": 50.00,
}


async def _get_upsell_prices(tenant_id: str) -> dict:
    """Return per-tenant upsell prices, falling back to defaults for any missing key."""
    prices = dict(DEFAULT_UPSELL_PRICES)
    doc = await db.upsell_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if doc and isinstance(doc.get("prices"), dict):
        for k, v in doc["prices"].items():
            if k in prices:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv >= 0:
                    prices[k] = fv
    return prices


# ============= PHASE H: GUEST CRM + UPSELL AI + MESSAGING =============









_MANUAL_UPSELL_TYPES = {
    "early_checkin", "late_checkout", "airport_transfer",
    "room_upgrade", "spa_package", "dining_credit", "champagne", "custom",
}














async def check_rate_limit(tenant_id: str, channel: str, limit_per_hour: int = 100) -> bool:
    """Check if rate limit is exceeded for messaging"""
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    count = await db.messages.count_documents({
        'tenant_id': tenant_id,
        'channel': channel,
        'sent_at': {'$gte': one_hour_ago}
    })

    return count < limit_per_hour








# Router will be included at the very end after ALL endpoints are defined

logger = logging.getLogger(__name__)



# ========================================

# 1. EXTERNAL REVIEW API INTEGRATION (Booking.com, Google, TripAdvisor)





# 2. IN-HOUSE SURVEY SYSTEM





# 3. DEPARTMENT-BASED SATISFACTION TRACKING




# ============= GUEST MOBILE APP ENDPOINTS =============

# rbac-allow: cache-rbac — GUEST portal — kendi rezervasyonları


































# ============================================================================
# REVIEW INVITES — Misafire e-posta ile değerlendirme linki gönder
# ============================================================================

def _render_review_invite_email(*, hotel_name: str, guest_name: str, link: str) -> tuple[str, str]:
    """Build (html, text) bodies for the review invite e-mail."""
    safe_guest = (guest_name or "Değerli Misafirimiz").strip() or "Değerli Misafirimiz"
    text = (
        f"Merhaba {safe_guest},\n\n"
        f"{hotel_name} olarak konaklamanızı değerlendirmenizi rica ederiz.\n"
        f"Aşağıdaki bağlantıdan birkaç dakikanızı ayırabilirsiniz:\n\n"
        f"{link}\n\n"
        f"Geri bildiriminiz hizmet kalitemizi geliştirmemize yardımcı oluyor.\n"
        f"Teşekkür ederiz.\n\n"
        f"{hotel_name}"
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f6f7fb;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
        <tr><td style="padding:28px 32px 8px 32px;">
          <h1 style="margin:0;font-size:20px;color:#111827;">{hotel_name}</h1>
          <p style="margin:4px 0 0 0;color:#6b7280;font-size:13px;">Konaklama Değerlendirmesi</p>
        </td></tr>
        <tr><td style="padding:16px 32px 8px 32px;">
          <p style="font-size:15px;line-height:1.6;margin:0 0 12px 0;">Merhaba <strong>{safe_guest}</strong>,</p>
          <p style="font-size:15px;line-height:1.6;margin:0 0 16px 0;">
            Bizi tercih ettiğiniz için teşekkür ederiz. Konaklamanızla ilgili görüşlerinizi
            bizimle paylaşmanız hizmet kalitemizi geliştirmemize yardımcı olacaktır.
          </p>
          <p style="font-size:15px;line-height:1.6;margin:0 0 24px 0;">
            Birkaç dakikanızı ayırarak değerlendirme yapabilir misiniz?
          </p>
        </td></tr>
        <tr><td align="center" style="padding:8px 32px 24px 32px;">
          <a href="{link}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:15px;">Değerlendirme Yap</a>
        </td></tr>
        <tr><td style="padding:0 32px 24px 32px;">
          <p style="font-size:12px;color:#6b7280;margin:0 0 4px 0;">Bağlantı çalışmıyorsa kopyalayıp tarayıcınıza yapıştırabilirsiniz:</p>
          <p style="font-size:12px;color:#374151;word-break:break-all;margin:0;"><a href="{link}" style="color:#2563eb;">{link}</a></p>
        </td></tr>
        <tr><td style="padding:16px 32px 24px 32px;border-top:1px solid #e5e7eb;">
          <p style="font-size:12px;color:#9ca3af;margin:0;">{hotel_name} • Bu e-posta konaklamanız sebebiyle gönderilmiştir.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
    return html, text




_REVIEW_INVITE_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")
_REVIEW_INVITE_INDEX_READY = False


async def _ensure_review_invite_indexes() -> None:
    """Idempotently ensure unique index on review_invites.token."""
    global _REVIEW_INVITE_INDEX_READY
    if _REVIEW_INVITE_INDEX_READY:
        return
    try:
        await db.review_invites.create_index("token", unique=True, name="uniq_token")
        await db.review_invites.create_index("tenant_id", name="by_tenant")
    except Exception as exc:  # pragma: no cover - best effort
        logging.warning("[review-invite] index ensure failed: %s", exc)
    _REVIEW_INVITE_INDEX_READY = True


def _validate_review_invite_token(token: str) -> None:
    if not token or not _REVIEW_INVITE_TOKEN_RE.match(token):
        raise HTTPException(status_code=400, detail="Geçersiz bağlantı")


def _check_invite_expiry_or_raise(expires_raw) -> None:
    """Fail-closed: missing or unparseable expiry is treated as expired."""
    if not expires_raw:
        raise HTTPException(status_code=410, detail="Bu davetin süresi dolmuş")
    try:
        exp = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=410, detail="Bu davetin süresi dolmuş") from exc
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Bu davetin süresi dolmuş")

router = APIRouter(prefix="/api", tags=["guest-experience"])


# ── POST /feedback/external-review-webhook ──
@router.post("/feedback/external-review-webhook")
async def receive_external_review(
    request: ExternalReviewWebhookRequest,
    current_user: User = Depends(get_current_user)
):
    """Webhook to receive reviews from external platforms"""
    review = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'platform': request.platform,
        'external_review_id': request.review_id,
        'rating': request.rating,
        'reviewer_name': request.reviewer_name,
        'review_text': request.review_text,
        'review_date': request.review_date,
        'booking_reference': request.booking_reference,
        'status': 'new',
        'sentiment': 'positive' if request.rating >= 4.0 else ('neutral' if request.rating >= 3.0 else 'negative'),
        'received_at': datetime.now(UTC).isoformat()
    }

    review_copy = review.copy()
    await db.external_reviews.insert_one(review_copy)

    return {'message': 'External review received successfully', 'review_id': review['id']}
# ── GET /feedback/external-reviews ──
@router.get("/feedback/external-reviews")
async def get_external_reviews(
    platform: str = None,
    sentiment: str = None,
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get reviews from external platforms"""
    query = {'tenant_id': current_user.tenant_id}

    if platform:
        query['platform'] = platform
    if sentiment:
        query['sentiment'] = sentiment
    if start_date and end_date:
        query['review_date'] = {'$gte': start_date, '$lte': end_date}

    reviews = await db.external_reviews.find(
        query,
        {'_id': 0}
    ).sort('review_date', -1).to_list(1000)

    return {'reviews': reviews, 'count': len(reviews)}
# ── GET /feedback/external-reviews/summary ──
@router.get("/feedback/external-reviews/summary")
async def get_external_reviews_summary(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get aggregated summary of external reviews"""
    query = {'tenant_id': current_user.tenant_id}

    if start_date and end_date:
        query['review_date'] = {'$gte': start_date, '$lte': end_date}

    reviews = await db.external_reviews.find(query, {'_id': 0}).to_list(10000)

    if not reviews:
        return {
            'message': 'No external reviews found',
            'summary': {}
        }

    # Calculate platform breakdown
    platform_stats = {}
    for review in reviews:
        platform = review.get('platform', 'unknown')
        if platform not in platform_stats:
            platform_stats[platform] = {
                'count': 0,
                'total_rating': 0,
                'positive': 0,
                'neutral': 0,
                'negative': 0
            }

        platform_stats[platform]['count'] += 1
        platform_stats[platform]['total_rating'] += review.get('rating', 0)

        sentiment = review.get('sentiment', 'neutral')
        platform_stats[platform][sentiment] += 1

    # Calculate averages
    for platform, stats in platform_stats.items():
        if stats['count'] > 0:
            stats['avg_rating'] = round(stats['total_rating'] / stats['count'], 2)

    # Overall stats
    total_reviews = len(reviews)
    avg_rating = sum(r.get('rating', 0) for r in reviews) / total_reviews if total_reviews > 0 else 0

    sentiment_breakdown = {
        'positive': sum(1 for r in reviews if r.get('sentiment') == 'positive'),
        'neutral': sum(1 for r in reviews if r.get('sentiment') == 'neutral'),
        'negative': sum(1 for r in reviews if r.get('sentiment') == 'negative')
    }

    return {
        'summary': {
            'total_reviews': total_reviews,
            'avg_rating': round(avg_rating, 2),
            'sentiment_breakdown': sentiment_breakdown,
            'platforms': platform_stats
        },
        'date_range': f"{start_date or 'all'} to {end_date or 'all'}"
    }
# ── POST /feedback/external-reviews/{review_id}/respond ──
@router.post("/feedback/external-reviews/{review_id}/respond")
async def respond_to_external_review(
    review_id: str,
    response_text: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Respond to external review"""
    review = await db.external_reviews.find_one({
        'id': review_id,
        'tenant_id': current_user.tenant_id
    })

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    await db.external_reviews.update_one(
        {'id': review_id},
        {
            '$set': {
                'response': response_text,
                'responded_at': datetime.now(UTC).isoformat(),
                'responded_by': current_user.id,
                'status': 'responded'
            }
        }
    )

    return {'message': 'Response posted successfully'}
# ── GET /feedback/surveys ──
@router.get("/feedback/surveys")
async def get_surveys(current_user: User = Depends(get_current_user)):
    """Get all surveys"""
    surveys = await db.surveys.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    # Get response counts
    for survey in surveys:
        response_count = await db.survey_responses.count_documents({
            'tenant_id': current_user.tenant_id,
            'survey_id': survey['id']
        })
        survey['response_count'] = response_count

    return {'surveys': surveys, 'count': len(surveys)}
# ── POST /feedback/surveys ──
@router.post("/feedback/surveys")
async def create_survey(
    request: CreateSurveyRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Create new survey"""
    survey = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'survey_name': request.survey_name,
        'description': request.description,
        'target_department': request.target_department,
        'questions': request.questions,
        'trigger': request.trigger,
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    survey_copy = survey.copy()
    await db.surveys.insert_one(survey_copy)
    return survey
# ── POST /feedback/surveys/response ──
@router.post("/feedback/surveys/response")
async def submit_survey_response(
    request: SubmitSurveyResponseRequest,
    current_user: User = Depends(get_current_user)
):
    """Submit survey response"""
    # Verify survey exists
    survey = await db.surveys.find_one({
        'id': request.survey_id,
        'tenant_id': current_user.tenant_id
    })

    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    # Calculate overall rating
    ratings = [r.get('rating') for r in request.responses if r.get('rating')]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    response = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'survey_id': request.survey_id,
        'survey_name': survey.get('survey_name'),
        'booking_id': request.booking_id,
        'guest_name': request.guest_name,
        'guest_email': request.guest_email,
        'responses': request.responses,
        'overall_rating': round(avg_rating, 2) if avg_rating else None,
        'submitted_at': datetime.now(UTC).isoformat()
    }

    response_copy = response.copy()
    await db.survey_responses.insert_one(response_copy)

    return {'message': 'Survey response submitted successfully', 'response_id': response['id']}
# ── GET /feedback/surveys/{survey_id}/responses ──
@router.get("/feedback/surveys/{survey_id}/responses")
async def get_survey_responses(
    survey_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get responses for specific survey"""
    # Verify survey
    survey = await db.surveys.find_one({
        'id': survey_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    # Get responses
    responses = await db.survey_responses.find({
        'tenant_id': current_user.tenant_id,
        'survey_id': survey_id
    }, {'_id': 0}).to_list(1000)

    # Calculate statistics
    if responses:
        ratings = [r.get('overall_rating') for r in responses if r.get('overall_rating')]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        # Aggregate answers per question
        question_stats = {}
        for response in responses:
            for answer in response.get('responses', []):
                q_id = answer.get('question_id', 'unknown')
                if q_id not in question_stats:
                    question_stats[q_id] = {
                        'ratings': [],
                        'answers': []
                    }

                if answer.get('rating'):
                    question_stats[q_id]['ratings'].append(answer['rating'])
                if answer.get('answer'):
                    question_stats[q_id]['answers'].append(answer['answer'])

        # Calculate averages
        for q_id, stats in question_stats.items():
            if stats['ratings']:
                stats['avg_rating'] = round(sum(stats['ratings']) / len(stats['ratings']), 2)
    else:
        avg_rating = 0
        question_stats = {}

    return {
        'survey': survey,
        'responses': responses,
        'statistics': {
            'total_responses': len(responses),
            'avg_overall_rating': round(avg_rating, 2),
            'question_stats': question_stats
        }
    }
# ── POST /feedback/department ──
@router.post("/feedback/department")
async def submit_department_feedback(
    request: CreateDepartmentFeedbackRequest,
    current_user: User = Depends(get_current_user)
):
    """Submit feedback for specific department"""
    feedback = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'department': request.department,
        'booking_id': request.booking_id,
        'guest_name': request.guest_name,
        'rating': request.rating,
        'comment': request.comment,
        'staff_member': request.staff_member,
        'sentiment': 'positive' if request.rating >= 4 else ('neutral' if request.rating == 3 else 'negative'),
        'submitted_at': datetime.now(UTC).isoformat()
    }

    feedback_copy = feedback.copy()
    await db.department_feedback.insert_one(feedback_copy)

    return {'message': 'Department feedback submitted successfully', 'feedback_id': feedback['id']}
# ── GET /feedback/department ──
@router.get("/feedback/department")
async def get_department_feedback(
    department: str = None,
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get department feedback"""
    query = {'tenant_id': current_user.tenant_id}

    if department:
        query['department'] = department

    if start_date and end_date:
        query['submitted_at'] = {'$gte': start_date, '$lte': end_date}

    feedback = await db.department_feedback.find(
        query,
        {'_id': 0}
    ).sort('submitted_at', -1).to_list(1000)

    return {'feedback': feedback, 'count': len(feedback)}
# ── GET /feedback/department/summary ──
@router.get("/feedback/department/summary")
async def get_department_satisfaction_summary(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get department satisfaction summary"""
    query = {'tenant_id': current_user.tenant_id}

    if start_date and end_date:
        query['submitted_at'] = {'$gte': start_date, '$lte': end_date}

    feedback = await db.department_feedback.find(query, {'_id': 0}).to_list(10000)

    if not feedback:
        return {
            'message': 'No department feedback found',
            'summary': {}
        }

    # Aggregate by department
    dept_stats = {}
    departments = ['housekeeping', 'front_desk', 'fnb', 'spa', 'concierge']

    for dept in departments:
        dept_feedback = [f for f in feedback if f.get('department') == dept]

        if dept_feedback:
            ratings = [f.get('rating', 0) for f in dept_feedback]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0

            sentiment_counts = {
                'positive': sum(1 for f in dept_feedback if f.get('sentiment') == 'positive'),
                'neutral': sum(1 for f in dept_feedback if f.get('sentiment') == 'neutral'),
                'negative': sum(1 for f in dept_feedback if f.get('sentiment') == 'negative')
            }

            dept_stats[dept] = {
                'total_feedback': len(dept_feedback),
                'avg_rating': round(avg_rating, 2),
                'sentiment_breakdown': sentiment_counts,
                'satisfaction_rate': round((sentiment_counts['positive'] / len(dept_feedback) * 100), 1) if dept_feedback else 0
            }
        else:
            dept_stats[dept] = {
                'total_feedback': 0,
                'avg_rating': 0,
                'sentiment_breakdown': {'positive': 0, 'neutral': 0, 'negative': 0},
                'satisfaction_rate': 0
            }

    # Overall stats
    all_ratings = [f.get('rating', 0) for f in feedback]
    overall_avg = sum(all_ratings) / len(all_ratings) if all_ratings else 0

    # Staff member performance
    staff_performance = {}
    for f in feedback:
        if f.get('staff_member'):
            staff = f['staff_member']
            if staff not in staff_performance:
                staff_performance[staff] = {
                    'ratings': [],
                    'department': f.get('department')
                }
            staff_performance[staff]['ratings'].append(f.get('rating', 0))

    # Calculate staff averages
    staff_stats = []
    for staff, data in staff_performance.items():
        if data['ratings']:
            avg = sum(data['ratings']) / len(data['ratings'])
            staff_stats.append({
                'staff_member': staff,
                'department': data['department'],
                'avg_rating': round(avg, 2),
                'feedback_count': len(data['ratings'])
            })

    staff_stats.sort(key=lambda x: x['avg_rating'], reverse=True)

    return {
        'summary': {
            'total_feedback': len(feedback),
            'overall_avg_rating': round(overall_avg, 2),
            'departments': dept_stats,
            'top_performers': staff_stats[:10],
            'needs_attention': [
                {'department': dept, 'avg_rating': stats['avg_rating']}
                for dept, stats in dept_stats.items()
                if stats['avg_rating'] > 0 and stats['avg_rating'] < 3.5
            ]
        },
        'date_range': f"{start_date or 'all'} to {end_date or 'all'}"
    }
# ── POST /feedback/review-invite ──
@router.post("/feedback/review-invite")
async def send_review_invite(
    payload: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Create a review invite for a booking and send the e-mail."""
    booking_id = (payload or {}).get("booking_id")
    if not booking_id or not isinstance(booking_id, str):
        raise HTTPException(status_code=400, detail="booking_id is required")

    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    guest_email = (payload.get("guest_email") or booking.get("guest_email") or "").strip().lower()
    if not guest_email or "@" not in guest_email:
        raise HTTPException(status_code=400, detail="Misafirin geçerli bir e-posta adresi yok")

    tenant = await db.tenants.find_one(
        {"id": current_user.tenant_id},
        {"_id": 0, "name": 1, "hotel_name": 1},
    ) or {}
    hotel_name = (tenant.get("hotel_name") or tenant.get("name") or "Otel").strip()

    await _ensure_review_invite_indexes()
    token = uuid.uuid4().hex
    invite = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "token": token,
        "booking_id": booking_id,
        "guest_name": booking.get("guest_name") or "",
        "guest_email": guest_email,
        "hotel_name": hotel_name,
        "room_number": booking.get("room_number") or "",
        "check_in": booking.get("check_in") or "",
        "check_out": booking.get("check_out") or "",
        "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }
    await db.review_invites.insert_one(invite.copy())

    from core.email import _frontend_base_url, send_email  # local import; avoid circulars
    base = _frontend_base_url()
    link = f"{base.rstrip('/')}/review/{token}"
    subject = f"{hotel_name} — Konaklamanızı değerlendirir misiniz?"
    html, text = _render_review_invite_email(
        hotel_name=hotel_name,
        guest_name=invite["guest_name"],
        link=link,
    )

    send_result = {"sent": False}
    try:
        send_result = await send_email(to=guest_email, subject=subject, html=html, text=text)
    except Exception as exc:  # pragma: no cover - mail provider may be offline
        logging.exception("[review-invite] e-mail send failed: %s", exc)
        send_result = {"sent": False, "error": str(exc)}

    await create_audit_log(
        current_user.tenant_id,
        current_user,
        "send_review_invite",
        "review_invite",
        invite["id"],
        changes={"booking_id": booking_id, "guest_email": guest_email, "sent": bool(send_result.get("sent"))},
    )

    return {
        "success": True,
        "invite_id": invite["id"],
        "sent": bool(send_result.get("sent")),
        "link": link,
    }
# ── GET /feedback/public/invite/{token} ──
@router.get("/feedback/public/invite/{token}")
async def get_review_invite_public(token: str):
    """Public lookup of a review invite (no auth)."""
    _validate_review_invite_token(token)

    invite = await db.review_invites.find_one({"token": token}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Davet bulunamadı")

    if invite.get("status") == "submitted":
        raise HTTPException(status_code=410, detail="Bu davet daha önce kullanılmış")

    _check_invite_expiry_or_raise(invite.get("expires_at"))

    return {
        "token": token,
        "hotel_name": invite.get("hotel_name"),
        "guest_name": invite.get("guest_name"),
        "room_number": invite.get("room_number"),
        "check_in": invite.get("check_in"),
        "check_out": invite.get("check_out"),
    }
# ── POST /feedback/public/invite/{token} ──
@router.post("/feedback/public/invite/{token}")
async def submit_review_public(token: str, payload: dict):
    """Public submission of a review using an invite token (no auth).

    Atomically claims the invite (status: pending -> submitting) before creating
    the review to prevent concurrent double-submission.
    """
    _validate_review_invite_token(token)

    raw_rating = (payload or {}).get("rating")
    try:
        rating = int(raw_rating)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Geçerli bir puan giriniz (1-5)") from exc
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Puan 1 ile 5 arasında olmalı")

    # Pre-check existence + expiry so we can return accurate error codes (404/410)
    pre = await db.review_invites.find_one({"token": token}, {"status": 1, "expires_at": 1})
    if not pre:
        raise HTTPException(status_code=404, detail="Davet bulunamadı")
    if pre.get("status") == "submitted":
        raise HTTPException(status_code=410, detail="Bu davet daha önce kullanılmış")
    _check_invite_expiry_or_raise(pre.get("expires_at"))

    # Atomic claim: only succeeds if status is still "pending".
    claim_ts = datetime.now(UTC).isoformat()
    invite = await db.review_invites.find_one_and_update(
        {"token": token, "status": "pending"},
        {"$set": {"status": "submitting", "claimed_at": claim_ts}},
    )
    if not invite:
        # Lost the race or invite consumed between pre-check and claim.
        raise HTTPException(status_code=410, detail="Bu davet daha önce kullanılmış")

    comment = ((payload or {}).get("comment") or "").strip()[:2000]
    submitted_name = ((payload or {}).get("guest_name") or "").strip()[:120]
    final_name = submitted_name or (invite.get("guest_name") or "").strip()[:120] or "Misafir"

    review = {
        "id": str(uuid.uuid4()),
        "tenant_id": invite["tenant_id"],
        "booking_id": invite.get("booking_id"),
        "guest_name": final_name,
        "rating": rating,
        "comment": comment,
        "source": "direct_invite",
        "category": "Konaklama",
        "sentiment": "positive" if rating >= 4 else ("neutral" if rating == 3 else "negative"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        await db.guest_reviews.insert_one(review.copy())
    except Exception:
        # Roll back the claim so the guest can retry.
        await db.review_invites.update_one(
            {"_id": invite["_id"], "status": "submitting"},
            {"$set": {"status": "pending"}, "$unset": {"claimed_at": ""}},
        )
        raise

    await db.review_invites.update_one(
        {"_id": invite["_id"]},
        {"$set": {
            "status": "submitted",
            "submitted_at": datetime.now(UTC).isoformat(),
            "review_id": review["id"],
        }},
    )

    return {"success": True, "review_id": review["id"]}
