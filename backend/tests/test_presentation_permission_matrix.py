"""Explicit existing front-office, POS, SPA and report policy for every role."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.spa_mice_authz import require_catalog, require_finance, require_spa_ops
from models.enums import UserRole
from modules.pms_core.role_permission_service import RolePermissionService, require_module_role, require_op

MANAGERS = {'admin', 'super_admin', 'supervisor'}
ADMINS = {'admin', 'super_admin'}
OPERATIONS = {
    'create_booking': MANAGERS | {'front_desk', 'sales'},
    'checkin': MANAGERS | {'front_desk'},
    'checkout': MANAGERS | {'front_desk'},
    'room_move': MANAGERS | {'front_desk'},
    'post_charge': MANAGERS | {'front_desk', 'finance'},
    'post_payment': MANAGERS | {'front_desk', 'finance'},
    'void_charge': ADMINS | {'finance'},
    'split_folio': ADMINS,
    'view_reports': MANAGERS | {'front_desk', 'finance', 'sales', 'procurement'},
    'view_finance_reports': MANAGERS | {'finance'},
    'manage_pos_settings': ADMINS,
}


@pytest.mark.parametrize('role', list(UserRole))
@pytest.mark.parametrize('operation,allowed', list(OPERATIONS.items()))
async def test_all_roles_on_financial_operational_and_report_dependencies(role, operation, allowed):
    actor = SimpleNamespace(role=role, tenant_id='hotel-a', id='operator', is_super_admin=False, granted_permissions=[])
    permitted = role.value in allowed
    assert RolePermissionService().check_permission(role, operation) is permitted
    if permitted:
        await require_op(operation)(actor)
    else:
        with pytest.raises(HTTPException) as error:
            await require_op(operation)(actor)
        assert error.value.status_code == 403


@pytest.mark.parametrize('role', list(UserRole))
async def test_pos_module_role_boundary(role):
    actor = SimpleNamespace(role=role, is_super_admin=False, roles=[])
    if role.value in MANAGERS | {'front_desk'}:
        await require_module_role('pos')(actor)
    else:
        with pytest.raises(HTTPException) as error:
            await require_module_role('pos')(actor)
        assert error.value.status_code == 403


@pytest.mark.parametrize('role', list(UserRole))
@pytest.mark.parametrize('guard,allowed', [
    (require_catalog, MANAGERS), (require_spa_ops, MANAGERS | {'front_desk', 'staff'}),
    (require_finance, MANAGERS | {'front_desk', 'finance'}),
])
def test_spa_catalog_scheduling_and_folio_posting_are_distinct(role, guard, allowed):
    actor = SimpleNamespace(role=role, is_super_admin=False, roles=[])
    if role.value in allowed:
        guard(actor)
    else:
        with pytest.raises(HTTPException) as error:
            guard(actor)
        assert error.value.status_code == 403


async def test_individual_grant_is_used_by_actual_dependency_but_does_not_grant_unrelated_operations():
    actor = SimpleNamespace(role='front_desk', tenant_id='hotel-a', id='cashier', is_super_admin=False,
        granted_permissions=['transfer_folio'])
    await require_op('split_folio')(actor)
    with pytest.raises(HTTPException):
        await require_op('void_charge')(actor)


@pytest.mark.parametrize('role', ['unknown_role', '', 'guest', 'agency_agent', 'housekeeping'])
async def test_unauthorized_role_never_gains_access_on_unknown_operation(role):
    actor = SimpleNamespace(role=role, is_super_admin=False, roles=[], granted_permissions=[])
    with pytest.raises(HTTPException) as error:
        await require_op('unknown_financial_operation')(actor)
    assert error.value.status_code == 403
