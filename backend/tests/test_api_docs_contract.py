"""Static contract checks that keep the in-product API guide honest.

These tests intentionally avoid MongoDB and application startup.  They compare
the external endpoint catalogue and scope list shown to integrators with the
FastAPI source that actually registers those routes.
"""

import ast
import re
import subprocess
import tempfile
from pathlib import Path

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


def _model_fields(source_name: str, class_name: str) -> set[str]:
    source = (B2B_ROUTER_DIR / source_name).read_text(encoding="utf-8")
    tree = ast.parse(source)
    model = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return {node.target.id for node in model.body if isinstance(node, ast.AnnAssign)}


def _documented_fields(method: str, path: str) -> set[str]:
    marker = f'<EndpointBlock method="{method}" path="{path}"'
    block = DOCS.split(marker, 1)[1].split("</EndpointBlock>", 1)[0]
    return set(re.findall(r"name: '([^']+)'", block))


def test_marketplace_documented_endpoints_exist_in_backend():
    block = DOCS.split("const marketplaceEndpoints = [", 1)[1].split("];", 1)[0]
    documented = re.findall(r"\['(GET|POST|PUT|PATCH|DELETE)', '([^']+)'", block)
    assert documented, "Marketplace endpoint catalogue is empty"
    missing = [(method, path) for method, path in documented if not _route_exists(method, path)]
    assert missing == []


def test_marketplace_endpoint_catalogue_has_english_descriptions():
    block = DOCS.split("const marketplaceEndpoints = [", 1)[1].split("];", 1)[0]
    rows = re.findall(
        r"\['(GET|POST|PUT|PATCH|DELETE)', '([^']+)', '([^']+)', '([^']+)'\]",
        block,
    )
    documented = re.findall(r"\['(GET|POST|PUT|PATCH|DELETE)', '([^']+)'", block)
    assert len(rows) == len(documented)
    assert all(english.strip() for _, _, _, english in rows)


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
    assert "Rate limit exceeded" not in DOCS
    assert "The same Idempotency-Key is still being processed" in DOCS


def test_hotel_status_table_matches_live_success_contract():
    status_table = DOCS.split("'HTTP Status Codes'", 1)[1].split("</table>", 1)[0]
    assert "code: '200'" in status_table
    assert "code: '201'" not in status_table


def test_core_hotel_response_examples_include_backend_fields():
    hotel_info = DOCS.split(
        '<EndpointBlock method="GET" path="/api/b2b/hotel-info"', 1
    )[1].split("</EndpointBlock>", 1)[0]
    assert all(
        field in hotel_info
        for field in ('"tenant_id"', '"hotel"', '"agency"', '"room_types"', '"content_published"')
    )

    rates = DOCS.split('<EndpointBlock method="GET" path="/api/b2b/rates"', 1)[1].split(
        "</EndpointBlock>", 1
    )[0]
    assert all(field in rates for field in ('"start_date"', '"end_date"', '"source"', '"rates"'))

    reservation = DOCS.split(
        '<EndpointBlock method="POST" path="/api/b2b/reservations"', 1
    )[1].split("</EndpointBlock>", 1)[0]
    assert all(
        field in reservation
        for field in (
            '"room_number"',
            '"total_amount"',
            '"commission_rate"',
            '"commission_amount"',
            '"created_at"',
            '"message"',
        )
    )


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


def test_documented_request_bodies_match_pydantic_models():
    contracts = {
        ("POST", "/api/b2b/reservations"): ("booking_engine.py", "B2BReservationCreate"),
        ("POST", "/api/b2b/guests/{guest_id}/loyalty/points"): ("guests.py", "LoyaltyPointsUpdate"),
        ("PUT", "/api/b2b/housekeeping/rooms/{room_id}"): ("housekeeping.py", "HousekeepingStatusUpdate"),
        ("POST", "/api/b2b/kbs/report"): ("kbs.py", "KBSReportCreate"),
        ("POST", "/api/b2b/identity/scan"): ("identity.py", "IdentityScanData"),
        ("POST", "/api/b2b/lost-found"): ("lost_found.py", "LostFoundCreate"),
        ("PUT", "/api/b2b/lost-found/{item_id}"): ("lost_found.py", "LostFoundUpdate"),
        ("POST", "/api/b2b/wake-up-calls"): ("wake_up.py", "WakeUpCallCreate"),
        ("PUT", "/api/b2b/wake-up-calls/{call_id}"): ("wake_up.py", "WakeUpCallUpdate"),
        ("POST", "/api/b2b/guest-journey/online-checkin"): ("guest_journey.py", "B2BOnlineCheckin"),
        ("POST", "/api/b2b/guest-journey/request"): ("guest_journey.py", "B2BGuestRequest"),
        ("POST", "/api/b2b/concierge/request"): ("services.py", "ConciergeRequest"),
        ("POST", "/api/b2b/spa/booking"): ("services.py", "SpaBookingCreate"),
        ("POST", "/api/b2b/groups/block"): ("groups.py", "GroupBlockCreate"),
        ("POST", "/api/b2b/folio/{booking_id}/charge"): ("folio.py", "FolioChargeCreate"),
        ("POST", "/api/b2b/webhooks"): ("webhooks.py", "WebhookRegister"),
    }
    mismatches = {}
    for endpoint, (source_name, class_name) in contracts.items():
        expected = _model_fields(source_name, class_name)
        shown = _documented_fields(*endpoint)
        if shown != expected:
            mismatches[endpoint] = {"missing": sorted(expected - shown), "extra": sorted(shown - expected)}
    assert mismatches == {}


