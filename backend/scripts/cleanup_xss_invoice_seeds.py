"""One-off cleanup: scrub legacy XSS payloads sitting in invoice/folio rows.

Earlier security probes inserted strings like '<img src=x onerror=alert(3)>'
into billing_name / billing_tax_id / customer_name / customer_address fields.
Output is sanitized at render time, but the raw values still live in MongoDB.
This script rewrites those fields with the sanitized text so the DB itself is clean.

Usage:
    python -m backend.scripts.cleanup_xss_invoice_seeds [--dry-run] [--tenant <id>]
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.database import db  # noqa: E402

from core.sanitize import sanitize_plaintext  # noqa: E402  — prod helper


SUSPECT = re.compile(r"<\s*(?:script|img|svg|iframe|body|onerror|onload|on\w+\s*=)", re.IGNORECASE)
COLLECTIONS = [
    ("accounting_invoices", ["billing_name", "billing_tax_id", "customer_name",
                             "customer_tax_office", "customer_address", "notes"]),
    ("invoices", ["customer_name", "customer_email", "notes"]),
    ("folios", ["guest_name", "company_name", "notes"]),
    ("guests", ["first_name", "last_name", "address", "notes"]),
    ("bookings", ["guest_name", "notes", "special_requests"]),
]


async def scan(dry_run: bool, tenant: str | None) -> dict:
    summary: dict = {}
    for coll, fields in COLLECTIONS:
        q: dict = {}
        if tenant:
            q["tenant_id"] = tenant
        q["$or"] = [{f: {"$regex": SUSPECT.pattern, "$options": "i"}} for f in fields]
        cursor = db[coll].find(q)
        cleaned = 0
        async for doc in cursor:
            updates = {}
            for f in fields:
                v = doc.get(f)
                if isinstance(v, str) and SUSPECT.search(v):
                    updates[f] = sanitize_plaintext(v, max_length=500)
            if updates:
                cleaned += 1
                if not dry_run:
                    await db[coll].update_one({"_id": doc["_id"]}, {"$set": updates})
        summary[coll] = cleaned
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Sadece raporla, yazma")
    parser.add_argument("--tenant", default=None, help="Tek tenant'a sınırla")
    args = parser.parse_args()
    summary = await scan(dry_run=args.dry_run, tenant=args.tenant)
    print("=" * 60)
    print(f"XSS payload cleanup ({'DRY RUN' if args.dry_run else 'APPLIED'})")
    print("=" * 60)
    for coll, n in summary.items():
        print(f"  {coll:25s} -> {n} kayıt temizlendi")
    print(f"  TOPLAM                  -> {sum(summary.values())} kayıt")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
