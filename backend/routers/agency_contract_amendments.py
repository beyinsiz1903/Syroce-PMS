"""Amendments to an approved hotel–agency contract, without terminating it.

Either party proposes new terms (payment terms, commission, cancellation
policy, validity); the other party approves or rejects, the proposer may
withdraw. While a proposal is pending the current terms stay in force, so
sales never stop. Approved terms apply to bookings made afterwards: every
booking keeps the terms it was sold with (it stores its own payment terms,
commission and cancellation policy). The contract keeps its code; each
approved amendment bumps ``terms_version`` and is kept with the previous
values in ``amendments``.

Agency (portal):   /api/marketplace/v1/contracts/{id}/amendments
Hotel (PMS JWT):   /api/marketplace/incoming-requests/{id}/amendments
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from pymongo import ReturnDocument

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from routers.agency_contracts import CancellationPolicy, _notify_contract_decision, _require_hotel_user, _validate_dates
from routers.marketplace_b2b import get_marketplace_agency

agency_router = APIRouter(prefix="/api/marketplace/v1/contracts", tags=["Marketplace v1 / Contract amendments"])
hotel_router = APIRouter(prefix="/api/marketplace/incoming-requests", tags=["Marketplace v1 / Contract amendments"])

TERMS = ("payment_terms", "commission_pct", "cancellation_policy", "valid_from", "valid_to")
PAYMENT_TERMS = {"prepaid": "Ön ödemeli", "on_arrival": "Girişte", "net_7": "7 gün vadeli", "net_15": "15 gün vadeli", "net_30": "30 gün vadeli"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AmendmentCreate(BaseModel):
    payment_terms: str | None = Field(None, pattern="^(prepaid|on_arrival|net_7|net_15|net_30)$")
    commission_pct: float | None = Field(None, ge=0, le=100)
    cancellation_policy: CancellationPolicy | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    note: str = Field("", max_length=1000)

    @model_validator(mode="after")
    def _something_changes(self):
        if all(getattr(self, key) is None for key in TERMS):
            raise ValueError("En az bir koşulu değiştirin")
        return self


class AmendmentApprove(BaseModel):
    note: str = Field("", max_length=1000)
    # Hotel only: the credit limit stays the hotel's decision.
    credit_limit: float | None = Field(None, ge=0)
    credit_currency: str | None = Field(None, pattern="^[A-Z]{3}$")


class AmendmentReject(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)


@dataclass(frozen=True)
class Party:
    side: str  # "hotel" | "agency"
    actor: str
    owner: dict


def _agency_party(agency: dict) -> Party:
    actor = (agency.get("user") or {}).get("email") or agency.get("contact_email") or agency["agency_id"]
    return Party("agency", actor, {"agency_id": agency["agency_id"]})


def _hotel_party(current_user: User) -> Party:
    return Party("hotel", current_user.email, {"tenant_id": _require_hotel_user(current_user)})


def _other(side: str) -> str:
    return "agency" if side == "hotel" else "hotel"


def _describe(changes: dict, contract: dict) -> str:
    parts = []
    if "payment_terms" in changes:
        parts.append(f"ödeme {PAYMENT_TERMS.get(contract.get('payment_terms'), contract.get('payment_terms'))} → {PAYMENT_TERMS.get(changes['payment_terms'], changes['payment_terms'])}")
    if "commission_pct" in changes:
        parts.append(f"komisyon %{float(contract.get('commission_pct') or 0):g} → %{changes['commission_pct']:g}")
    if "cancellation_policy" in changes:
        policy = changes["cancellation_policy"]
        parts.append(f"iptal: girişten {policy['free_until_days_before']} gün öncesine kadar ücretsiz, sonra %{policy['penalty_pct']:g}, no-show %{policy['no_show_penalty_pct']:g}")
    if "valid_from" in changes or "valid_to" in changes:
        parts.append(f"geçerlilik {changes.get('valid_from', contract.get('valid_from'))} – {changes.get('valid_to', contract.get('valid_to'))}")
    return "; ".join(parts)


async def _load(contract_id: str, party: Party) -> dict:
    contract = await get_system_db().agency_contracts.find_one({"id": contract_id, **party.owner}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Sözleşme bulunamadı")
    return contract


async def _notify(sysdb, contract: dict, to_side: str, title: str, message: str) -> None:
    if to_side == "agency":
        await _notify_contract_decision(sysdb, contract, title, message)
        return
    from core.agency_notify import notify_hotel

    await notify_hotel(
        contract["tenant_id"], kind="agency_contract_amendment",
        title=f"{contract.get('contract_code', '')} · {contract.get('agency_name', '')}: {title}", message=message,
        action_url="/app/incoming-agency-contracts", metadata={"contract_id": contract["id"]},
    )


async def _event(sysdb, contract: dict, event: str, actor: str, payload: dict) -> None:
    await sysdb.agency_contract_events.insert_one({
        "id": str(uuid.uuid4()), "contract_id": contract["id"], "agency_id": contract["agency_id"],
        "tenant_id": contract["tenant_id"], "event": event, "actor": actor, "payload": payload, "created_at": _now(),
    })


async def _propose(contract_id: str, data: AmendmentCreate, party: Party) -> dict:
    sysdb = get_system_db()
    contract = await _load(contract_id, party)
    if contract.get("status") != "approved":
        raise HTTPException(409, "Değişiklik yalnız onaylı sözleşmeye önerilebilir")
    if contract.get("pending_amendment"):
        raise HTTPException(409, "Bu sözleşmede yanıt bekleyen bir değişiklik teklifi var; önce sonuçlanmalı")
    changes = {}
    for key in TERMS:
        value = getattr(data, key)
        if value is None:
            continue
        value = value.model_dump() if isinstance(value, CancellationPolicy) else value
        if value != contract.get(key):
            changes[key] = value
    if not changes:
        raise HTTPException(400, "Önerilen koşullar mevcut sözleşmeyle aynı")
    if "commission_pct" in changes and contract.get("contract_type") == "net_rate":
        raise HTTPException(400, "Net fiyat sözleşmesinde komisyon yoktur; fiyatlar otel tarafından sezon bazında belirlenir")
    if "valid_from" in changes or "valid_to" in changes:
        valid_from = changes.get("valid_from", contract.get("valid_from"))
        valid_to = changes.get("valid_to", contract.get("valid_to"))
        _validate_dates(valid_from, valid_to)
        if valid_to < datetime.now(UTC).date().isoformat():
            raise HTTPException(400, "Yeni bitiş tarihi geçmişte olamaz; sözleşmeyi sonlandırmak için fesih kullanın")
    amendment = {"id": str(uuid.uuid4()), "changes": changes, "note": data.note.strip(), "proposed_by_side": party.side,
                 "proposed_by": party.actor, "proposed_at": _now(), "terms_version": contract.get("terms_version") or 1}
    updated = await sysdb.agency_contracts.find_one_and_update(
        {"id": contract_id, **party.owner, "status": "approved", "pending_amendment": None},
        {"$set": {"pending_amendment": amendment, "updated_at": _now()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Sözleşme eş zamanlı değişti; yenileyip tekrar deneyin")
    await _event(sysdb, updated, "amendment_proposed", party.actor, {"side": party.side, "changes": changes, "note": amendment["note"]})
    await _notify(sysdb, updated, _other(party.side), "sözleşme değişikliği önerildi",
                  f"{_describe(changes, contract)}. {amendment['note']}".strip() + " Onaylayın veya reddedin.")
    return {"ok": True, "contract": updated}


def _pending(contract: dict, amendment_id: str) -> dict:
    amendment = contract.get("pending_amendment") or {}
    if amendment.get("id") != amendment_id:
        raise HTTPException(409, "Yanıt bekleyen böyle bir değişiklik teklifi yok")
    return amendment


async def _approve(contract_id: str, amendment_id: str, data: AmendmentApprove, party: Party) -> dict:
    sysdb = get_system_db()
    contract = await _load(contract_id, party)
    amendment = _pending(contract, amendment_id)
    if amendment["proposed_by_side"] == party.side:
        raise HTTPException(403, "Kendi teklifinizi onaylayamazsınız; karşı tarafın onayı gerekir")
    if contract.get("status") != "approved":
        raise HTTPException(409, "Sözleşme artık onaylı değil")
    if party.side == "agency" and data.credit_limit is not None:
        raise HTTPException(403, "Kredi limitini yalnız otel belirler")
    if data.credit_limit is not None and not data.credit_currency:
        raise HTTPException(422, "Kredi limiti için kredi para birimi zorunludur")
    changes = dict(amendment["changes"])
    # Re-checked now: a proposal may wait for days, and terms that are no
    # longer valid would leave an "approved" contract no sale can use.
    valid_from = changes.get("valid_from", contract.get("valid_from"))
    valid_to = changes.get("valid_to", contract.get("valid_to"))
    if "valid_from" in changes or "valid_to" in changes:
        _validate_dates(valid_from, valid_to)
    if valid_to and valid_to < datetime.now(UTC).date().isoformat():
        raise HTTPException(409, "Teklifteki bitiş tarihi geçti; güncel tarihlerle yeni bir teklif gönderin")
    updates = {**changes, "updated_at": _now(), "pending_amendment": None,
               "terms_version": (contract.get("terms_version") or 1) + 1}
    if "commission_pct" in changes:
        updates["hotel_approved_commission_pct"] = changes["commission_pct"]
    if data.credit_limit is not None:
        updates.update(credit_limit=data.credit_limit, credit_currency=data.credit_currency)
    previous = {key: contract.get(key) for key in changes}
    if data.credit_limit is not None:
        previous.update(credit_limit=contract.get("credit_limit"), credit_currency=contract.get("credit_currency"))
    record = {**amendment, "status": "approved", "decided_by": party.actor, "decided_by_side": party.side,
              "decided_at": _now(), "decision_note": data.note.strip(), "previous": previous,
              **({"credit_limit": data.credit_limit, "credit_currency": data.credit_currency} if data.credit_limit is not None else {})}
    updated = await sysdb.agency_contracts.find_one_and_update(
        # Only the proposal that was read, on a contract still approved.
        {"id": contract_id, **party.owner, "status": "approved", "pending_amendment.id": amendment_id},
        {"$set": updates, "$push": {"amendments": record}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Teklif eş zamanlı sonuçlandı veya sözleşme değişti; yenileyin")
    await _event(sysdb, updated, "amendment_approved", party.actor, {"side": party.side, "changes": changes, "previous": previous})
    await _notify(sysdb, updated, _other(party.side), "sözleşme değişikliği onaylandı",
                  f"{_describe(changes, contract)}. Yeni koşullar bundan sonraki rezervasyonlara uygulanır; mevcut rezervasyonlar kendi koşullarını korur.")
    return {"ok": True, "contract": updated}


async def _close(contract_id: str, amendment_id: str, party: Party, *, status: str, reason: str) -> dict:
    sysdb = get_system_db()
    contract = await _load(contract_id, party)
    amendment = _pending(contract, amendment_id)
    if status == "withdrawn" and amendment["proposed_by_side"] != party.side:
        raise HTTPException(403, "Yalnız teklifi yapan taraf geri çekebilir")
    if status == "rejected" and amendment["proposed_by_side"] == party.side:
        raise HTTPException(403, "Kendi teklifinizi reddedemezsiniz; geri çekebilirsiniz")
    record = {**amendment, "status": status, "decided_by": party.actor, "decided_by_side": party.side,
              "decided_at": _now(), "decision_note": reason.strip()}
    updated = await sysdb.agency_contracts.find_one_and_update(
        {"id": contract_id, **party.owner, "pending_amendment.id": amendment_id},
        {"$set": {"pending_amendment": None, "updated_at": _now()}, "$push": {"amendments": record}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Teklif eş zamanlı sonuçlandı; yenileyin")
    await _event(sysdb, updated, f"amendment_{status}", party.actor, {"side": party.side, "reason": reason.strip()})
    title = "sözleşme değişikliği reddedildi" if status == "rejected" else "sözleşme değişikliği geri çekildi"
    await _notify(sysdb, updated, _other(party.side), title, reason.strip() or "Mevcut koşullar geçerli.")
    return {"ok": True, "contract": updated}


# ── Agency ─────────────────────────────────────────────────────────


@agency_router.post("/{contract_id}/amendments")
async def agency_propose_amendment(contract_id: str, data: AmendmentCreate, agency: dict = Depends(get_marketplace_agency)):
    return await _propose(contract_id, data, _agency_party(agency))


@agency_router.post("/{contract_id}/amendments/{amendment_id}/approve")
async def agency_approve_amendment(contract_id: str, amendment_id: str, data: AmendmentApprove, agency: dict = Depends(get_marketplace_agency)):
    return await _approve(contract_id, amendment_id, data, _agency_party(agency))


@agency_router.post("/{contract_id}/amendments/{amendment_id}/reject")
async def agency_reject_amendment(contract_id: str, amendment_id: str, data: AmendmentReject, agency: dict = Depends(get_marketplace_agency)):
    return await _close(contract_id, amendment_id, _agency_party(agency), status="rejected", reason=data.reason)


@agency_router.post("/{contract_id}/amendments/{amendment_id}/withdraw")
async def agency_withdraw_amendment(contract_id: str, amendment_id: str, agency: dict = Depends(get_marketplace_agency)):
    return await _close(contract_id, amendment_id, _agency_party(agency), status="withdrawn", reason="")


# ── Hotel ──────────────────────────────────────────────────────────


@hotel_router.post("/{contract_id}/amendments")
async def hotel_propose_amendment(contract_id: str, data: AmendmentCreate, current_user: User = Depends(get_current_user),
                                  _perm=Depends(require_op("manage_approvals"))):
    return await _propose(contract_id, data, _hotel_party(current_user))


@hotel_router.post("/{contract_id}/amendments/{amendment_id}/approve")
async def hotel_approve_amendment(contract_id: str, amendment_id: str, data: AmendmentApprove,
                                  current_user: User = Depends(get_current_user), _perm=Depends(require_op("manage_approvals"))):
    return await _approve(contract_id, amendment_id, data, _hotel_party(current_user))


@hotel_router.post("/{contract_id}/amendments/{amendment_id}/reject")
async def hotel_reject_amendment(contract_id: str, amendment_id: str, data: AmendmentReject,
                                 current_user: User = Depends(get_current_user), _perm=Depends(require_op("manage_approvals"))):
    return await _close(contract_id, amendment_id, _hotel_party(current_user), status="rejected", reason=data.reason)


@hotel_router.post("/{contract_id}/amendments/{amendment_id}/withdraw")
async def hotel_withdraw_amendment(contract_id: str, amendment_id: str, current_user: User = Depends(get_current_user),
                                   _perm=Depends(require_op("manage_approvals"))):
    return await _close(contract_id, amendment_id, _hotel_party(current_user), status="withdrawn", reason="")