def test_nested_rooming_list_schema_is_complete():
    shown = _documented_fields("POST", "/api/b2b/groups/{block_id}/rooming-list")
    entry_fields = _model_fields("groups.py", "RoomingListEntry")
    expected = {"guests", *(f"guests[].{field}" for field in entry_fields)}
    assert shown == expected


def test_documented_query_parameters_match_route_contracts():
    contracts = {
        ("GET", "/api/b2b/availability"): {"check_in", "check_out", "room_type"},
        ("GET", "/api/b2b/rates"): {"start_date", "end_date", "room_type"},
        ("GET", "/api/b2b/reservations"): {"status", "check_in_from", "check_in_to", "limit"},
        ("GET", "/api/b2b/guests/search"): {"q", "limit"},
        ("GET", "/api/b2b/guests/{guest_id}/stays"): {"limit"},
        ("GET", "/api/b2b/housekeeping/rooms"): {"status", "floor"},
        ("GET", "/api/b2b/kbs/guests"): {"date", "status", "limit"},
        ("GET", "/api/b2b/lost-found"): {"status", "category", "limit"},
        ("GET", "/api/b2b/wake-up-calls"): {"date", "status"},
        ("GET", "/api/b2b/guest-journey/requests"): {"booking_id", "status", "request_type", "limit"},
        ("GET", "/api/b2b/groups"): {"status", "limit"},
    }
    mismatches = {
        endpoint: {"missing": sorted(expected - _documented_fields(*endpoint)), "extra": sorted(_documented_fields(*endpoint) - expected)}
        for endpoint, expected in contracts.items()
        if _documented_fields(*endpoint) != expected
    }
    assert mismatches == {}


def test_documentation_code_examples_are_syntax_valid():
    python_examples = re.findall(
        r'<CodeBlock lang="python" code={`(.*?)`} />', DOCS, flags=re.DOTALL
    )
    assert python_examples
    for example in python_examples:
        ast.parse(example.replace(r"\n", "\n").replace(r"\'", "'"))

    javascript_examples = re.findall(
        r'<CodeBlock lang="javascript" code={`(.*?)`} />', DOCS, flags=re.DOTALL
    )
    assert javascript_examples
    for example in javascript_examples:
        # Template interpolation belongs to the rendered example. Replace it
        # only for the parser; runtime credentials remain intentionally absent.
        source = (
            example.replace(r"\n", "\n")
            .replace(r"\`", "`")
            .replace(r"\${", "${")
        )
        with tempfile.NamedTemporaryFile(suffix=".mjs", mode="w", encoding="utf-8") as handle:
            handle.write(source)
            handle.flush()
            result = subprocess.run(
                ["node", "--check", handle.name], capture_output=True, text=True, check=False
            )
        assert result.returncode == 0, result.stderr


def test_webhook_test_and_production_delivery_are_not_conflated():
    source = WEBHOOK_SOURCE
    retry_source = (ROOT / "backend/routers/webhook_retry_service.py").read_text(
        encoding="utf-8"
    )
    assert '"X-Idempotency-Key": idempotency_key' in retry_source
    test_route = source.split("async def b2b_test_webhook", 1)[1]
    assert '"X-Webhook-Delivery": delivery_id' in test_route
    assert "X-Idempotency-Key" not in test_route
    assert "one synchronous delivery" in DOCS
    assert "does not retry" in DOCS


def test_versioning_policy_defines_breaking_and_additive_changes():
    assert "clients must ignore unknown response fields" in DOCS
    assert "requires a new versioned base path" in DOCS
    assert "credentials and scopes are never broadened automatically" in DOCS


def test_turkish_documentation_headings_use_turkish_characters():
    stale = (
        "Yanit",
        "Ornek",
        "Kullanim",
        "Icerik API",
        "Musaitlik API",
        "Baslangic",
    )
    assert [token for token in stale if token in DOCS] == []
