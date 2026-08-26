"""e-Defter readiness checks and an accountant-transfer source package.

The ZIP produced here is deliberately *not* represented as a GIB e-Defter or
berat.  GIB requires XBRL-GL schema/schematron validation, an approved source
application, a qualified electronic signature or financial seal, and a GIB
berat.  This module prepares deterministic source rows and an integrity
manifest for transfer into that approved workflow without contacting a
provider or signing anything.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from shared_kernel.gl_posting import verify_journal_entry_hash

PERIOD_RE = re.compile(r"^(?P<year>20\d{2})-(?P<month>0[1-9]|1[0-2])$")
ENTRY_NO_RE = re.compile(r"^YEV-(?P<year>20\d{2})-(?P<number>\d{8})$")


class ELedgerSourceError(ValueError):
    """Raised when a source period cannot be parsed or safely packaged."""


def period_bounds(period: str) -> tuple[int, int, str, str]:
    match = PERIOD_RE.fullmatch(period or "")
    if not match:
        raise ELedgerSourceError("Dönem YYYY-AA biçiminde olmalıdır")
    year = int(match.group("year"))
    month = int(match.group("month"))
    last_day = calendar.monthrange(year, month)[1]
    return year, month, f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _minor(line: dict, side: str) -> int:
    stored = line.get(f"{side}_minor")
    if stored is not None:
        return int(stored)
    return int((Decimal(str(line.get(side, 0) or 0)) * 100).quantize(Decimal("1")))


def _safe_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value[:1] in {"=", "+", "-", "@"}:
        return f"'{value}"
    return value


def _csv_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows([[_safe_cell(value) for value in row] for row in rows])
    return output.getvalue().encode("utf-8-sig")


async def preflight_eledger_source(db, tenant_id: str, period: str, settings: dict | None = None) -> dict:
    year, month, start, end = period_bounds(period)
    settings = settings or await db.gl_eledger_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    entries = (
        await db.gl_journal_entries.find(
            {"tenant_id": tenant_id, "date": {"$gte": start, "$lte": end}},
            {"_id": 0},
        )
        .sort("entry_no", 1)
        .to_list(100000)
    )
    accounts = await db.gl_accounts.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)
    period_doc = await db.gl_periods.find_one(
        {"tenant_id": tenant_id, "fiscal_year": year, "period_no": month},
        {"_id": 0},
    )
    reservations = await db.gl_sequence_reservations.find(
        {"tenant_id": tenant_id, "fiscal_year": year},
        {"_id": 0},
    ).to_list(100000)

    blockers: list[dict] = []
    warnings: list[dict] = []
    if not settings:
        blockers.append({"code": "settings_missing", "message": "e-Defter hazırlık bilgileri tanımlanmamış"})
    else:
        taxpayer_id = str(settings.get("taxpayer_id") or "")
        if not re.fullmatch(r"\d{10,11}", taxpayer_id):
            blockers.append({"code": "taxpayer_id_invalid", "message": "VKN/TCKN 10 veya 11 rakam olmalıdır"})
        if not str(settings.get("legal_name") or "").strip():
            blockers.append({"code": "legal_name_missing", "message": "Yasal unvan eksik"})
        if not str(settings.get("source_application_version") or "").strip():
            blockers.append({"code": "source_application_missing", "message": "Kaynak uygulama sürümü eksik"})
        if not str(settings.get("software_approval_reference") or "").strip():
            warnings.append(
                {
                    "code": "software_approval_unverified",
                    "message": "GİB yazılım uyumluluk onayı referansı kayıtlı değil; paket resmi e-Defter değildir",
                }
            )
    if not period_doc:
        blockers.append({"code": "period_missing", "message": "Mali dönem oluşturulmamış"})
    elif period_doc.get("status") != "closed":
        blockers.append({"code": "period_open", "message": "Kaynak paket öncesi mali dönem kapatılmalıdır"})
    if not entries:
        blockers.append({"code": "period_empty", "message": "Seçili dönemde kaynak pakete alınacak yevmiye fişi yok"})

    account_codes = {item.get("code") for item in accounts}
    entry_numbers: list[int] = []
    duplicate_entry_nos: set[str] = set()
    seen_entry_nos: set[str] = set()
    unbalanced_entries: list[str] = []
    missing_account_entries: list[str] = []
    non_posted_entries: list[str] = []
    unsealed_entries: list[str] = []
    integrity_mismatches: list[str] = []
    for entry in entries:
        entry_no = str(entry.get("entry_no") or entry.get("id") or "?")
        if entry_no in seen_entry_nos:
            duplicate_entry_nos.add(entry_no)
        seen_entry_nos.add(entry_no)
        match = ENTRY_NO_RE.fullmatch(entry_no)
        if match and int(match.group("year")) == year:
            entry_numbers.append(int(match.group("number")))
        if entry.get("status") != "posted":
            non_posted_entries.append(entry_no)
        if not entry.get("entry_hash"):
            unsealed_entries.append(entry_no)
        elif not verify_journal_entry_hash(entry):
            integrity_mismatches.append(entry_no)
        debit = sum(_minor(line, "debit") for line in entry.get("lines", []))
        credit = sum(_minor(line, "credit") for line in entry.get("lines", []))
        if debit <= 0 or debit != credit:
            unbalanced_entries.append(entry_no)
        if any(line.get("account_code") not in account_codes for line in entry.get("lines", [])):
            missing_account_entries.append(entry_no)
    if duplicate_entry_nos:
        blockers.append({"code": "duplicate_entry_no", "message": "Yinelenen yevmiye numarası var", "entries": sorted(duplicate_entry_nos)})
    if non_posted_entries:
        blockers.append({"code": "non_posted_entry", "message": "Kesinleşmemiş fişler var", "entries": non_posted_entries[:100]})
    if unsealed_entries:
        blockers.append(
            {
                "code": "legacy_unsealed_entry",
                "message": "Bütünlük mührü bulunmayan eski yevmiye kayıtları var",
                "entries": unsealed_entries[:100],
            }
        )
    if integrity_mismatches:
        blockers.append(
            {
                "code": "journal_integrity_mismatch",
                "message": "İçeriği bütünlük mührüyle uyuşmayan yevmiye kayıtları var",
                "entries": integrity_mismatches[:100],
            }
        )
    if unbalanced_entries:
        blockers.append({"code": "unbalanced_entry", "message": "Borç/alacak dengesi bozuk fişler var", "entries": unbalanced_entries[:100]})
    if missing_account_entries:
        blockers.append({"code": "account_missing", "message": "Hesap planında bulunmayan kod kullanan fişler var", "entries": missing_account_entries[:100]})

    known_sequence_numbers = {int(item["sequence"]) for item in reservations if item.get("sequence") is not None and item.get("status") in {"posted", "reserved", "void"}}
    unexplained_gaps: list[int] = []
    if entry_numbers:
        for sequence_no in range(min(entry_numbers), max(entry_numbers) + 1):
            if sequence_no not in entry_numbers and sequence_no not in known_sequence_numbers:
                unexplained_gaps.append(sequence_no)
    if unexplained_gaps:
        blockers.append(
            {
                "code": "unexplained_sequence_gap",
                "message": "Açıklanmamış yevmiye sıra boşlukları var",
                "sequence_numbers": unexplained_gaps[:100],
            }
        )

    return {
        "period": period,
        "start": start,
        "end": end,
        "ready_for_source_export": not blockers,
        "official_edefter": False,
        "entry_count": len(entries),
        "line_count": sum(len(entry.get("lines", [])) for entry in entries),
        "period_status": (period_doc or {}).get("status") or "missing",
        "blockers": blockers,
        "warnings": warnings,
        "external_requirements": [
            "GİB uyumlu XBRL-GL dönüşümü ve şema/şematron doğrulaması",
            "Uyumluluk onaylı kaynak uygulama",
            "Mali mühür veya güvenli elektronik imza",
            "Berat oluşturma ve GİB onayı",
        ],
    }


async def build_eledger_source_package(db, tenant_id: str, period: str, settings: dict) -> tuple[bytes, dict]:
    preflight = await preflight_eledger_source(db, tenant_id, period, settings=settings)
    if preflight["blockers"]:
        raise ELedgerSourceError("Ön kontrol engelleri giderilmeden kaynak paket üretilemez")

    _, _, start, end = period_bounds(period)
    entries = (
        await db.gl_journal_entries.find(
            {"tenant_id": tenant_id, "status": "posted", "date": {"$gte": start, "$lte": end}},
            {"_id": 0},
        )
        .sort("entry_no", 1)
        .to_list(100000)
    )
    accounts = await db.gl_accounts.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)
    account_by_code = {item.get("code"): item for item in accounts}

    journal_rows: list[list[object]] = []
    ledger = defaultdict(lambda: {"debit_minor": 0, "credit_minor": 0})
    for entry in entries:
        for line_no, line in enumerate(entry.get("lines", []), start=1):
            code = str(line.get("account_code") or "")
            debit_minor = _minor(line, "debit")
            credit_minor = _minor(line, "credit")
            ledger[code]["debit_minor"] += debit_minor
            ledger[code]["credit_minor"] += credit_minor
            journal_rows.append(
                [
                    entry.get("entry_no"),
                    entry.get("date"),
                    line_no,
                    code,
                    line.get("account_name") or (account_by_code.get(code) or {}).get("name"),
                    f"{Decimal(debit_minor) / 100:.2f}",
                    f"{Decimal(credit_minor) / 100:.2f}",
                    line.get("memo") or entry.get("memo"),
                    entry.get("source"),
                    entry.get("source_ref"),
                ]
            )
    ledger_rows = []
    for code in sorted(ledger):
        amounts = ledger[code]
        account = account_by_code.get(code) or {}
        ledger_rows.append(
            [
                code,
                account.get("name"),
                account.get("type"),
                f"{Decimal(amounts['debit_minor']) / 100:.2f}",
                f"{Decimal(amounts['credit_minor']) / 100:.2f}",
            ]
        )

    files = {
        "journal.csv": _csv_bytes(
            ["entry_no", "date", "line_no", "account_code", "account_name", "debit", "credit", "memo", "source", "source_ref"],
            journal_rows,
        ),
        "general_ledger.csv": _csv_bytes(
            ["account_code", "account_name", "account_type", "total_debit", "total_credit"],
            ledger_rows,
        ),
        "README.txt": (
            "Syroce PMS e-Defter kaynak veri paketi\n\n"
            "Bu arşiv GİB e-Defter veya berat değildir. Mali mühür/e-imza içermez ve GİB'e gönderilmemiştir.\n"
            "Veriler uyumluluk onaylı e-Defter yazılımına kontrollü aktarım için hazırlanmıştır.\n"
        ).encode(),
    }
    generated_at = datetime.now(UTC).isoformat()
    manifest = {
        "format": "syroce-eledger-source-v1",
        "official_edefter": False,
        "tenant_id": tenant_id,
        "period": period,
        "generated_at": generated_at,
        "taxpayer_id": settings.get("taxpayer_id"),
        "legal_name": settings.get("legal_name"),
        "source_application": settings.get("source_application"),
        "source_application_version": settings.get("source_application_version"),
        "entry_count": len(entries),
        "line_count": len(journal_rows),
        "files": {name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)} for name, content in files.items()},
        "preflight": preflight,
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue(), manifest
