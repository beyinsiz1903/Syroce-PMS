"""
Pilot Read-Only Fixtures — F8M v2 § 41B sample-gap closer
==========================================================
Idempotently ensures the pilot tenant carries one `room_blocks` doc
and one `kbs_reports` doc so the B2B sub-router IDOR matrix spec
(`frontend/e2e-stress/specs/41B-b2b-subrouter-matrix.spec.js`) can
exercise real pilot ids for the `groups` and `kbs` rows instead of
falling back to BOGUS_UUID (pure existence-deny).

Fail-closed gates:
- super_admin role required (require_super_admin_guard)
- request `pilot_tenant_id` must equal env `PILOT_TENANT_ID`
  (refuses to seed any other tenant)
- inserts are read-only fixtures (tagged `pilot_fixture=True`,
  `_kind=fixture`) — no booking flow, no external calls, no PII

Endpoint:
- POST /api/admin/pilot-fixtures/ensure
    body: { pilot_tenant_id: str }
    returns: { block_id, kbs_report_id, agency_id, created: {...} }

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
    await db.room_blocks.insert_one({
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
    })
    return block_id, True


async def _ensure_kbs_report(pilot_tid: str) -> tuple[str, bool]:
    existing = await db.kbs_reports.find_one(
        {"tenant_id": pilot_tid, "pilot_fixture": True},
        {"id": 1, "_id": 0},
    )
    if existing and existing.get("id"):
        return existing["id"], False
    report_id = str(uuid.uuid4())
    await db.kbs_reports.insert_one({
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
    })
    return report_id, True


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
            detail=(
                "pilot_tenant_id does not match PILOT_TENANT_ID env. "
                "Pilot-fixture endpoint refuses to seed any other tenant."
            ),
        )

    block_id, block_created = await _ensure_room_block(pilot_tid)
    kbs_report_id, kbs_created = await _ensure_kbs_report(pilot_tid)

    logger.info(
        "pilot_fixtures.ensure tenant=%s block_id=%s (created=%s) "
        "kbs_report_id=%s (created=%s)",
        pilot_tid, block_id, block_created, kbs_report_id, kbs_created,
    )

    return {
        "ok": True,
        "pilot_tenant_id": pilot_tid,
        "agency_id": FIXTURE_AGENCY_ID,
        "block_id": block_id,
        "kbs_report_id": kbs_report_id,
        "created": {
            "block": block_created,
            "kbs_report": kbs_created,
        },
    }
