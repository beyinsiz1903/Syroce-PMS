"""Hotel-scoped Extranet directory; no shadow local agencies or payments.

Balances come from the same report/statement service used by both parties.
An approved contract is enough to list a partner, even before its first sale.
Expired partners with financial history remain accessible for settlement.
"""

from datetime import date

from core.agency_reports import build_report

CONTRACT_STATUSES = ("approved", "terminated", "expired")


async def finance_partners(database, tenant_id: str) -> dict[str, dict]:
    partners: dict[str, dict] = {}
    async for contract in database.agency_contracts.find(
        {"tenant_id": tenant_id, "status": {"$in": list(CONTRACT_STATUSES)}},
        {"_id": 0, "agency_id": 1, "agency_name": 1, "status": 1},
    ):
        aid = contract.get("agency_id")
        if aid:
            partner = partners.setdefault(aid, {"id": aid, "name": contract.get("agency_name"), "approved": False})
            partner["approved"] |= contract.get("status") == "approved"
    # Contract removal must not make an existing financial record inaccessible.
    for collection, query in (
        (database.marketplace_bookings, {"tenant_id": tenant_id}),
        (database.agency_statements, {"tenant_id": tenant_id, "status": {"$ne": "void"}}),
    ):
        async for row in collection.find(query, {"_id": 0, "agency_id": 1, "agency_name": 1}):
            aid = row.get("agency_id")
            if aid:
                partner = partners.setdefault(aid, {"id": aid, "name": row.get("agency_name"), "approved": False})
                partner["has_financial_history"] = True
    return partners


async def extranet_directory(database, tenant_id: str, *, today: date) -> dict:
    partners = await finance_partners(database, tenant_id)
    if not partners:
        return {"agencies": [], "as_of": today.isoformat()}
    async for agency in database.marketplace_agencies.find(
        {"id": {"$in": list(partners)}},
        {"_id": 0, "id": 1, "name": 1, "contact_name": 1, "contact_email": 1, "status": 1},
    ):
        partners[agency["id"]].update({key: agency[key] for key in ("name", "contact_name", "contact_email", "status") if key in agency})
    report = await build_report(database, side="hotel", scope={"tenant_id": tenant_id},
                                period_start=today.isoformat(), period_end=today.isoformat(), today=today)
    for partner in partners.values():
        partner["currencies"] = [
            {key: row[key] for key in ("currency", "receivables", "unbilled", "forward")}
            for row in report["rows"] if row["party_id"] == partner["id"]
        ]
        partner["finance_source"] = "extranet_statements"
    return {"agencies": sorted(partners.values(), key=lambda row: str(row.get("name") or row["id"]).casefold()),
            "as_of": report["as_of"]}


async def linked_extranet_id(database, tenant_id: str, agency_id: str, local: dict | None = None) -> str | None:
    """Only explicit IDs, never a name/email merge across independent partners."""
    candidates = {agency_id}
    if local:
        candidates.update(local.get(key) for key in ("marketplace_agency_id", "migrated_to_marketplace_agency_id") if local.get(key))
    scope = {"tenant_id": tenant_id, "agency_id": {"$in": sorted(candidates)}}
    for collection, extra in (
        (database.agency_contracts, {"status": {"$in": list(CONTRACT_STATUSES)}}),
        (database.marketplace_bookings, {}),
        (database.agency_statements, {"status": {"$ne": "void"}}),
    ):
        row = await collection.find_one({**scope, **extra}, {"_id": 0, "agency_id": 1})
        if row:
            return row["agency_id"]
    return None
