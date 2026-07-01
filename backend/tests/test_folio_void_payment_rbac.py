"""Wave 9 — Finance folio void_payment RBAC contract.

The legacy finance void-payment route (`POST /api/.../folio/{folio_id}/payment/
{payment_id}/void`) previously gated on `post_payment` (POST_PAYMENT), which let
any role that can *post* a payment also *void* one. The hardening route
(`pms_hardening.py`) already required the dedicated `void_payment` (VOID_CHARGE)
op. This locks the finance route to the same, stricter contract.

Doctrine: this is an RBAC *tightening*; no role gains access. FRONT_DESK keeps
post_payment but must NOT be able to void; FINANCE/ADMIN (VOID_CHARGE) may.
"""

import inspect

import pytest
from fastapi import HTTPException

from models.enums import UserRole
from modules.pms_core.role_permission_service import RolePermissionService


svc = RolePermissionService()


# ── service-level contract ────────────────────────────────────────────

def test_front_desk_can_post_but_not_void_payment():
    assert svc.check_permission(UserRole.FRONT_DESK.value, "post_payment") is True
    assert svc.check_permission(UserRole.FRONT_DESK.value, "void_payment") is False


def test_finance_and_admin_can_void_payment():
    assert svc.check_permission(UserRole.FINANCE.value, "void_payment") is True
    assert svc.check_permission(UserRole.ADMIN.value, "void_payment") is True


def test_housekeeping_cannot_void_payment():
    assert svc.check_permission(UserRole.HOUSEKEEPING.value, "void_payment") is False


# ── route enforces void_payment (behavioral, no DB needed: guard is first) ──

@pytest.mark.asyncio
async def test_void_payment_route_blocks_post_only_role():
    from routers.finance.folio import void_payment

    front_desk = type("U", (), {"role": UserRole.FRONT_DESK.value, "tenant_id": "t1"})()
    with pytest.raises(HTTPException) as exc:
        await void_payment(
            folio_id="f1", payment_id="p1", body={"reason": "x"}, current_user=front_desk
        )
    assert exc.value.status_code == 403


def test_void_payment_route_source_uses_void_permission():
    """Source-contract guard: the route must enforce the `void_payment` op,
    not `post_payment`, so a refactor can't silently re-loosen it."""
    from routers.finance.folio import void_payment

    src = inspect.getsource(void_payment)
    assert 'enforce_permission(current_user.role, "void_payment")' in src
    assert 'enforce_permission(current_user.role, "post_payment")' not in src
