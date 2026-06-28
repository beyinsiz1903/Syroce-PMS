"""
Pilot Read-Only Fixtures — F8M v2 § 41B + F9C § 98 sample-gap closer
=====================================================================
Idempotently ensures the pilot tenant carries one `room_blocks` doc,
one `kbs_reports` doc, and one sales lead so cross-tenant IDOR specs
exercise real pilot ids instead of falling back to BOGUS_UUID
(pure existence-deny):

- F8M v2 § 41B B2B IDOR matrix (groups, kbs rows)
  → `frontend/e2e-stress/specs/41B-b2b-subrouter-matrix.spec.js`
- F9C § 98 Sales lifecycle step J (cross-tenant PUT
  /api/sales/leads/{id}/stage)
  → `frontend/e2e-stress/specs/98-sales-basic-lifecycle.spec.js`

Fail-closed gates:
- super_admin role required (require_super_admin_guard)
- request `pilot_tenant_id` must equal env `PILOT_TENANT_ID`
  (refuses to seed any other tenant)
- inserts are read-only fixtures (tagged `pilot_fixture=True`,
  `_kind=fixture` for blocks/kbs; sales lead keeps the real
  `_kind="lead"` so it appears in `/api/sales/leads` listings —
  but carries `pilot_fixture=True` + a non-`E2E_` company name so
  `backend/scripts/cleanup_e2e_pilot_residue.py` ignores it)
  no booking flow, no external calls, no PII

Endpoint:
- POST /api/admin/pilot-fixtures/ensure
    body: { pilot_tenant_id: str }
    returns: {
        block_id, kbs_report_id, sales_lead_id, payroll_run_id,
        agency_id, created: {...}
    }

Wave 7 (2026-05-30): added `_ensure_payroll_run` so the export-artifact
IDOR spec (91) harvests a real pilot payroll-run id instead of a bogus
UUID. status="fixture" → never collides with the draft partial-unique
index and never looks like a finalized run.

Idempotency: a stable tagged doc is searched first; only created when
missing. Re-running the endpoint always returns the same ids.
"""

import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.helpers import require_super_admin_guard
from models.schemas import User

logger = logging.getLogger("admin.pilot_fixtures")

router = APIRouter(prefix="/api", tags=["Admin / Operations"])
require_super_admin = require_super_admin_guard()

FIXTURE_AGENCY_ID = "pilot_fixture_agency"

# Stable marker for the F9C § 98 sales-lead IDOR fixture. Picked to be
# unmistakable and NOT to start with `E2E_` so the residue cleanup
# script (`backend/scripts/cleanup_e2e_pilot_residue.py`) leaves it
# alone across runs.
SALES_LEAD_COMPANY = "IDOR_PROBE_SEED"
SALES_LEAD_CONTACT = "pilot.fixture.sales"
SALES_LEAD_EMAIL = "pilot.fixture.sales@fixture.local"

# Wave 7: export-artifact IDOR spec (91) harvests pilot payroll-run ids via
# GET /api/hr/payroll/runs then probes cross-tenant export.xlsx with the
# stress token (expects 403/404 deny). Without a real pilot run the harvest
# falls back to a bogus UUID (pure existence-deny, weaker assertion). The
# fixture period is far-future so it never overlaps a real pilot payroll.
PAYROLL_FIXTURE_PERIOD = "2099-01"


class PilotFixturesRequest(BaseModel):
    pilot_tenant_id: str


def _pilot_tid() -> str:
    tid = os.environ.get("PILOT_TENANT_ID", "").strip()
    if not tid:
        raise HTTPException(
            status_code=412,
            detail="PILOT_TENANT_ID env var not configured",
        )
    return tid


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _ensure_room_block(pilot_tid: str) -> tuple[str, bool]:
    existing = await db.room_blocks.find_one(
        {"tenant_id": pilot_tid, "pilot_fixture": True},
        {"id": 1, "_id": 0},
    )
    if existing and existing.get("id"):
        return existing["id"], False
    block_id = str(uuid.uuid4())
    await db.room_blocks.insert_one(
        {
            "id": block_id,
            "tenant_id": pilot_tid,
            "agency_id": FIXTURE_AGENCY_ID,
            "group_name": "PILOT_FIXTURE_BLOCK",
            "contact_name": "pilot.fixture",
            "contact_email": "",
            "contact_phone": "",
            "check_in": "2099-01-01",
            "check_out": "2099-01-02",
            "rooms_requested": 0,
            "room_type": "",
            "event_type": "fixture",
            "estimated_revenue": 0,
            "notes": "Read-only fixture for B2B IDOR matrix spec (41B). Do not mutate.",
            "status": "fixture",
            "pilot_fixture": True,
            "_kind": "fixture",
            "created_at": _now_iso(),
        }
    )
    return block_id, True


async def _ensure_kbs_report(pilot_tid: str) -> tuple[str, bool]:
    existing = await db.kbs_reports.find_one(
        {"tenant_id": pilot_tid, "pilot_fixture": True},
        {"id": 1, "_id": 0},
    )
    if existing and existing.get("id"):
        return existing["id"], False
    report_id = str(uuid.uuid4())
    await db.kbs_reports.insert_one(
        {
            "id": report_id,
            "tenant_id": pilot_tid,
            "agency_id": FIXTURE_AGENCY_ID,
            "date": "2099-01-01",
            "status": "fixture",
            "guest_count": 0,
            "guest_ids": [],
            "notes": "Read-only fixture for B2B IDOR matrix spec (41B). Do not mutate.",
            "submitted_by": "pilot_fixture",
            "pilot_fixture": True,
            "_kind": "fixture",
            "created_at": _now_iso(),
        }
    )
    return report_id, True


