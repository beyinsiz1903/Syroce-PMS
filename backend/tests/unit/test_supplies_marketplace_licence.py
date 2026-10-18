"""The hotel supplies market is its own opt-in feature (hidden_marketplace),
not a channel-manager product."""

import inspect

import pytest

from core import entitlement

SUPPLIES = [
    "/api/marketplace/products", "/api/marketplace/inventory", "/api/marketplace/inventory/adjust",
    "/api/marketplace/purchase-orders", "/api/marketplace/purchase-orders/p1/approve",
    "/api/marketplace/suppliers", "/api/marketplace/deliveries", "/api/marketplace/warehouses",
    "/api/marketplace/stock-alerts", "/api/marketplace/orders",
]


@pytest.mark.parametrize("path", SUPPLIES)
def test_supplies_routes_are_not_tied_to_the_channel_manager(path):
    assert entitlement._match_route_module(path) is None


@pytest.mark.parametrize("path", ["/api/marketplace/v1/extranet/profile", "/api/marketplace/hotel/statements", "/api/marketplace/incoming-requests"])
def test_agency_extranet_routes_keep_their_module(path):
    assert entitlement._match_route_module(path) == "agency_extranet"


def test_every_supplies_route_requires_the_hidden_marketplace_feature():
    import server
    from domains.pms import enterprise_router, marketplace_router, supplies_orders_router

    expected = {
        (method, route.path)
        for router in (enterprise_router.router, marketplace_router.router, supplies_orders_router.router)
        for route in router.routes
        if route.path.startswith("/api/marketplace")
        for method in route.methods
    }

    unguarded = []
    checked = set()
    for route in server.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/marketplace") or entitlement._match_route_module(path) == "agency_extranet":
            continue
        checked.update((method, path) for method in route.methods)
        guards = [
            inspect.getclosurevars(dep.call).nonlocals
            for dep in route.dependant.dependencies
            if inspect.isfunction(dep.call)
        ]
        if not any(guard.get("feature_key") == "hidden_marketplace" for guard in guards):
            unguarded.append((sorted(route.methods), path))
        if path == "/api/marketplace/orders":
            assert all(guard.get("module_key") != "pos_fnb" for guard in guards)
            assert all(guard.get("normalized") != "pos" for guard in guards)
            assert sum(path == getattr(r, "path", "") and route.methods == getattr(r, "methods", None)
                       for r in server.app.routes) == 1
    # Fail if a router silently stops mounting instead of vacuously passing.
    assert checked == expected
    assert {("GET", "/api/marketplace/orders"), ("POST", "/api/marketplace/orders")} <= checked
    assert unguarded == []
