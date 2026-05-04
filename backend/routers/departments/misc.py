"""
misc

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Department-Specific Endpoints Router
Front Office, Housekeeping Manager, Finance, Revenue, F&B, Maintenance,
Sales, HR, IT/Security department dashboards.
Extracted from server.py for modularity.
"""
import logging

from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW

logger = logging.getLogger(__name__)
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import RolePermissionService, require_op

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CU (v60) — Departments/Reports/Rates/POS RBAC zorunlu."""
    _role_perm.enforce_permission(role, op)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
except ImportError:
    Workbook = None

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

security = HTTPBearer()


# ==================== DEPARTMENT-SPECIFIC ENDPOINTS ====================

# rbac-allow: cache-rbac — FO dashboard operasyonel, hotel staff geneli görür (FO/HK/manager/admin)

# rbac-allow: cache-rbac — HK dashboard operasyonel, FO/HK/manager/admin görür








# NOTE: /ai/dashboard/briefing duplicate removed (R10b) — canonical implementation
# lives in `domains/ai/endpoints.py::get_daily_briefing` with @cached(ttl=300) and
# parallel `_asyncio.gather` over 4 collections.




# rbac-allow: cache-rbac — booking için müsait odalar operasyonel (FO/HK/manager)



# rbac-allow: cache-rbac — HK aktif temizlik timer'ları operasyonel (HK/FO/manager)











































# rbac-allow: cache-rbac — task kanban operasyonel cross-role (FO/HK/maintenance/manager)

router = APIRouter(prefix="/api", tags=["departments"])


# ── POST /reviews/ai-sentiment-analysis ──
@router.post("/reviews/ai-sentiment-analysis")
async def ai_sentiment_analysis(
    data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """
    AI Sentiment Analysis for guest reviews
    Returns: sentiment, confidence, issues, highlights, recommendations
    """
    review_text = data.get('review_text', '')

    if not review_text:
        raise HTTPException(status_code=400, detail='Review text is required')

    review_lower = review_text.lower()

    negative_keywords = ['dirty', 'broken', 'bad', 'terrible', 'awful', 'poor', 'noise', 'smell', 'rude', 'slow']
    positive_keywords = ['great', 'excellent', 'amazing', 'wonderful', 'clean', 'friendly', 'helpful', 'perfect', 'love']

    negative_count = sum(1 for keyword in negative_keywords if keyword in review_lower)
    positive_count = sum(1 for keyword in positive_keywords if keyword in review_lower)

    if negative_count > positive_count:
        sentiment = 'negative'
        confidence = min(0.6 + (negative_count * 0.1), 0.95)
    elif positive_count > negative_count:
        sentiment = 'positive'
        confidence = min(0.6 + (positive_count * 0.1), 0.95)
    else:
        sentiment = 'neutral'
        confidence = 0.5

    issues = []
    if 'dirty' in review_lower or 'clean' in review_lower:
        issues.append({'category': 'Cleanliness', 'description': 'Guest mentioned cleanliness concerns', 'severity': 'high' if 'dirty' in review_lower else 'medium'})
    if 'broken' in review_lower or 'repair' in review_lower:
        issues.append({'category': 'Maintenance', 'description': 'Equipment or room maintenance issue', 'severity': 'high'})
    if 'noise' in review_lower:
        issues.append({'category': 'Noise', 'description': 'Noise complaint detected', 'severity': 'medium'})
    if 'rude' in review_lower or 'unfriendly' in review_lower:
        issues.append({'category': 'Staff Behavior', 'description': 'Staff attitude issue mentioned', 'severity': 'high'})

    highlights = []
    if 'friendly' in review_lower or 'helpful' in review_lower:
        highlights.append({'category': 'Staff Friendliness', 'description': 'Guest praised staff attitude'})
    if 'clean' in review_lower and 'dirty' not in review_lower:
        highlights.append({'category': 'Cleanliness', 'description': 'Guest appreciated room cleanliness'})
    if 'location' in review_lower and ('great' in review_lower or 'perfect' in review_lower):
        highlights.append({'category': 'Location', 'description': 'Guest loved the location'})

    recommendations = []
    if sentiment == 'negative':
        recommendations.append('Contact guest immediately for service recovery')
        recommendations.append('Assign compensation (points/discount) if appropriate')
        if issues:
            recommendations.append(f'Create maintenance task for {issues[0]["category"]}')
    elif sentiment == 'positive':
        recommendations.append('Thank guest and encourage loyalty program enrollment')
        recommendations.append('Share review on social media (with permission)')

    return {
        'sentiment': sentiment,
        'confidence': confidence,
        'issues': issues,
        'highlights': highlights,
        'recommendations': recommendations,
    }
# ── GET /tasks/kanban ──
@router.get("/tasks/kanban")
@cached(ttl=180, key_prefix="tasks_kanban")  # Cache for 3 min
async def get_tasks_kanban(current_user: User = Depends(get_current_user)):
    """
    Get tasks organized by kanban columns: new, in_progress, waiting_parts, completed
    """
    tasks = await db.tasks.find({
        'tenant_id': current_user.tenant_id
    }).to_list(1000)

    kanban = {
        'new': [],
        'in_progress': [],
        'waiting_parts': [],
        'completed': []
    }

    for task in tasks:
        status = task.get('status', 'new')
        kanban[status].append(task)

    return {'tasks': kanban}
# ── POST /tasks/move ──
@router.post("/tasks/move")
async def move_task(
    data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """
    Move task between kanban columns
    """
    task_id = data.get('task_id')
    to_status = data.get('to_status')

    await db.tasks.update_one(
        {
            'id': task_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {
                'status': to_status,
                'updated_at': datetime.now(UTC).isoformat()
            }
        }
    )

    return {'message': f'Task moved to {to_status}'}
