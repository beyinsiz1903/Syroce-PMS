"""What is waiting, for either party of the Agency Extranet, in one list.

For a side ("hotel" or "agency") and its scope ({"tenant_id"} / {"agency_id"})
every open item is reported once, either as **yours** (this side must act) or
**theirs** (waiting for the other side), with a link target:

* contract request — the hotel approves or rejects an agency's request;
* contract amendment — the side that did not propose it decides;
* statement approval — issued / resolved and this side has not agreed to the
  current revision (each line correction bumps the revision);
* dispute — the side that did not raise it answers;
* payment notice — the payee verifies a pending notice;
* payment — an agreed statement with an open balance and no pending notice:
  the debtor pays, due on agreement date + payment term (core.agency_reports).

The same rules as the routers that act on them (agency_contracts,
agency_contract_amendments, agency_statements); nothing here writes.
"""

from __future__ import annotations

from datetime import date

from core.agency_reports import due_date
from core.agency_statements import outstanding

SIDES = ("hotel", "agency")
OPEN_STATEMENTS = ("issued", "agreed", "disputed", "resolved")
PAYABLE = ("agreed", "resolved")


def _other(side: str) -> str:
    return "agency" if side == "hotel" else "hotel"


def _agreements(statement: dict) -> dict:
    """Revision each party agreed to (legacy statements: hotel-issued)."""
    if isinstance(statement.get("agreements"), dict):
        return {side: statement["agreements"].get(side) for side in SIDES}
    revision = statement.get("revision") or 1
    agreed = statement.get("status") in ("agreed", "settled")
    return {"hotel": revision, "agency": revision if agreed else None}


def _party_name(doc: dict, side: str) -> str | None:
    """The counterpart's name as this side sees it."""
    return doc.get("agency_name") if side == "hotel" else doc.get("hotel_name")


def _item(kind: str, owner: str, doc: dict, side: str, **extra) -> dict:
    return {
        "kind": kind,
        "owner": owner,  # "yours" | "theirs"
        "party_name": _party_name(doc, side),
        "party_id": doc.get("agency_id") if side == "hotel" else doc.get("tenant_id"),
        **extra,
    }


def contract_items(contract: dict, side: str) -> list[dict]:
    items = []
    ref = contract.get("contract_code") or contract.get("id")
    if contract.get("status") == "pending":
        # Agencies request, hotels decide.
        owner = "yours" if side == "hotel" else "theirs"
        items.append(_item("contract_request", owner, contract, side, target="contracts", ref=ref,
                           record_id=contract.get("id"), since=contract.get("created_at"),
                           commission_pct=contract.get("commission_pct"), payment_terms=contract.get("payment_terms")))
    amendment = contract.get("pending_amendment")
    if contract.get("status") == "approved" and isinstance(amendment, dict):
        owner = "theirs" if amendment.get("proposed_by_side") == side else "yours"
        items.append(_item("contract_amendment", owner, contract, side, target="contracts", ref=ref,
                           record_id=contract.get("id"), since=amendment.get("proposed_at"),
                           changes=amendment.get("changes") or {}))
    return items


def statement_items(statement: dict, side: str, today: date) -> list[dict]:
    status = statement.get("status")
    if status not in OPEN_STATEMENTS:
        return []
    items = []
    ref = statement.get("number") or statement.get("id")
    common = {"target": "statements", "ref": ref, "record_id": statement.get("id"),
              "currency": statement.get("currency") or "TRY",
              "period": [statement.get("period_start"), statement.get("period_end")]}
    revision = statement.get("revision") or 1
    agreements = _agreements(statement)

    if status in ("issued", "resolved"):
        mine, theirs = agreements.get(side) == revision, agreements.get(_other(side)) == revision
        if not mine:
            items.append(_item("statement_approval", "yours", statement, side, since=statement.get("updated_at") or statement.get("issued_at"), **common))
        elif not theirs:
            items.append(_item("statement_approval", "theirs", statement, side, since=statement.get("updated_at") or statement.get("issued_at"), **common))

    if status == "disputed":
        dispute = statement.get("dispute") or {}
        owner = "theirs" if (dispute.get("by_side") or "agency") == side else "yours"
        items.append(_item("dispute", owner, statement, side, since=dispute.get("at"), reason=dispute.get("reason"), **common))

    pending = [n for n in statement.get("payment_notices") or [] if n.get("status") == "pending"]
    for notice in pending:
        payee = "hotel" if (notice.get("direction") or "agency_to_hotel") == "agency_to_hotel" else "agency"
        owner = "yours" if payee == side else "theirs"
        items.append(_item("payment_notice", owner, statement, side, since=notice.get("reported_at"),
                           amount=notice.get("amount"), notice_id=notice.get("id"), payment_ref=notice.get("reference"), **common))

    if status in PAYABLE and not pending:
        balance = outstanding(statement)
        if abs(balance) >= 0.01:
            debtor = "agency" if balance > 0 else "hotel"
            due = due_date(statement)
            items.append(_item("payment", "yours" if debtor == side else "theirs", statement, side,
                               since=statement.get("agreed_at"), amount=round(abs(balance), 2),
                               due_date=due.isoformat() if due else None,
                               overdue=bool(due and due < today), **common))
    return items


def _sort_key(item: dict):
    return (not item.get("overdue"), item.get("due_date") or "9999", item.get("since") or "")


async def pending_actions(sysdb, *, side: str, scope: dict, today: date) -> dict:
    if side not in SIDES:
        raise ValueError(side)
    items: list[dict] = []
    contract_query = {**scope, "contract_code": {"$type": "string"},
                      "$or": [{"status": "pending"}, {"status": "approved", "pending_amendment": {"$type": "object"}}]}
    async for contract in sysdb.agency_contracts.find(contract_query, {"_id": 0}):
        items.extend(contract_items(contract, side))
    async for statement in sysdb.agency_statements.find({**scope, "status": {"$in": list(OPEN_STATEMENTS)}}, {"_id": 0}):
        items.extend(statement_items(statement, side, today))
    yours = sorted((i for i in items if i["owner"] == "yours"), key=_sort_key)
    theirs = sorted((i for i in items if i["owner"] == "theirs"), key=_sort_key)
    return {"side": side, "as_of": today.isoformat(), "yours": yours, "theirs": theirs,
            "counts": {"yours": len(yours), "theirs": len(theirs), "overdue": sum(1 for i in yours if i.get("overdue"))}}
