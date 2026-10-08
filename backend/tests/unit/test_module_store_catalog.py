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
