from inspect import signature
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.security import get_current_user
from routers.report_builder import get_builder_config, router


def _allow_report_permission(app: FastAPI) -> None:
    for route in router.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for dependency in dependant.dependencies:
            if dependency.name == "_perm":
                app.dependency_overrides[dependency.call] = lambda: None


def test_report_builder_config_accepts_cookie_style_auth_dependency() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="test-user",
        tenant_id="test-tenant",
    )
    _allow_report_permission(app)

    response = TestClient(app).get("/api/reports/builder/config")

    assert response.status_code == 200
    assert set(response.json()["data_sources"]) == {
        "reservations",
        "revenue",
        "guests",
        "rooms",
        "housekeeping",
        "folios",
    }


def test_report_builder_endpoints_do_not_require_a_second_bearer_dependency() -> None:
    endpoint_names = {
        "get_builder_config",
        "generate_report",
        "export_report_excel",
        "export_report_pdf",
        "list_templates",
        "save_template",
        "delete_template",
    }

    for route in router.routes:
        endpoint = getattr(route, "endpoint", None)
        if getattr(endpoint, "__name__", "") not in endpoint_names:
            continue
        parameters = signature(endpoint).parameters
        assert "current_user" in parameters
        assert parameters["current_user"].default.dependency is get_current_user
        assert "credentials" not in parameters

    assert signature(get_builder_config).parameters["current_user"].default.dependency is get_current_user
