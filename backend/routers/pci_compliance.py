"""PCI-DSS Compliance reporting endpoints.

Surfaces the evaluator in `core/pci_dss.py` so admins (and procurement
teams) can see which controls are in place. Also exports a JSON
attestation packet and a CSV of all 12 requirements.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core.csv_safe import safe_writerow
from core.pci_dss import evaluate_controls, summary
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/compliance/pci", tags=["compliance"])

_ADMIN_ROLES = {"super_admin", "platform_admin", "admin", "owner"}


def _require_admin(user: User) -> None:
    role = (user.role or "").lower()
    if role not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Bu rapor için yönetici yetkisi gerekli")


@router.get("/status")
async def get_status(current_user: User = Depends(get_current_user)) -> dict:
    _require_admin(current_user)
    controls = evaluate_controls()
    return summary(controls)


@router.get("/controls")
async def get_controls(current_user: User = Depends(get_current_user)) -> dict:
    _require_admin(current_user)
    controls = evaluate_controls()
    return {
        "summary": summary(controls),
        "controls": controls,
    }


@router.get("/report.csv")
async def export_csv(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    controls = evaluate_controls()
    buf = io.StringIO()
    writer = csv.writer(buf)
    # Bug AN: defend against spreadsheet formula injection in any
    # evidence/recommendations text that might begin with =/+/-/@
    safe_writerow(writer, ["Req #", "Title", "Status", "Evidence", "Recommendations"])
    for c in controls:
        safe_writerow(writer, [
            c["req_id"],
            c["title"],
            c["status"],
            " | ".join(c["evidence"]),
            " | ".join(c["recommendations"]),
        ])
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel
    fname = f"pci_dss_report_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/attestation")
async def attestation(current_user: User = Depends(get_current_user)):
    """Downloadable JSON attestation packet — useful for procurement RFPs."""
    _require_admin(current_user)
    controls = evaluate_controls()
    packet = {
        "issuer": "Syroce Hotel PMS",
        "tenant_id": current_user.tenant_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "issued_by": {
            "user_id": current_user.id,
            "user_email": current_user.email,
            "role": current_user.role,
        },
        "summary": summary(controls),
        "controls": controls,
        "disclaimer": (
            "Bu rapor, kontrollerin teknik olarak uygulanmış olduğunu "
            "gösteren bir öz-değerlendirmedir. Resmi PCI-DSS sertifikasyonu "
            "için yetkili bir QSA değerlendirmesi gereklidir."
        ),
    }
    fname = f"syroce_pci_attestation_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    return Response(
        content=json.dumps(packet, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
