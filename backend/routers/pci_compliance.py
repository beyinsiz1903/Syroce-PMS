"""PCI-DSS Compliance reporting endpoints.

Surfaces the evaluator in `core/pci_dss.py` so admins (and procurement
teams) can see which controls are in place. Also exports a JSON
attestation packet (HMAC-SHA256 signed) and a multi-row CSV.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from core.csv_safe import safe_writerow
from core.pci_dss import VERSION, evaluate_cached, invalidate_cache, summary
from core.security import _is_super_admin, get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/compliance/pci", tags=["compliance"])

_ADMIN_ROLES = {"super_admin", "platform_admin", "admin", "owner"}


def _require_admin(user: User) -> None:
    if _is_super_admin(user):
        return
    role = (user.role or "").lower()
    if role in _ADMIN_ROLES:
        return
    roles = getattr(user, "roles", None) or []
    if isinstance(roles, list) and any(((r or "").lower() in _ADMIN_ROLES) for r in roles):
        return
    raise HTTPException(status_code=403, detail="Bu rapor için yönetici yetkisi gerekli")


def _signing_key() -> bytes:
    """HMAC anahtarı: ATTESTATION_SIGNING_KEY > JWT_SECRET fallback.

    Üretimde ATTESTATION_SIGNING_KEY ayrı tutulması önerilir (token compromise
    etki yarıçapını sınırlar)."""
    key = os.environ.get("ATTESTATION_SIGNING_KEY") or os.environ.get("JWT_SECRET") or ""
    return key.encode("utf-8")


def _hmac_sha256(payload: bytes) -> str:
    return hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()


@router.get("/status")
async def get_status(current_user: User = Depends(get_current_user)) -> dict:
    _require_admin(current_user)
    controls = await evaluate_cached(current_user.tenant_id)
    return summary(controls)


@router.get("/controls")
async def get_controls(
    current_user: User = Depends(get_current_user),
    refresh: bool = Query(False, description="True: cache bypass + invalidate"),
) -> dict:
    _require_admin(current_user)
    if refresh:
        invalidate_cache(current_user.tenant_id)
    controls = await evaluate_cached(current_user.tenant_id)
    return {"summary": summary(controls), "controls": controls}


@router.get("/report.csv")
async def export_csv(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    controls = await evaluate_cached(current_user.tenant_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    # safe_writerow: spreadsheet formula injection (= + - @) koruması.
    # Multi-row export: her evidence/öneri ayrı satır → Excel'de okunabilir.
    safe_writerow(writer, ["Req #", "Title", "Status", "Type", "Detail"])
    for c in controls:
        safe_writerow(writer, [c["req_id"], c["title"], c["status"], "summary", ""])
        for ev in c.get("evidence", []) or []:
            safe_writerow(writer, [c["req_id"], c["title"], c["status"], "evidence", ev])
        for rec in c.get("recommendations", []) or []:
            safe_writerow(writer, [c["req_id"], c["title"], c["status"], "recommendation", rec])
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel
    fname = f"pci_dss_report_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/attestation")
async def attestation(
    current_user: User = Depends(get_current_user),
    anonymize: bool = Query(
        False,
        description="True: kişisel detayları (email, user_id) gizle (KVKK/GDPR safe RFP paketi)",
    ),
):
    """Downloadable JSON attestation packet — HMAC-SHA256 signed.

    `anonymize=true` parametresi RFP/satın alma paylaşımları için kişisel
    detayları kaldırır (yalnız tenant_id, role kategorisi kalır).
    """
    _require_admin(current_user)
    controls = await evaluate_cached(current_user.tenant_id)

    issued_by: dict = {"role": current_user.role}
    if not anonymize:
        issued_by.update({
            "user_id": current_user.id,
            "user_email": current_user.email,
        })

    body = {
        "issuer": "Syroce Hotel PMS",
        "version": VERSION,
        "tenant_id": current_user.tenant_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "issued_by": issued_by,
        "anonymized": bool(anonymize),
        "summary": summary(controls),
        "controls": controls,
        "disclaimer": (
            "Bu rapor, kontrollerin teknik olarak uygulanmış olduğunu "
            "gösteren bir öz-değerlendirmedir. Resmi PCI-DSS sertifikasyonu "
            "için yetkili bir QSA değerlendirmesi gereklidir."
        ),
    }

    # Deterministic serialization → kararlı imza (sort_keys + separators).
    body_bytes = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sha256 = hashlib.sha256(body_bytes).hexdigest()
    sig = _hmac_sha256(body_bytes) if _signing_key() else None

    packet = {
        "body": body,
        "integrity": {
            "algo": "HMAC-SHA256" if sig else "SHA-256",
            "sha256": sha256,
            "hmac_sha256": sig,
            "signed": bool(sig),
            "verify_hint": (
                "json.dumps(body, sort_keys=True, separators=(',',':')) → "
                "HMAC-SHA256 with ATTESTATION_SIGNING_KEY"
            ),
        },
    }
    fname = f"syroce_pci_attestation_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    return Response(
        content=json.dumps(packet, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
