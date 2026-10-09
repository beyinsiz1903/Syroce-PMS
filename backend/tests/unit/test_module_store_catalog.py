from pathlib import Path

from core.marketplace_contracts import ROUTE_CONTRACTS, calculate_price
from routers.marketplace import DEFAULT_PRODUCTS, router


def test_professional_catalog_has_paid_operational_modules():
    products = {product["key"]: product for product in DEFAULT_PRODUCTS}
    expected = {
        "hr",
        "pos_fnb",
        "invoices",
        "revenue_management",
        "spa",
        "mice",
        "maintenance",
        "sales_crm",
        "contact_center",
        "academy",
        "booking_engine",
        "multi_property",
    }

    assert expected <= products.keys()
    for key in expected:
        product = products[key]
        assert product["billing_type"] == "subscription"
        assert product["price_try"] > 0
        assert product["route_path"].startswith("/")
        assert product["features"]
        assert product["features_en"]


def test_quote_request_endpoint_is_registered():
    paths = {route.path for route in router.routes}
    assert "/api/module-store/request-quote" in paths


def test_every_sellable_product_has_versioned_commercial_and_provisioning_contract():
    for product in DEFAULT_PRODUCTS:
        assert product["pricing_model"] in {"property", "room", "employee", "outlet", "user", "pack"}
        assert product["included_units"] >= 1
        assert product["unit_price_try"] >= 0
        assert 0 <= product["tax_rate_pct"] <= 100
        assert product["price_version"] >= 1
        assert product["price_source"]
        assert product["provisioning_strategy"] in {"native", "external", "credit"}
        assert isinstance(product["readiness_checks"], list)


def test_checkout_price_is_quantity_aware_and_tax_consistent():
    product = next(row for row in DEFAULT_PRODUCTS if row["key"] == "hr")
    quote = calculate_price(product, 26)
    assert quote == {
        "quantity": 26, "billable_units": 2, "subtotal_try": 2980.0,
        "tax_rate_pct": 20.0, "tax_try": 596.0, "total_try": 3576.0,
        "currency": "TRY", "price_version": 1,
    }


def test_catalog_routes_match_the_canonical_frontend_contract():
    products = {product["key"]: product for product in DEFAULT_PRODUCTS}
    for key, path in ROUTE_CONTRACTS.items():
        assert products[key]["route_path"] == path

    route_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).parents[3] / "frontend/src/routes/sections").glob("*.js")
    )
    for path in ROUTE_CONTRACTS.values():
        assert path.split("?", 1)[0] in route_sources


def test_marketplace_lifecycle_endpoints_are_registered():
    paths = {route.path for route in router.routes}
    assert {
        "/api/module-store/billing",
        "/api/module-store/subscriptions/{subscription_id}/cancel",
        "/api/module-store/subscriptions/{subscription_id}/readiness",
        "/api/module-store/orders/refund-request",
        "/api/module-store/payment-methods/{payment_method_id}",
        "/api/module-store/admin/products/{key}/price-history",
        "/api/module-store/admin/run-renewals",
    } <= paths
