import asyncio
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Ensure TESTING=1 so rate limiter uses relaxed limits during test runs
os.environ.setdefault("TESTING", "1")

# Mongo: tests run outside start.sh so MONGO_URL may be unset.
# Fallback to MONGO_ATLAS_URI (the same source start.sh uses).
if not os.environ.get("MONGO_URL"):
    _atlas = os.environ.get("MONGO_ATLAS_URI")
    if _atlas:
        os.environ["MONGO_URL"] = _atlas
        os.environ.setdefault("DB_NAME", "syroce-pms")


# ── Quarantine Auto-Skip Hook (ADR-002) ──────────────────────────────────
# Loads the quarantine manifest and auto-skips listed tests at collection time.
# This keeps failing tests visible in output (as "skipped") without blocking CI.
def pytest_collection_modifyitems(config, items):
    try:
        from tests._quarantine.quarantine_manifest import QUARANTINED_TESTS
    except ImportError:
        QUARANTINED_TESTS = {}

    try:
        from tests.live_server_manifest import LIVE_SERVER_TESTS
    except ImportError:
        LIVE_SERVER_TESTS = set()

    for item in items:
        node_id = item.nodeid

        # Apply quarantine skips
        for q_id, reason in QUARANTINED_TESTS.items():
            if q_id in node_id:
                item.add_marker(pytest.mark.skip(reason=reason))
                break

        # Apply live_server marker
        try:
            rel_path = str(item.path.relative_to(item.config.rootpath)).replace("\\\\", "/")
        except ValueError:
            rel_path = str(item.path).replace("\\\\", "/")

        if rel_path in LIVE_SERVER_TESTS:
            item.add_marker(pytest.mark.live_server)

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")


# Ensure VITE_BACKEND_URL is set for test files that read it directly.
# Backend listens on 8000 (start.sh:69 → uvicorn --port 8000).
if not os.environ.get("VITE_BACKEND_URL"):
    os.environ["VITE_BACKEND_URL"] = "http://localhost:8000"
    BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def demo_auth_token():
    """Shared demo admin auth token for all tests."""
    if not BASE_URL:
        pytest.skip("VITE_BACKEND_URL not set")
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        headers={"Origin": BASE_URL},
    )
    if resp.status_code != 200:
        pytest.skip("Authentication failed for demo@hotel.com")
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def demo_auth_headers(demo_auth_token):
    """Shared auth headers dict."""
    return {"Authorization": f"Bearer {demo_auth_token}", "Content-Type": "application/json"}


def _bind_test_database(database_module, raw_db):
    """Bind a test DB while preserving the global proxy object's identity."""
    from core.tenant_db import TenantAwareDBProxy

    current_db = database_module.db

    if isinstance(current_db, TenantAwareDBProxy):
        previous_proxy_target = object.__getattribute__(current_db, "_db")
        object.__setattr__(current_db, "_db", raw_db)
        return current_db, previous_proxy_target

    previous_proxy_target = None
    database_module.db = TenantAwareDBProxy(raw_db)
    return current_db, previous_proxy_target


def _restore_test_database(
    database_module,
    *,
    previous_db,
    active_db,
    previous_proxy_target,
):
    from core.tenant_db import TenantAwareDBProxy

    if (
        isinstance(active_db, TenantAwareDBProxy)
        and previous_proxy_target is not None
    ):
        object.__setattr__(active_db, "_db", previous_proxy_target)
        database_module.db = active_db
    else:
        database_module.db = previous_db


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session.
    This is required because Motor client binds to the event loop at import time.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Re-initialize motor client on this loop
    import os

    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient

    from core import database
    load_dotenv(BACKEND_ROOT / '.env')
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/hotel_pms')
    db_name = os.environ.get('DB_NAME', 'hotel_pms')

    previous_client = database.client
    previous_raw_db = getattr(database, "_raw_db", None)
    previous_db = database.db

    client = AsyncIOMotorClient(mongo_url)
    raw_db = client[db_name]

    database.client = client
    database._raw_db = raw_db

    active_db, previous_proxy_target = _bind_test_database(
        database,
        raw_db,
    )

    try:
        yield loop
    finally:
        client.close()
        database.client = previous_client
        database._raw_db = previous_raw_db
        _restore_test_database(
            database,
            previous_db=previous_db,
            active_db=active_db,
            previous_proxy_target=previous_proxy_target,
        )
        asyncio.set_event_loop(None)
        loop.close()


# ── live_mongo no-false-green gate (Task #323) ───────────────────────────
# Doctrine gereği `live_mongo` testleri gerçek MongoDB erişilemezse atlanır.
# Bu, CI'da Mongo bağlanamazsa tüm canlı testlerin "skip" olup build'in yine
# yeşil görünmesine (false-green) yol açar. REQUIRE_LIVE_MONGO=1 set edildiğinde
# (CI'da adanmış adım), `live_mongo` testlerinden HERHANGİ biri atlanırsa veya
# hiç koşmazsa oturum FAIL olur. Yerelde (env yoksa) skip serbesttir.
_LIVE_MONGO_OUTCOMES = {"passed": 0, "failed": 0, "skipped": 0}


def _require_live_mongo() -> bool:
    return os.environ.get("REQUIRE_LIVE_MONGO", "").strip().lower() in ("1", "true", "yes")


def pytest_runtest_logreport(report):
    # Yalnız live_mongo marker'lı testleri say. Skip fixture/setup'ta olur
    # (report.when == "setup"); pass/fail call fazında raporlanır.
    if "live_mongo" not in getattr(report, "keywords", {}):
        return
    if report.skipped and report.when in ("setup", "call"):
        _LIVE_MONGO_OUTCOMES["skipped"] += 1
    elif report.when == "call":
        if report.passed:
            _LIVE_MONGO_OUTCOMES["passed"] += 1
        elif report.failed:
            _LIVE_MONGO_OUTCOMES["failed"] += 1


def pytest_sessionfinish(session, exitstatus):
    if not _require_live_mongo():
        return
    o = _LIVE_MONGO_OUTCOMES
    ran = o["passed"] + o["failed"]
    if o["skipped"] > 0 or ran == 0:
        msg = (
            f"REQUIRE_LIVE_MONGO set ama live_mongo testleri gerçekten koşmadı "
            f"(passed={o['passed']} failed={o['failed']} skipped={o['skipped']}). "
            f"Skip-as-pass reddedildi (false-green guard)."
        )
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line("")
            reporter.write_line(msg, red=True, bold=True)
        # Oturumu kırmızıya çevir (exit kodu != 0).
        session.exitstatus = 1
