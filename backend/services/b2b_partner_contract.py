"""
B2B Partner Contract Layer — a single, consolidated read of an agency's effective
commercial terms for the B2B booking hot path.

Today the terms an agency books under are scattered: the approved B2B contract
(`sysdb.agency_contracts`), the legacy commission on the agency record
(`sysdb.agencies.commission_rate`), and (for T003) per-agency credit/allotment
controls. This service folds them into ONE read so the booking path has a single,
authoritative source instead of re-deriving terms inline.

Resolution (additive, non-destructive, back-compatible):
  - Commission / payment terms / allowed room types / currency come from the
    APPROVED + date-valid contract when one exists; the contract value WINS.
  - With NO approved contract the agency still transacts on its legacy
    `commission_rate` (back-compat — fail-OPEN on terms, pilot_drift=0).
  - Credit limit and allotments are OPT-IN business controls carried on the
    contract: absent config => uncapped / no caps. They are surfaced here
    READ-ONLY; HARD, race-safe enforcement lives in
    ``services.b2b_booking_guards`` (T003). T002 never rejects on them.

Read-only. No writes, no PII. Tenant-scoped by construction: the contract lookup
is keyed (agency_id, tenant_id) and the agency id is unique within its tenant.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)

# Mirrors booking_engine's historical default (agency.get("commission_rate", 0))
# so the no-contract path stays byte-identical to the legacy behaviour.
_DEFAULT_COMMISSION_PCT = 0.0
_DEFAULT_PAYMENT_TERMS = "on_arrival"


@dataclass(frozen=True)
class PartnerContractSnapshot:
    """Effective commercial terms for one (tenant, agency) at a point in time."""

    tenant_id: str
    agency_id: str
    has_contract: bool
    commission_pct: float
    commission_source: str  # "contract" | "agency_default"
    payment_terms: str
    allowed_room_types: list[str]
    currency: str | None
    # Opt-in controls (None / [] => uncapped). Enforced in T003, not here.
    credit_limit: float | None
    current_debt: float
    available_credit: float | None
    allotments: list[dict] = field(default_factory=list)
    # Reference / audit fields (never used for authz decisions).
    contract_id: str | None = None
    contract_code: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    def is_room_type_allowed(self, room_type: str) -> bool:
        """True when the contract places no room-type restriction, or the
        requested type is explicitly allowed. Empty list => no restriction."""
        if not self.allowed_room_types:
            return True
        return room_type in self.allowed_room_types

    def to_public_dict(self) -> dict:
        """JSON-safe projection (no internal-only fields beyond the contract terms)."""
        return {
            "has_contract": self.has_contract,
            "commission_pct": self.commission_pct,
            "commission_source": self.commission_source,
            "payment_terms": self.payment_terms,
            "allowed_room_types": list(self.allowed_room_types),
            "currency": self.currency,
            "credit_limit": self.credit_limit,
            "available_credit": self.available_credit,
            "allotments": [dict(a) for a in self.allotments],
            "contract_code": self.contract_code,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
        }


def _normalize_allotments(raw) -> list[dict]:
    """Coerce contract allotment config into a stable, read-only shape.

    Each entry: {room_type, period_start, period_end, rooms_allocated, rooms_used}.
    Tolerant of missing keys so a partially-configured contract never raises on
    the hot path; enforcement (T003) reads rooms_allocated / rooms_used.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append({
            "room_type": item.get("room_type"),
            "period_start": item.get("period_start"),
            "period_end": item.get("period_end"),
            "rooms_allocated": int(item.get("rooms_allocated", 0) or 0),
            "rooms_used": int(item.get("rooms_used", 0) or 0),
        })
    return out


async def build_snapshot(
    tenant_id: str,
    agency_id: str,
    *,
    agency_doc: dict | None = None,
    on_date: str | None = None,
) -> PartnerContractSnapshot:
    """Build the consolidated partner-contract snapshot for one agency.

    Reads at most two SYSTEM-db documents (the active contract + the agency
    record). ``agency_doc`` may be supplied by the caller (e.g. the value the
    B2B auth dependency already loaded) to skip the legacy-fallback fields, but
    the agency record is always read for the atomic ``current_debt`` counter so
    the snapshot is complete for T003.
    """
    # Lazy import: routers.agency_contracts imports routers.marketplace_b2b at
    # module load — keep it out of import time to avoid a circular import.
    from routers.agency_contracts import has_active_contract

    sysdb = get_system_db()

    contract = await has_active_contract(agency_id, tenant_id, on_date)

    agency = await sysdb.agencies.find_one(
        {"id": agency_id, "tenant_id": tenant_id},
        {"_id": 0, "commission_rate": 1, "current_debt": 1, "currency": 1},
    ) or {}

    legacy_commission = float(agency_doc.get("commission_rate", agency.get("commission_rate", _DEFAULT_COMMISSION_PCT))
                              if agency_doc else agency.get("commission_rate", _DEFAULT_COMMISSION_PCT) or _DEFAULT_COMMISSION_PCT)
    current_debt = float(agency.get("current_debt", 0.0) or 0.0)

    if contract:
        commission_pct = float(contract.get("commission_pct", legacy_commission) or 0.0)
        commission_source = "contract"
        payment_terms = contract.get("payment_terms") or _DEFAULT_PAYMENT_TERMS
        allowed_room_types = list(contract.get("allowed_room_types") or [])
        currency = contract.get("currency") or agency.get("currency")
        raw_credit = contract.get("credit_limit", None)
        credit_limit = float(raw_credit) if raw_credit is not None else None
        allotments = _normalize_allotments(contract.get("allotments"))
        contract_id = contract.get("id")
        contract_code = contract.get("contract_code")
        valid_from = contract.get("valid_from")
        valid_to = contract.get("valid_to")
    else:
        commission_pct = legacy_commission
        commission_source = "agency_default"
        payment_terms = _DEFAULT_PAYMENT_TERMS
        allowed_room_types = []
        currency = agency.get("currency")
        credit_limit = None
        allotments = []
        contract_id = contract_code = valid_from = valid_to = None

    available_credit = (
        round(credit_limit - current_debt, 2) if credit_limit is not None else None
    )

    return PartnerContractSnapshot(
        tenant_id=tenant_id,
        agency_id=agency_id,
        has_contract=bool(contract),
        commission_pct=commission_pct,
        commission_source=commission_source,
        payment_terms=payment_terms,
        allowed_room_types=allowed_room_types,
        currency=currency,
        credit_limit=credit_limit,
        current_debt=current_debt,
        available_credit=available_credit,
        allotments=allotments,
        contract_id=contract_id,
        contract_code=contract_code,
        valid_from=valid_from,
        valid_to=valid_to,
    )