async def _ensure_sales_lead(pilot_tid: str) -> tuple[str, bool]:
    """Ensure one durable pilot sales lead so the F9C § 98 step J
    cross-tenant IDOR probe always hits a real id instead of falling
    back to a bogus UUID.

    The lead lives in `mice_opportunities` with `_kind="lead"` (matches
    `backend/domains/sales/router.py:LEAD_KIND`) so it shows up in
    `GET /api/sales/leads`. `pilot_fixture=True` + the stable
    `IDOR_PROBE_SEED` company name mark it as a long-lived fixture and
    keep it out of the residue-cleanup script's `E2E_` regex.
    """
    existing = await db.mice_opportunities.find_one(
        {
            "_kind": "lead",
            "tenant_id": pilot_tid,
            "pilot_fixture": True,
        },
        {"id": 1, "_id": 0},
    )
    if existing and existing.get("id"):
        return existing["id"], False
    lead_id = str(uuid.uuid4())
    now = _now_iso()
    await db.mice_opportunities.insert_one(
        {
            "_kind": "lead",
            "id": lead_id,
            "tenant_id": pilot_tid,
            "company_name": SALES_LEAD_COMPANY,
            "contact_name": SALES_LEAD_CONTACT,
            "contact_email": SALES_LEAD_EMAIL,
            "contact_phone": "",
            "source": "pilot_fixture",
            "status": "new",
            "priority": "low",
            "estimated_value": 0,
            "estimated_rooms": 0,
            "target_checkin": None,
            "assigned_to": None,
            "lead_score": 0,
            "notes": ("Read-only fixture for F9C § 98 sales-lifecycle step J (cross-tenant IDOR probe). Do not mutate or delete — the stress suite expects this id to remain reachable."),
            "pilot_fixture": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    return lead_id, True


async def _ensure_payroll_run(pilot_tid: str) -> tuple[str, bool]:
    """Ensure one durable pilot `payroll_runs` doc so the export-artifact
    IDOR spec (91) harvests a real pilot run id instead of a bogus UUID.

    `status="fixture"` (NOT draft/locked) keeps it out of the
    (tenant, period_month, status=draft) partial-unique index and ensures
    it never looks like a real finalized payroll run. `pilot_fixture=True`
    marks it long-lived; the residue-cleanup script
    (`backend/scripts/cleanup_e2e_pilot_residue.py`) only sweeps
    bookings/guests/folio_charges, so this row is left alone across runs.
    """
    existing = await db.payroll_runs.find_one(
        {"tenant_id": pilot_tid, "pilot_fixture": True},
        {"id": 1, "_id": 0},
    )
    if existing and existing.get("id"):
        return existing["id"], False
    run_id = str(uuid.uuid4())
    now = _now_iso()
    await db.payroll_runs.insert_one(
        {
            "id": run_id,
            "tenant_id": pilot_tid,
            "period_month": PAYROLL_FIXTURE_PERIOD,
            "status": "fixture",
            "rows": [],
            "summary": {},
            "extras": [],
            "note": ("Read-only fixture for export-artifact IDOR spec (91) cross-tenant export probe. Do not mutate or delete — the stress suite expects this id to remain reachable."),
            "parent_run_id": None,
            "finalized_at": None,
            "finalized_by": None,
            "created_at": now,
            "updated_at": now,
            "pilot_fixture": True,
            "_kind": "fixture",
        }
    )
    return run_id, True


@router.post("/admin/pilot-fixtures/ensure")
async def ensure_pilot_fixtures(
    req: PilotFixturesRequest,
    current_user: User = Depends(require_super_admin),
):
    """Idempotently ensure pilot tenant has one room_block + one kbs_report
    fixture so the F8M v2 § 41B B2B IDOR matrix spec exercises real ids."""
    pilot_tid = _pilot_tid()
    if req.pilot_tenant_id != pilot_tid:
        raise HTTPException(
            status_code=403,
            detail=("pilot_tenant_id does not match PILOT_TENANT_ID env. Pilot-fixture endpoint refuses to seed any other tenant."),
        )

    block_id, block_created = await _ensure_room_block(pilot_tid)
    kbs_report_id, kbs_created = await _ensure_kbs_report(pilot_tid)
    sales_lead_id, lead_created = await _ensure_sales_lead(pilot_tid)
    payroll_run_id, payroll_created = await _ensure_payroll_run(pilot_tid)

    logger.info(
        "pilot_fixtures.ensure tenant=%s block_id=%s (created=%s) kbs_report_id=%s (created=%s) sales_lead_id=%s (created=%s) payroll_run_id=%s (created=%s)",
        pilot_tid,
        block_id,
        block_created,
        kbs_report_id,
        kbs_created,
        sales_lead_id,
        lead_created,
        payroll_run_id,
        payroll_created,
    )

    return {
        "ok": True,
        "pilot_tenant_id": pilot_tid,
        "agency_id": FIXTURE_AGENCY_ID,
        "block_id": block_id,
        "kbs_report_id": kbs_report_id,
        "sales_lead_id": sales_lead_id,
        "payroll_run_id": payroll_run_id,
        "created": {
            "block": block_created,
            "kbs_report": kbs_created,
            "sales_lead": lead_created,
            "payroll_run": payroll_created,
        },
    }
