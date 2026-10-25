"""Offline, explicitly approved restoration of 69 Demo attribution preimages.

Not an HTTP endpoint or generic append-only bypass. Dry run is the default.
Only IP/device fields may become null, and ONLY if that reproduces the existing
SHA-256 commitment recorded in the already-sealed reconstruction incident.
The observed raw rows, their digests and a receipt commit atomically with all
69 restorations and a NEW restoration attestation. Old seals/links never change.
"""
import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime

from core import audit_chain
from modules.pms_core import demo_source_remediation as source
from shared_kernel.audit_helper import build_audit_entry

POLICY = "demo-audit-attribution-restoration-20261025-v1"
COLLECTIONS = ("audit_logs", "audit_logs_archive")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()).hexdigest()


async def plan(db, *, session=None):
    await source.guard(db, source.TENANT, session)
    kw = {"session": session} if session is not None else {}
    receipt = await db.demo_source_remediations.find_one({"tenant_id": source.TENANT, "id": source.POLICY}, **kw)
    if not receipt:
        raise ValueError("The sealed Demo reconstruction incident is required")
    anchor = []
    for name in COLLECTIONS:
        anchor += await db[name].find({"tenant_id": source.TENANT, "id": receipt["audit_id"]}, **kw).to_list(None)
    if len(anchor) != 1 or anchor[0].get("record_hash") != receipt["audit_hash"] or audit_chain.compute_record_hash(
            anchor[0], anchor[0]["seq"], anchor[0]["prev_hash"]) != receipt["audit_hash"]:
        raise ValueError("Incident commitment is missing, ambiguous or altered")
    incident = receipt["plan"]["audit_incident"]
    if anchor[0].get("after_snapshot", {}).get("audit_incident") != incident:
        raise ValueError("Incident differs from its existing audit commitment")
    findings = incident["findings"]
    if len(findings) != 69 or len({row["id"] for row in findings}) != 69:
        raise ValueError("Only the exact reviewed 69-record incident may be restored")
    rows = []
    for finding in findings:
        matches = []
        for name in COLLECTIONS:
            for row in await db[name].find({"tenant_id": source.TENANT, "id": finding["id"]}, **kw).to_list(None):
                matches.append((name, row))
        if len(matches) != 1:
            raise ValueError("Historical row missing or duplicated: " + finding["id"])
        name, observed = matches[0]
        recovered = {**observed, "ip_address": None, "user_agent": None}
        if (observed.get("record_hash") != finding["sealed_hash"] or observed.get("seq") != finding["seq"]
            or audit_chain.compute_record_hash(observed, observed["seq"], observed["prev_hash"]) != finding["observed_content_hash"]
            or audit_chain.compute_record_hash(recovered, observed["seq"], observed["prev_hash"]) != finding["sealed_hash"]):
            raise ValueError("Observed row or original commitment changed: " + finding["id"])
        rows.append({"collection": name, "observed": observed, "before_digest": digest(observed), "sealed_hash": finding["sealed_hash"]})
    public = {"policy_id": POLICY, "tenant_id": source.TENANT, "count": 69,
        "incident_audit_id": receipt["audit_id"], "incident_audit_hash": receipt["audit_hash"],
        "changes": [{"collection": row["collection"], "id": row["observed"]["id"], "seq": row["observed"]["seq"],
            "before_digest": row["before_digest"], "preserved_sealed_hash": row["sealed_hash"],
            "set": {"ip_address": None, "user_agent": None}} for row in rows]}
    return {"public": public, "plan_hash": digest(public), "rows": rows}


