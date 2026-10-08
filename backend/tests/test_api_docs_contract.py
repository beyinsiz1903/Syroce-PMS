"""Static contract checks that keep the in-product API guide honest.

These tests intentionally avoid MongoDB and application startup.  They compare
the external endpoint catalogue and scope list shown to integrators with the
FastAPI source that actually registers those routes.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
DOCS = (ROOT / "frontend/src/pages/B2BApiDocs.jsx").read_text(encoding="utf-8")
MARKETPLACE = (ROOT / "backend/routers/marketplace_b2b.py").read_text(encoding="utf-8")
CONTRACTS = (ROOT / "backend/routers/agency_contracts.py").read_text(encoding="utf-8")
SCOPE_SOURCE = (ROOT / "backend/routers/b2b_api/_scope.py").read_text(encoding="utf-8")
WEBHOOK_SOURCE = (ROOT / "backend/routers/b2b_api/webhooks.py").read_text(encoding="utf-8")
B2B_ROUTER_DIR = ROOT / "backend/routers/b2b_api"


def _route_exists(method: str, path: str) -> bool:
    decorator = rf'@(router|agency_router)\.{method.lower()}\("{re.escape(path)}"'
    return bool(re.search(decorator, MARKETPLACE + "\n" + CONTRACTS))


def test_marketplace_documented_endpoints_exist_in_backend():
    block = DOCS.split("const marketplaceEndpoints = [", 1)[1].split("];", 1)[0]
    documented = re.findall(r"\['(GET|POST|PUT|PATCH|DELETE)', '([^']+)'", block)
    assert documented, "Marketplace endpoint catalogue is empty"
    missing = [(method, path) for method, path in documented if not _route_exists(method, path)]
    assert missing == []


def test_hotel_scope_badges_match_backend_source_of_truth():
    scope_block = SCOPE_SOURCE.split("B2B_SCOPES = [", 1)[1].split("]", 1)[0]
    expected = set(re.findall(r'"([a-z_]+)"', scope_block))
    badge_block = DOCS.split("{['booking_engine'", 1)[1].split("].map(scope", 1)[0]
    shown = {"booking_engine", *re.findall(r"'([a-z_]+)'", badge_block)}
    assert shown == expected


def test_hotel_documented_endpoints_match_external_backend_routes():
    """Keep the integrator catalogue equal to the operational Hotel API."""
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in B2B_ROUTER_DIR.glob("*.py")
        if path.name not in {"api_keys.py", "connect_requests.py"}
    )
    backend_routes = {
        (method.upper(), path)
        for method, path in re.findall(
            r'@router\.(get|post|put|patch|delete)\("([^"]+)"', sources
        )
    }
    documented = {
        (method, path.removeprefix("/api/b2b"))
        for method, path in re.findall(
            r'<EndpointBlock method="(GET|POST|PUT|PATCH|DELETE)" path="(/api/b2b[^"]+)"',
            DOCS,
        )
    }
    assert documented == backend_routes


def test_docs_do_not_promise_unimplemented_rate_limit_contract():
    assert "X-RateLimit-Limit: 120" not in DOCS
    assert "X-RateLimit-Remaining: 115" not in DOCS
    assert "Maximum requests allowed in the window" not in DOCS


def test_hotel_docs_describe_required_scope_model():
    assert "scopes=booking_engine" in DOCS
    assert "19 API Groups" not in DOCS
    assert "Mevcut Moduller (19 API Grubu)" not in DOCS


def test_hotel_docs_list_every_supported_webhook_event():
    event_block = WEBHOOK_SOURCE.split("VALID_WEBHOOK_EVENTS = {", 1)[1].split("}", 1)[0]
    expected = set(re.findall(r'"([a-z.]+)"', event_block))
    missing = sorted(event for event in expected if event not in DOCS)
    assert missing == []


def test_pagination_docs_do_not_claim_a_universal_count_envelope():
    assert "All list responses include a count field" not in DOCS
    assert "Tüm liste yanitlari bir count alani icerir" not in DOCS
    table = DOCS.split("Client-supplied limits per endpoint", 1)[1].split("</table>", 1)[0]
    assert "'/housekeeping/rooms'" not in table
    assert "'/wake-up-calls'" not in table


def test_server_to_server_examples_do_not_send_browser_credentials():
    assert 'credentials: "include"' not in DOCS
