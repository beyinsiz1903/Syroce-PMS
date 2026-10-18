"""The hotel supplies market is its own opt-in feature (hidden_marketplace),
not a channel-manager product."""

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

    unguarded = []
    for route in server.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/marketplace") or entitlement._match_route_module(path) == "agency_extranet":
            continue
        guards = [getattr(dep.call, "__qualname__", "") for dep in route.dependant.dependencies]
        if not any(name.startswith("require_feature.") for name in guards):
            unguarded.append((sorted(route.methods), path))
    assert unguarded == []
