"""Sharding readiness audit — shard-key index coverage + tenant_id query scan.

Task #366. The actual sharding operation (config servers, mongos,
``sh.shardCollection``, balancer) is an Atlas/DBA infrastructure job and is
explicitly OUT OF SCOPE here. This script does the *preparation* audit that
proves the code is "shard-ready" BEFORE that migration:

  1. Shard-key index coverage — for every collection the strategy doc
     (``docs/DATABASE_SHARDING_STRATEGY.md``) plans to shard, verify a
     compound index whose prefix matches the recommended shard key (leading
     ``tenant_id``) exists. Missing coverage is reported, never created.

  2. Query shard-compatibility — a static scan that flags hot read paths
     issued directly against the *raw* (un-scoped) database handle on a
     shardable collection WITHOUT a ``tenant_id`` filter. On a sharded
     cluster those queries fan out to every shard (scatter-gather). Reads
     that go through the tenant-aware proxy (``db``) auto-inject
     ``tenant_id`` and are therefore shard-routable by construction, so the
     scan only inspects the ``_raw_db`` escape hatch.

  3. Readiness summary — a PASS / REVIEW / FAIL verdict the operator can use
     as the go/no-go reference for the real sharding migration.

This is a READ-ONLY audit. It never creates/drops indexes, never mutates
data, and never triggers live sharding.

Usage
-----
    # Full audit (index coverage needs a reachable cluster; query scan is static)
    python backend/scripts/audit_shard_readiness.py

    # Static query scan only — no DB needed (CI / offline)
    python backend/scripts/audit_shard_readiness.py --query-only

    # Treat REVIEW (warnings) as failure for a deploy/CI gate
    python backend/scripts/audit_shard_readiness.py --strict

Exit codes
----------
    0 — PASS or REVIEW (code is shard-ready, or only operator-review warnings)
    1 — FAIL (a BLOCKER: a shardable collection has NO tenant_id-leading
        index, which would force scatter-gather and cannot be cleanly
        sharded) — or REVIEW under --strict
    2 — usage/connection error when a live index audit was requested

Machine-parseable summary tail:
    SUMMARY blockers=N warnings=M info=K verdict=PASS|REVIEW|FAIL
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── Recommended shard keys (verbatim from DATABASE_SHARDING_STRATEGY.md §2) ──
# Each value is the ordered shard-key spec: list of (field, direction).
SHARD_KEY_SPEC: dict[str, list[tuple[str, int]]] = {
    "bookings": [("tenant_id", 1), ("check_in", -1)],
    "guests": [("tenant_id", 1), ("email", 1)],
    "rooms": [("tenant_id", 1)],
    "folios": [("tenant_id", 1), ("created_at", -1)],
    "audit_logs": [("tenant_id", 1), ("timestamp", -1)],
    "tasks": [("tenant_id", 1)],
}

# The strategy doc names a `tasks` collection, but the codebase has no such
# collection — operational task data lives in `housekeeping_tasks` (front-of-
# house task board) and `task_queue` (background job poller). Audit the real
# collections behind the doc's logical name.
COLLECTION_ALIASES: dict[str, list[str]] = {
    "tasks": ["housekeeping_tasks", "task_queue"],
}

# Collections the static query scan inspects for un-scoped raw reads.
QUERY_SCAN_COLLECTIONS: set[str] = {
    "bookings", "guests", "rooms", "folios",
    "audit_logs", "pms_audit_trail",
    "housekeeping_tasks", "task_queue",
}

# Read operations whose first/pipeline argument carries the query filter.
READ_OPS: set[str] = {"find", "find_one", "count_documents", "distinct", "aggregate"}

# The un-scoped database handles. Reads through these bypass the tenant-aware
# proxy and so are the only scatter-gather risk on a sharded cluster.
RAW_DB_NAMES: set[str] = {"_raw_db"}

# Directory names skipped by the static scan (out of production scope per
# threat_model.md: tests, scripts, e2e harnesses, vendored code).
_SKIP_DIRS: set[str] = {
    "tests", "scripts", "e2e", "e2e-business", "e2e-smoke",
    ".venv", "venv", "node_modules", "__pycache__", ".git",
    "migrations", "seeds",
}


# ── Findings model (mirrors verify_exely_whitelist.py) ───────────────────


@dataclass
class Findings:
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def block(self, msg: str) -> None:
        self.blockers.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.info.append(msg)

    @property
    def verdict(self) -> str:
        if self.blockers:
            return "FAIL"
        if self.warnings:
            return "REVIEW"
        return "PASS"


# ── Index coverage (pure logic — unit-testable without a DB) ─────────────


@dataclass
class CollIndexResult:
    logical: str                      # doc-named collection (e.g. "tasks")
    resolved: list[str]               # real collection(s) audited
    present: bool                     # any resolved collection exists live
    tenant_leading: list[str]         # index names leading with tenant_id
    shardkey_by_field: list[str]      # index names whose prefix == shard fields
    shardkey_exact: list[str]         # ... and direction also matches
    status: str                       # READY | READY_TENANT_ONLY | MISSING | ABSENT
    notes: list[str] = field(default_factory=list)


def _first_field(keylist: list) -> str | None:
    """Leading field name of an index key spec, or None if empty."""
    if not keylist:
        return None
    head = keylist[0]
    # index_information() yields [(field, direction), ...]; tolerate lists too.
    return head[0] if isinstance(head, (list, tuple)) else None


def _field_names(keylist: list) -> list[str]:
    out: list[str] = []
    for k in keylist:
        if isinstance(k, (list, tuple)) and k:
            out.append(k[0])
    return out


def _norm_pairs(keylist: list) -> list[tuple[str, object]]:
    return [
        (k[0], k[1]) for k in keylist
        if isinstance(k, (list, tuple)) and len(k) >= 2
    ]


def evaluate_collection(
    logical: str,
    shard_key: list[tuple[str, int]],
    index_maps: dict[str, dict[str, list]],
) -> CollIndexResult:
    """Decide shard readiness for one logical collection.

    ``index_maps`` maps each *resolved* collection name to
    ``{index_name: key_spec}`` (key_spec as returned by
    ``index_information()['key']``). A resolved collection mapped to ``None``
    means it does not exist on the live cluster.
    """
    resolved = COLLECTION_ALIASES.get(logical, [logical])
    shard_fields = [f for f, _ in shard_key]
    shard_pairs = [(f, d) for f, d in shard_key]

    tenant_leading: list[str] = []
    shardkey_by_field: list[str] = []
    shardkey_exact: list[str] = []
    present = False

    for coll in resolved:
        idxs = index_maps.get(coll)
        if idxs is None:
            continue
        present = True
        for name, keylist in idxs.items():
            tag = name if len(resolved) == 1 else f"{coll}.{name}"
            if _first_field(keylist) == "tenant_id":
                tenant_leading.append(tag)
            names = _field_names(keylist)
            if names[: len(shard_fields)] == shard_fields:
                shardkey_by_field.append(tag)
                if _norm_pairs(keylist)[: len(shard_pairs)] == shard_pairs:
                    shardkey_exact.append(tag)

    notes: list[str] = []
    if logical in COLLECTION_ALIASES:
        notes.append(
            f"strateji dokümanı '{logical}' koleksiyonunu listeliyor; kod "
            f"tabanında karşılığı: {', '.join(resolved)}"
        )

    if not present:
        status = "ABSENT"
        notes.append(
            "koleksiyon canlı cluster'da yok (henüz veri yazılmamış olabilir) "
            "— shard öncesi yeniden denetle"
        )
    elif not tenant_leading:
        status = "MISSING"
    elif shardkey_by_field:
        status = "READY"
        if not shardkey_exact:
            notes.append(
                "shard-key alanlarını taşıyan index var ama önerilen yön "
                f"({_fmt_key(shard_key)}) ile birebir değil — sharding anında "
                "tam yönlü shard-key index'i oluşturulmalı"
            )
    else:
        status = "READY_TENANT_ONLY"
        notes.append(
            f"önerilen bileşik shard-key {_fmt_key(shard_key)} hiçbir index'le "
            "desteklenmiyor; tenant_id öncüllü index'ler var → {tenant_id} "
            "shard-key'i için hazır, bileşik için index eklenmeli"
        )

    return CollIndexResult(
        logical=logical,
        resolved=resolved,
        present=present,
        tenant_leading=sorted(set(tenant_leading)),
        shardkey_by_field=sorted(set(shardkey_by_field)),
        shardkey_exact=sorted(set(shardkey_exact)),
        status=status,
        notes=notes,
    )


def _fmt_key(shard_key: list[tuple[str, int]]) -> str:
    inner = ", ".join(f"{f}: {d}" for f, d in shard_key)
    return "{" + inner + "}"


# ── Static query scan (pure AST — unit-testable without a DB) ────────────


@dataclass
class QueryFinding:
    path: str
    lineno: int
    collection: str
    op: str
    scoped: bool          # True if the call's source carries a tenant_id filter
    by_design: bool       # True if it matches a known cross-tenant pattern
    snippet: str


def _collection_of_call(call: ast.Call) -> tuple[str | None, str | None]:
    """Return (collection, op) if ``call`` is a raw-db read, else (None, None).

    Matches ``_raw_db.<coll>.<op>(...)`` and ``_raw_db["<coll>"].<op>(...)``.
    """
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in READ_OPS:
        return None, None
    op = func.attr
    target = func.value  # the collection expression

    coll: str | None = None
    base = None
    if isinstance(target, ast.Attribute):
        coll = target.attr
        base = target.value
    elif isinstance(target, ast.Subscript):
        base = target.value
        idx = target.slice
        if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
            coll = idx.value

    if coll is None or not isinstance(base, ast.Name):
        return None, None
    if base.id not in RAW_DB_NAMES:
        return None, None
    return coll, op


def scan_source_tree(root: Path) -> list[QueryFinding]:
    """Walk production ``*.py`` under ``root`` and flag un-scoped raw reads on
    shardable collections."""
    findings: list[QueryFinding] = []
    for py in sorted(root.rglob("*.py")):
        rel_parts = set(py.relative_to(root).parts)
        if rel_parts & _SKIP_DIRS:
            continue
        try:
            text = py.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(py))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            coll, op = _collection_of_call(node)
            if coll is None or coll not in QUERY_SCAN_COLLECTIONS:
                continue
            segment = ast.get_source_segment(text, node) or ""
            scoped = "tenant_id" in segment
            by_design = (not scoped) and ("guest_id" in segment)
            first_line = segment.strip().splitlines()[0] if segment.strip() else ""
            findings.append(
                QueryFinding(
                    path=str(py.relative_to(root)),
                    lineno=node.lineno,
                    collection=coll,
                    op=op,
                    scoped=scoped,
                    by_design=by_design,
                    snippet=first_line[:140],
                )
            )
    return findings


# ── Live index inspection (read-only) ────────────────────────────────────


async def fetch_index_maps(collections: list[str]) -> dict[str, dict[str, list]]:
    """Read ``index_information()`` for each collection from the configured
    cluster. A collection that does not exist maps to ``None``. Read-only."""
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")
    if not mongo_url:
        raise RuntimeError(
            "MONGO_URL (veya MONGO_ATLAS_URI) tanımlı değil — index denetimi "
            "canlı cluster gerektirir. --query-only ile statik tarama yapın."
        )
    db_name = os.environ.get("DB_NAME", "hotel_pms")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        rawdb = client[db_name]
        existing = set(await rawdb.list_collection_names())
        out: dict[str, dict[str, list]] = {}
        for coll in collections:
            if coll not in existing:
                out[coll] = None  # type: ignore[assignment]
                continue
            info = await rawdb[coll].index_information()
            out[coll] = {name: meta.get("key", []) for name, meta in info.items()}
        return out
    finally:
        client.close()


def _resolved_collection_names() -> list[str]:
    names: list[str] = []
    for logical in SHARD_KEY_SPEC:
        names.extend(COLLECTION_ALIASES.get(logical, [logical]))
    return sorted(set(names))


# ── Reporting ─────────────────────────────────────────────────────────────


def build_findings(
    index_results: list[CollIndexResult] | None,
    query_findings: list[QueryFinding],
) -> Findings:
    f = Findings()

    # 1) Index coverage
    if index_results is None:
        f.warn(
            "Index shard-key denetimi ATLANDI (canlı cluster sorgulanmadı). "
            "Tam hazırlık raporu için MONGO_URL ile --query-only olmadan çalıştır."
        )
    else:
        for r in index_results:
            label = f"{r.logical} (shard-key {_fmt_key(SHARD_KEY_SPEC[r.logical])})"
            if r.status == "MISSING":
                f.block(
                    f"{label}: tenant_id öncüllü HİÇBİR index yok → sorgular "
                    "scatter-gather'a düşer, koleksiyon temiz shard'lanamaz. "
                    f"Denetlenen: {', '.join(r.resolved)}."
                )
            elif r.status == "READY_TENANT_ONLY":
                f.warn(
                    f"{label}: tenant_id öncüllü index var ama önerilen bileşik "
                    "shard-key'i destekleyen index yok — sharding anında bu "
                    "index eklenmeli (ya da {tenant_id} shard-key'i seçilmeli). "
                    f"tenant_id öncüllü: {', '.join(r.tenant_leading) or '-'}."
                )
            elif r.status == "ABSENT":
                f.note(
                    f"{label}: koleksiyon canlı cluster'da yok — "
                    f"{'; '.join(r.notes)}"
                )
            else:  # READY
                detail = f"shard-key index'i: {', '.join(r.shardkey_by_field)}"
                if not r.shardkey_exact:
                    detail += " (alan adıyla; yön birebir değil)"
                f.note(f"{label}: HAZIR — {detail}.")
            for n in r.notes:
                if r.status not in ("ABSENT",):
                    f.note(f"  · {r.logical}: {n}")

    # 2) Query shard-compatibility
    unscoped = [q for q in query_findings if not q.scoped and not q.by_design]
    by_design = [q for q in query_findings if q.by_design]
    scoped = [q for q in query_findings if q.scoped]
    f.note(
        f"Statik sorgu taraması: {len(query_findings)} raw-db okuma "
        f"(_raw_db.<koleksiyon>) bulundu — {len(scoped)} tenant_id'li, "
        f"{len(by_design)} bilinçli cross-tenant (guest_id), "
        f"{len(unscoped)} tenant_id'siz."
    )
    for q in by_design:
        f.note(
            f"  · bilinçli global: {q.path}:{q.lineno} {q.collection}.{q.op} "
            f"(guest-app cross-tenant) → {q.snippet}"
        )
    for q in unscoped:
        f.warn(
            f"tenant_id'siz raw okuma (shard'da scatter-gather): {q.path}:"
            f"{q.lineno} {q.collection}.{q.op} → {q.snippet}"
        )

    return f


def _print_report(f: Findings) -> None:
    print("=== Sharding Hazırlık Denetimi (shard-key index + tenant_id sorgu) ===")
    if f.blockers:
        print(f"\n[BLOCKER] ({len(f.blockers)})")
        for b in f.blockers:
            print(f"  x {b}")
    if f.warnings:
        print(f"\n[WARNING] ({len(f.warnings)})")
        for w in f.warnings:
            print(f"  ! {w}")
    if f.info:
        print(f"\n[INFO] ({len(f.info)})")
        for i in f.info:
            print(f"  - {i}")
    print(
        f"\nSUMMARY blockers={len(f.blockers)} warnings={len(f.warnings)} "
        f"info={len(f.info)} verdict={f.verdict}"
    )


# ── CLI ────────────────────────────────────────────────────────────────────


async def run(query_only: bool) -> Findings:
    backend_root = Path(__file__).resolve().parents[1]
    query_findings = scan_source_tree(backend_root)

    index_results: list[CollIndexResult] | None = None
    if not query_only:
        index_maps = await fetch_index_maps(_resolved_collection_names())
        index_results = [
            evaluate_collection(logical, shard_key, index_maps)
            for logical, shard_key in SHARD_KEY_SPEC.items()
        ]
    return build_findings(index_results, query_findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--query-only",
        action="store_true",
        help="Sadece statik sorgu taraması çalıştır (DB gerektirmez).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="REVIEW (warnings>0) durumunu da hata say — exit 1.",
    )
    args = parser.parse_args(argv)

    try:
        findings = asyncio.run(run(args.query_only))
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # pragma: no cover — connection/runtime guard
        print(f"ERROR: index denetimi başarısız: {e}", file=sys.stderr)
        return 2

    _print_report(findings)
    if findings.blockers:
        return 1
    if args.strict and findings.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
