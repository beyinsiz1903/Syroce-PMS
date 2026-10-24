"""Tenant-scoped enterprise billing controls; no external payment calls."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core import enterprise_billing as service
from modules.pms_core import security_funds
from modules.pms_core.role_permission_service import RolePermissionService, require_op

router = APIRouter(prefix="/api/enterprise-billing", tags=["PMS / Enterprise Billing"])
logger = logging.getLogger(__name__)


async def _refresh_after_commit(tenant_id, booking_id):
    # A projection/cache failure must not misrepresent a committed financial
    # result as a failed action. Durable operation keys still protect replay.
    from core.booking_payment_state import refresh_booking_payment_state
    from core.report_cache import invalidate_financial_report_caches

    try:
        await refresh_booking_payment_state(db, tenant_id, booking_id)
    except Exception:
        logger.warning("Enterprise billing payment projection refresh failed after commit")
    try:
        invalidate_financial_report_caches(tenant_id)
    except Exception:
        logger.warning("Enterprise billing cache invalidation failed after commit")


async def hotel_user(user: User = Depends(get_current_user)):
    _ensure_hotel_context(user)
    return user


async def _transaction(user, booking_id, callback):
    from core.booking_atomicity import is_replica_set_unavailable, with_resource_locks
    from core.database import client

    try:
        return await with_resource_locks(client=client, db=db, tenant_id=user.tenant_id,
            locks_collection="reservation_financial_locks", resources=sorted({("booking", booking_id), ("booking", "billing-policy")}), callback=callback)
    except Exception as exc:
        if is_replica_set_unavailable(exc):
            raise HTTPException(503, "Finansal işlem için Mongo transaction desteği gerekli") from exc
        raise


@router.get("/catalog")
async def catalog(user: User = Depends(hotel_user), _perm=Depends(require_op("view_folio"))):
    return await service.payment_catalog(db, user.tenant_id)


@router.get("/policy")
async def get_policy(user: User = Depends(hotel_user), _perm=Depends(require_op("view_folio"))):
    permissions = RolePermissionService()
    return {"actor_id": user.id, "concession_mode": "direct", "reason_required": True, "can_approve": False,
            "can_apply": all(permissions.check_permission(user.role, op, getattr(user, "granted_permissions", None))
                             for op in ["post_charge", "override_rate"])}


@router.put("/policy")
async def set_policy(body: service.BillingPolicy, user: User = Depends(hotel_user),
                     _perm=Depends(require_op("manage_approvals"))):
    raise HTTPException(410, "Ayrı ikram onayı ve onay limiti kaldırıldı; yetkili kullanıcı zorunlu açıklamayla doğrudan uygular")


@router.get("/concessions")
async def concessions(booking_id: str, user: User = Depends(hotel_user), _perm=Depends(require_op("view_folio"))):
    # The UI derives remaining per-service concession capacity from all applied
    # decisions. Never silently truncate that history and overstate capacity.
    rows = await db.billing_concessions.find({"tenant_id": user.tenant_id, "booking_id": booking_id}).sort("created_at", -1).to_list(None)
    return {"items": [service.public_concession(row) for row in rows]}


@router.post("/concessions", status_code=201)
async def request_concession(body: service.ConcessionRequest, user: User = Depends(hotel_user),
                             _perm=Depends(require_op("post_charge")), _finance=Depends(require_op("override_rate"))):
    async def commit(session):
        return await service.request_concession(db, user.tenant_id, user.id, body, session=session,
            actor_name=user.name, actor_role=user.role)

    result = await _transaction(user, body.booking_id, commit)
    await _refresh_after_commit(user.tenant_id, body.booking_id)
    return result


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    approve: bool
    reason: str | None = Field(default=None, min_length=3, max_length=500)


class ApplyConcession(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=500)


@router.post("/concessions/{request_id}/apply")
async def apply_concession(request_id: UUID, body: ApplyConcession, user: User = Depends(hotel_user),
                           _perm=Depends(require_op("post_charge")), _finance=Depends(require_op("override_rate"))):
    return await decision(request_id, Decision(approve=True, reason=body.reason), user)


@router.post("/concessions/{request_id}/decision")
async def decision(request_id: UUID, body: Decision, user: User = Depends(hotel_user),
                   _perm=Depends(require_op("post_charge")), _finance=Depends(require_op("override_rate"))):
    row = await db.billing_concessions.find_one({"_id": f"concession:{user.tenant_id}:{request_id}", "tenant_id": user.tenant_id})
    if not row:
        raise HTTPException(404, "İkram talebi bulunamadı")

    async def commit(session):
        return await service.decide_concession(db, user.tenant_id, user.id, request_id, body.approve, session=session,
            reason=body.reason, actor_name=user.name, actor_role=user.role)

    result = await _transaction(user, row["booking_id"], commit)
    await _refresh_after_commit(user.tenant_id, row["booking_id"])
    return result


@router.get("/security-funds")
async def list_security_funds(booking_id: str, user: User = Depends(hotel_user), _perm=Depends(require_op("view_folio"))):
    rows = await db.security_funds.find({"tenant_id": user.tenant_id, "booking_id": booking_id}, {"_id": 0}).to_list(None)
    return {"items": rows, "basis": "refundable_liability_not_folio_payment"}


@router.post("/security-funds", status_code=201)
async def receive_security_fund(body: security_funds.Receipt, user: User = Depends(hotel_user),
                                _perm=Depends(require_op("post_payment"))):
    from domains.pms.cashier_service import record_cash_transaction

    async def commit(session):
        return await security_funds.receive(db, user.tenant_id, user.id, body, session=session, record_cash=record_cash_transaction)

    return await _transaction(user, body.booking_id, commit)


@router.post("/security-funds/{fund_id}/movements")
async def move_security_fund(fund_id: UUID, body: security_funds.Movement, user: User = Depends(hotel_user),
                             _perm=Depends(require_op("post_payment"))):
    from domains.pms.cashier_service import record_cash_transaction

    fund = await db.security_funds.find_one({"_id": f"security-fund:{user.tenant_id}:{fund_id}", "tenant_id": user.tenant_id})
    if not fund:
        raise HTTPException(404, "Güvence kaydı bulunamadı")

    async def commit(session):
        return await security_funds.move(db, user.tenant_id, user.id, fund_id, body, session=session, record_cash=record_cash_transaction)

    result = await _transaction(user, fund["booking_id"], commit)
    await _refresh_after_commit(user.tenant_id, fund["booking_id"])
    return result
