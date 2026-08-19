import asyncio

import pytest
from fastapi import HTTPException

from bootstrap import router_registry


def _dependency_for(module_path: str):
    dependencies = router_registry._router_dependencies(module_path, None)
    assert len(dependencies) == 1
    return dependencies[0].dependency


def test_dedicated_router_gets_module_scope_dependency():
    dependency = _dependency_for("routers.procurement")

    allowed = asyncio.run(
        dependency(
            current_user={
                "role": "staff",
                "module_scopes": ["procurement"],
            }
        )
    )
    assert allowed["module_scopes"] == ["procurement"]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            dependency(
                current_user={
                    "role": "staff",
                    "module_scopes": ["stock"],
                }
            )
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "MODULE_ACCESS_DENIED"


def test_provider_and_public_webhook_routers_are_not_user_scope_wrapped():
    assert router_registry._router_dependencies(
        "domains.channel_manager.providers.hotelrunner_webhook", None
    ) == []
    assert router_registry._router_dependencies(
        "domains.channel_manager.providers.exely.exely_webhook_router", None
    ) == []
    assert router_registry._router_dependencies(
        "domains.contact_center.voice_router", None
    ) == []


def test_declared_dependencies_are_preserved_when_module_scope_is_added():
    marker = object()
    dependencies = router_registry._router_dependencies(
        "domains.pms.maintenance_router", [marker]
    )
    assert dependencies[0] is marker
    assert len(dependencies) == 2


def test_expected_qa_modules_have_backend_router_or_endpoint_enforcement():
    router_scopes = set(router_registry.ROUTER_MODULE_SCOPES.values())
    # `tasks` and `stock` live in mixed legacy routers and are intentionally
    # enforced at endpoint level instead of wrapping the entire router.
    assert {
        "cashier",
        "channel_manager",
        "finance",
        "frontdesk",
        "housekeeping",
        "hr",
        "maintenance",
        "pos",
        "procurement",
        "reports",
        "sales",
    }.issubset(router_scopes)