async def restore(db, client, *, expected_plan_hash, approval_reference, actor):
    if len(approval_reference.strip()) < 20 or not actor.strip():
        raise ValueError("Explicit operator and human approval reference required")
    request_hash = digest({"plan_hash": expected_plan_hash, "approval_reference": approval_reference, "actor": actor})
    async with await client.start_session() as session:
        async def commit(s):
            old = await db.audit_attribution_restorations.find_one({"_id": POLICY, "tenant_id": source.TENANT}, session=s)
            if old:
                if old["request_hash"] != request_hash:
                    raise ValueError("Restoration already committed with a different request")
                return {**old["result"], "replayed": True}
            current = await plan(db, session=s)
            if current["plan_hash"] != expected_plan_hash:
                raise ValueError("Stale restoration plan; review the exact current observations again")
            now = datetime.now(UTC).isoformat()
            for item in current["rows"]:
                raw = item["observed"]
                evidence = {"_id": POLICY + ":" + raw["id"], "policy_id": POLICY, "tenant_id": source.TENANT,
                    "source_collection": item["collection"], "source_id": raw["id"], "observed_raw_record": raw,
                    "before_digest": item["before_digest"], "preserved_sealed_hash": item["sealed_hash"], "captured_at": now}
                await db.audit_restoration_preimages.insert_one(evidence, session=s)
                updated = await db[item["collection"]].update_one({"_id": raw["_id"], "tenant_id": source.TENANT,
                    "seq": raw["seq"], "record_hash": raw["record_hash"], "prev_hash": raw["prev_hash"],
                    "ip_address": raw.get("ip_address"), "user_agent": raw.get("user_agent")},
                    {"$set": {"ip_address": None, "user_agent": None}}, session=s)
                if updated.modified_count != 1:
                    raise ValueError("Historical observation changed during restoration")
                after = await db[item["collection"]].find_one({"_id": raw["_id"], "tenant_id": source.TENANT}, session=s)
                if after != {**raw, "ip_address": None, "user_agent": None} or audit_chain.compute_record_hash(
                        after, after["seq"], after["prev_hash"]) != raw["record_hash"]:
                    raise ValueError("Restoration changed more than the two approved fields")
            result = {"policy_id": POLICY, "restored_count": 69, "preimage_count": 69, "plan_hash": expected_plan_hash,
                "original_hashes_links_and_sequences_preserved": True, "old_records_resealed": False,
                "financial_records_changed": False, "restored_at": now, "approval_reference": approval_reference, "replayed": False}
            entry = build_audit_entry(actor, source.TENANT, "audit_restoration", POLICY, "historical_audit_attribution_restored")
            entry.update(override_reason=approval_reference, after_snapshot={"result": result, "restoration_plan": current["public"]})
            await audit_chain.append_audit_log(db, entry, session=s, require_chain=True)
            await db.audit_attribution_restorations.insert_one({"_id": POLICY, "tenant_id": source.TENANT,
                "request_hash": request_hash, "result": result, "attestation_id": entry["id"], "attestation_hash": entry["record_hash"]}, session=s)
            return result

        return await session.with_transaction(commit)


async def main(args):
    # Raw access exists only in this offline, fixed-tenant recovery tool. Runtime
    # append-only guards and the verifier are deliberately unchanged.
    from core.database import _raw_db, client

    before = await audit_chain.verify_chain(source.TENANT, limit=50000)
    prior = await _raw_db.audit_attribution_restorations.find_one({"_id": POLICY, "tenant_id": source.TENANT})
    if not prior:
        prepared = await plan(_raw_db)
        expected_ids = {row["id"] for row in prepared["public"]["changes"]}
        if (before.get("truncated") or len(before["breaks"]) != 69 or
            {row.get("id") for row in before["breaks"]} != expected_ids or
            any(row.get("reason") != "content_hash_mismatch" for row in before["breaks"])):
            raise ValueError("Unexpected audit failure set; only the reviewed metadata incident is authorized")
    if not args.apply:
        if prior:
            print(json.dumps({"already_restored": True, "result": prior["result"], "chain_ok": before["ok"]}, ensure_ascii=False))
            return
        prepared = await plan(_raw_db)
        if len(before["breaks"]) != 69 or before.get("truncated"):
            raise ValueError("Unexpected audit verification scope or failure count")
        print(json.dumps({"plan_hash": prepared["plan_hash"], **prepared["public"]}, ensure_ascii=False))
        return
    if not args.expected_plan_hash or args.confirmation != "RESTORE_ONLY_69_DEMO_ATTRIBUTION_FIELDS":
        raise ValueError("Reviewed plan hash and exact confirmation required")
    result = await restore(_raw_db, client, expected_plan_hash=args.expected_plan_hash,
        approval_reference=args.approval_reference or "", actor=args.actor or "")
    after = await audit_chain.verify_chain(source.TENANT, limit=50000)
    print(json.dumps({"result": result, "chain_ok_after": after["ok"], "break_count_after": len(after["breaks"]),
        "verified_through": after.get("as_of_seq")}, ensure_ascii=False))
    if not after["ok"]:
        raise ValueError("Restoration committed but whole retained chain still needs review; do not replay writes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-plan-hash")
    parser.add_argument("--approval-reference")
    parser.add_argument("--actor")
    parser.add_argument("--confirmation")
    asyncio.run(main(parser.parse_args()))
