import os
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-with-at-least-32-characters")

from domains.pms.approvals_router import router as pms_approvals_router
from domains.revenue.analytics_router.approvals import can_manage_approvals


def _matching_routes(path: str, method: str):
    return [route for route in pms_approvals_router.routes if route.path == path and method in route.methods]


def test_pms_approval_mutations_have_one_handler_each():
    assert len(_matching_routes("/api/approvals/{approval_id}/approve", "PUT")) == 1
    assert len(_matching_routes("/api/approvals/{approval_id}/reject", "PUT")) == 1
    assert not _matching_routes("/api/approvals/pending", "GET")
    assert not _matching_routes("/api/approvals/my-requests", "GET")


def test_approval_manager_roles_include_primary_and_secondary_roles():
    assert can_manage_approvals(SimpleNamespace(role="finance_manager", roles=[]))
    assert can_manage_approvals(SimpleNamespace(role="staff", roles=["supervisor"]))
    assert not can_manage_approvals(SimpleNamespace(role="staff", roles=[]))
