"""F8 § 98 (Wave 3) — Marketplace lifecycle: deployed routes + the one
feature-flag-gated write surface.

Accurate contract (verified against backend/domains/pms/marketplace_router.py):
  - The marketplace inventory/PO/supplier routes ARE registered (deployed);
    most are gated by RBAC (require_op / role guards), NOT by a feature flag.
  - Only `POST /api/marketplace/purchase-orders` is additionally gated behind
    the `hidden_marketplace` feature flag (intentionally-undeployed write
    surface for tenants that have not opted in).

The marketplace deep-lifecycle stress spec's P2 "module-blocked" for the
stress tenant therefore reflects RBAC/feature gating on a *deployed* surface,
not a missing endpoint. These tests lock both facts.
"""

from domains.pms.marketplace_router import router as marketplace_router


def _routes():
    return list(marketplace_router.routes)


def _paths():
    return {getattr(r, "path", "") for r in _routes()}


def _has_hidden_marketplace_gate(route) -> bool:
    """True if any dependency closure references the hidden_marketplace flag."""
    for d in route.dependant.dependencies:
        closure = getattr(d.call, "__closure__", None) or ()
        for cell in closure:
            try:
                if cell.cell_contents == "hidden_marketplace":
                    return True
            except (ValueError, AttributeError):
                continue
    return False


def test_marketplace_core_routes_registered():
    paths = _paths()
    for p in (
        "/api/marketplace/inventory",
        "/api/marketplace/purchase-orders",
        "/api/marketplace/purchase-orders/{po_id}/approve",
        "/api/marketplace/purchase-orders/{po_id}/receive",
        "/api/marketplace/suppliers",
    ):
        assert p in paths, f"expected marketplace route missing: {p}"


def test_post_purchase_orders_is_feature_flag_gated():
    gated = [
        r for r in _routes()
        if getattr(r, "path", "") == "/api/marketplace/purchase-orders"
        and "POST" in getattr(r, "methods", set())
    ]
    assert gated, "POST /api/marketplace/purchase-orders not found"
    assert _has_hidden_marketplace_gate(gated[0]), (
        "POST purchase-orders must be gated behind hidden_marketplace feature flag"
    )
