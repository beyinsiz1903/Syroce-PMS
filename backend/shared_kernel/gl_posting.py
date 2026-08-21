"""
Shared kernel — Genel Muhasebe (GL) posting çekirdeği
=====================================================
Çift-taraflı (double-entry) yevmiye fişi gönderimi ve mizan (trial balance)
hesabı. Domain'ler arası coupling olmadan paylaşılabilsin diye shared_kernel'de
tutulur (örn. accounting GL router + hr bordro köprüsü aynı çekirdeği kullanır).

Değişmezler:
  * Her fiş dengeli olmalı: sum(debit) == sum(credit) > 0.
  * Her satır debit XOR credit (>0) olmalı; ikisi birden olmaz.
  * Her account_code tenant'ın hesap planında (gl_accounts) AKTİF olmalı.
  * idempotency_key verilirse aynı anahtarla ikinci post yeni fiş yaratmaz
    (partial-unique index + DuplicateKeyError → mevcut fiş döner). Fail-closed:
    index kurulamazsa yükseltir (sessiz çift-post YOK).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from shared_kernel.gl_periods import GLPeriodError, assert_gl_period_open, normalize_posting_date
from shared_kernel.pos_idem import ensure_compound_unique

# Hesap tipleri ve normal bakiye yönü.
ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
_NORMAL_DEBIT = {"asset", "expense"}
_NORMAL_CREDIT = {"liability", "equity", "revenue"}

_CENT = Decimal("0.01")
logger = logging.getLogger("shared_kernel.gl_posting")


class GLPostingError(ValueError):
    """Geçersiz yevmiye fişi (denge/satır/COA ihlali)."""


def normal_balance(account_type: str) -> str:
    if account_type in _NORMAL_DEBIT:
        return "debit"
    if account_type in _NORMAL_CREDIT:
        return "credit"
    raise GLPostingError(f"Geçersiz hesap tipi: {account_type}")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def ensure_gl_idem_index(db) -> None:
    """gl_journal_entries idempotency index (fail-closed)."""
    await ensure_compound_unique(
        db.gl_journal_entries,
        [("tenant_id", 1), ("idempotency_key", 1)],
        partial_filter={"idempotency_key": {"$type": "string"}},
        name="ux_gl_journal_idem",
    )


async def _allocate_journal_sequence(db, tenant_id: str, fiscal_year: int, entry_id: str, now: str) -> tuple[int, str]:
    """Reserve a monotonic tenant/year journal ordinal with a durable trace.

    A reservation is written before the journal insert. If a concurrent
    idempotent request wins, the losing reservation is marked ``void`` rather
    than disappearing as an unexplained gap.
    """
    counter_id = f"gl-journal-counter:{tenant_id}:{fiscal_year}"
    counter = await db.gl_counters.find_one_and_update(
        {"_id": counter_id, "tenant_id": tenant_id},
        {
            "$inc": {"value": 1},
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "fiscal_year": fiscal_year,
                "created_at": now,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    sequence = int(counter["value"])
    reservation_id = f"gl-journal-sequence:{tenant_id}:{fiscal_year}:{sequence:08d}"
    await db.gl_sequence_reservations.insert_one(
        {
            "_id": reservation_id,
            "id": reservation_id,
            "tenant_id": tenant_id,
            "fiscal_year": fiscal_year,
            "sequence": sequence,
            "entry_id": entry_id,
            "status": "reserved",
            "created_at": now,
            "updated_at": now,
        }
    )
    return sequence, reservation_id


async def _mark_sequence_reservation(db, tenant_id: str, reservation_id: str, status: str, now: str, **extra) -> None:
    try:
        await db.gl_sequence_reservations.update_one(
            {"_id": reservation_id, "tenant_id": tenant_id},
            {"$set": {"status": status, "updated_at": now, **extra}},
        )
    except Exception as exc:
        # The reservation remains visibly ``reserved`` and can be reconciled;
        # never mask the journal insert result after money has been posted.
        logger.warning("GL sequence reservation status update failed: %s", exc)


def _money_to_minor(value: object) -> int:
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise GLPostingError("Geçersiz parasal tutar") from exc
    if not amount.is_finite():
        raise GLPostingError("Parasal tutar sonlu olmalıdır")
    if abs(amount) > Decimal("999999999999999.99"):
        raise GLPostingError("Parasal tutar izin verilen sınırı aşıyor")
    return int((amount.quantize(_CENT, rounding=ROUND_HALF_UP) * 100).to_integral_exact())


def _minor_to_float(value: int) -> float:
    return float(Decimal(value) / 100)


def _normalize_lines(lines: list[dict]) -> tuple[list[dict], float, float]:
    if not lines:
        raise GLPostingError("Fiş satırı yok")
    out: list[dict] = []
    total_debit_minor = total_credit_minor = 0
    for idx, ln in enumerate(lines):
        code = (ln.get("account_code") or "").strip()
        if not code:
            raise GLPostingError(f"Satır {idx}: hesap kodu zorunlu")
        debit_minor = _money_to_minor(ln.get("debit", 0))
        credit_minor = _money_to_minor(ln.get("credit", 0))
        if debit_minor < 0 or credit_minor < 0:
            raise GLPostingError(f"Satır {idx}: negatif tutar")
        if (debit_minor > 0) == (credit_minor > 0):
            raise GLPostingError(f"Satır {idx}: debit XOR credit (>0) olmalı")
        total_debit_minor += debit_minor
        total_credit_minor += credit_minor
        currency = (ln.get("currency") or "").strip().upper() or None
        foreign_amount = ln.get("foreign_amount")
        exchange_rate = ln.get("exchange_rate")
        foreign_amount_minor = None
        normalized_rate = None
        if currency:
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise GLPostingError(f"Satır {idx}: geçersiz para birimi")
            if currency in {"TRY", "TRL"}:
                raise GLPostingError(f"Satır {idx}: yabancı para alanları TRY için kullanılamaz")
            if foreign_amount is None or exchange_rate is None:
                raise GLPostingError(f"Satır {idx}: yabancı tutar ve kur zorunludur")
            foreign_amount_minor = _money_to_minor(foreign_amount)
            try:
                rate_decimal = Decimal(str(exchange_rate))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise GLPostingError(f"Satır {idx}: geçersiz döviz kuru") from exc
            if not rate_decimal.is_finite() or rate_decimal <= 0:
                raise GLPostingError(f"Satır {idx}: döviz kuru pozitif olmalıdır")
            normalized_rate = str(rate_decimal.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
            expected_base_minor = int(
                (Decimal(foreign_amount_minor) * rate_decimal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            base_minor = debit_minor or credit_minor
            if abs(expected_base_minor - base_minor) > 1:
                raise GLPostingError(f"Satır {idx}: yabancı tutar × kur TL tutarıyla uyuşmuyor")
        elif foreign_amount is not None or exchange_rate is not None:
            raise GLPostingError(f"Satır {idx}: yabancı tutar ve kur için para birimi zorunludur")
        out.append(
            {
                "line_no": idx,
                "account_code": code,
                "account_name": (ln.get("account_name") or "").strip() or None,
                "debit": _minor_to_float(debit_minor),
                "credit": _minor_to_float(credit_minor),
                "debit_minor": debit_minor,
                "credit_minor": credit_minor,
                "memo": (ln.get("memo") or "").strip() or None,
                "currency": currency,
                "foreign_amount": _minor_to_float(foreign_amount_minor) if foreign_amount_minor is not None else None,
                "foreign_amount_minor": foreign_amount_minor,
                "exchange_rate": normalized_rate,
            }
        )
    if total_debit_minor <= 0:
        raise GLPostingError("Toplam tutar sıfır")
    if total_debit_minor != total_credit_minor:
        raise GLPostingError(
            f"Fiş dengesiz: debit={_minor_to_float(total_debit_minor)} credit={_minor_to_float(total_credit_minor)}"
        )
    return out, _minor_to_float(total_debit_minor), _minor_to_float(total_credit_minor)


async def post_journal_entry(
    db,
    tenant_id: str,
    *,
    date: str | None,
    memo: str,
    lines: list[dict],
    source: str = "manual",
    source_ref: str | None = None,
    actor: str = "system",
    idempotency_key: str | None = None,
    reverses_entry_id: str | None = None,
    reversal_reason: str | None = None,
) -> dict:
    """Dengeli yevmiye fişini doğrular, COA'ya göre zenginleştirir ve yazar.

    Döner: yazılan (veya idempotent mevcut) fiş dökümanı (_id'siz).
    """
    posting_date = normalize_posting_date(date)
    norm_lines, tot_debit, tot_credit = _normalize_lines(lines)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "date": posting_date,
                "memo": memo,
                "lines": norm_lines,
                "source": source,
                "source_ref": source_ref,
                "reverses_entry_id": reverses_entry_id,
                "reversal_reason": reversal_reason,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    # An exact retry must remain idempotent even after its period is closed.
    # Return the already-posted entry before evaluating the current lock state.
    if idempotency_key:
        await ensure_gl_idem_index(db)
        existing = await db.gl_journal_entries.find_one(
            {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
            {"_id": 0},
        )
        if existing:
            existing_fingerprint = existing.get("idempotency_fingerprint")
            if existing_fingerprint and existing_fingerprint != fingerprint:
                raise GLPostingError("Idempotency anahtarı farklı bir fiş içeriğiyle yeniden kullanılamaz")
            return existing

    try:
        period = await assert_gl_period_open(db, tenant_id, posting_date, actor=actor)
    except GLPeriodError as exc:
        raise GLPostingError(str(exc)) from exc

    # COA doğrulama — tüm hesaplar aktif olmalı; ad COA'dan doldurulur.
    codes = sorted({ln["account_code"] for ln in norm_lines})
    accts = await db.gl_accounts.find({"tenant_id": tenant_id, "code": {"$in": codes}}, {"_id": 0}).to_list(1000)
    acct_by_code = {a["code"]: a for a in accts}
    for code in codes:
        a = acct_by_code.get(code)
        if not a:
            raise GLPostingError(f"Hesap planında yok: {code}")
        if not a.get("active", True):
            raise GLPostingError(f"Hesap pasif: {code}")
    for ln in norm_lines:
        if not ln.get("account_name"):
            ln["account_name"] = acct_by_code[ln["account_code"]].get("name")

    now = _now_iso()
    entry_id = str(uuid.uuid4())
    fiscal_year = int(period.get("fiscal_year") or posting_date[:4])
    sequence, reservation_id = await _allocate_journal_sequence(db, tenant_id, fiscal_year, entry_id, now)
    doc = {
        "id": entry_id,
        "tenant_id": tenant_id,
        "entry_no": f"YEV-{fiscal_year}-{sequence:08d}",
        "posting_sequence": sequence,
        "sequence_scope": f"{tenant_id}:{fiscal_year}",
        "sequence_reservation_id": reservation_id,
        "date": posting_date,
        "period_id": period.get("id"),
        "fiscal_year": period.get("fiscal_year"),
        "period_no": period.get("period_no"),
        "memo": memo,
        "lines": norm_lines,
        "total_debit": tot_debit,
        "total_credit": tot_credit,
        "total_debit_minor": _money_to_minor(tot_debit),
        "total_credit_minor": _money_to_minor(tot_credit),
        "source": source,
        "source_ref": source_ref,
        "status": "posted",
        "idempotency_key": idempotency_key,
        "idempotency_fingerprint": fingerprint if idempotency_key else None,
        "created_at": now,
        "created_by": actor,
    }
    if reverses_entry_id:
        doc["reverses_entry_id"] = reverses_entry_id
        doc["reversal_reason"] = (reversal_reason or "").strip() or None
    try:
        await db.gl_journal_entries.insert_one(dict(doc))
    except DuplicateKeyError:
        await _mark_sequence_reservation(
            db,
            tenant_id,
            reservation_id,
            "void",
            _now_iso(),
            void_reason="idempotency_race",
        )
        if idempotency_key:
            existing = await db.gl_journal_entries.find_one(
                {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
                {"_id": 0},
            )
            if existing:
                return existing
        raise
    except Exception:
        await _mark_sequence_reservation(
            db,
            tenant_id,
            reservation_id,
            "void",
            _now_iso(),
            void_reason="journal_insert_failed",
        )
        raise
    await _mark_sequence_reservation(
        db,
        tenant_id,
        reservation_id,
        "posted",
        _now_iso(),
        entry_no=doc["entry_no"],
    )
    doc.pop("_id", None)
    return doc


async def compute_trial_balance(db, tenant_id: str, as_of: str | None = None) -> dict:
    """Posted fişlerden mizan üretir (opsiyonel as_of tarihine kadar)."""
    q: dict = {"tenant_id": tenant_id, "status": "posted"}
    if as_of:
        q["date"] = {"$lte": as_of}
    entries = await db.gl_journal_entries.find(q, {"_id": 0}).to_list(100000)

    agg: dict[str, dict] = {}
    for e in entries:
        for ln in e.get("lines", []):
            code = ln.get("account_code")
            row = agg.setdefault(code, {"debit_minor": 0, "credit_minor": 0, "name": ln.get("account_name")})
            debit_minor = ln.get("debit_minor")
            credit_minor = ln.get("credit_minor")
            row["debit_minor"] += int(debit_minor) if debit_minor is not None else _money_to_minor(ln.get("debit", 0))
            row["credit_minor"] += int(credit_minor) if credit_minor is not None else _money_to_minor(ln.get("credit", 0))

    accts = await db.gl_accounts.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)
    type_by_code = {a["code"]: a.get("type") for a in accts}
    name_by_code = {a["code"]: a.get("name") for a in accts}
    normal_balance_by_code = {
        a["code"]: a.get("normal_balance") or normal_balance(a.get("type")) for a in accts
    }

    rows = []
    total_debit_balance_minor = total_credit_balance_minor = 0
    for code in sorted(agg):
        debit_minor = agg[code]["debit_minor"]
        credit_minor = agg[code]["credit_minor"]
        net_minor = debit_minor - credit_minor
        debit_balance_minor = net_minor if net_minor > 0 else 0
        credit_balance_minor = -net_minor if net_minor < 0 else 0
        total_debit_balance_minor += debit_balance_minor
        total_credit_balance_minor += credit_balance_minor
        rows.append(
            {
                "account_code": code,
                "account_name": name_by_code.get(code) or agg[code].get("name") or code,
                "account_type": type_by_code.get(code),
                "normal_balance": normal_balance_by_code.get(code),
                "total_debit": _minor_to_float(debit_minor),
                "total_credit": _minor_to_float(credit_minor),
                "debit_balance": _minor_to_float(debit_balance_minor),
                "credit_balance": _minor_to_float(credit_balance_minor),
                "debit_balance_minor": debit_balance_minor,
                "credit_balance_minor": credit_balance_minor,
            }
        )
    return {
        "as_of": as_of,
        "rows": rows,
        "totals": {
            "debit_balance": _minor_to_float(total_debit_balance_minor),
            "credit_balance": _minor_to_float(total_credit_balance_minor),
            "debit_balance_minor": total_debit_balance_minor,
            "credit_balance_minor": total_credit_balance_minor,
            "balanced": total_debit_balance_minor == total_credit_balance_minor,
        },
    }


async def compute_income_statement(
    db,
    tenant_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Return revenue/expense activity for a date range using minor units."""
    query: dict = {"tenant_id": tenant_id, "status": "posted"}
    if start or end:
        date_query: dict = {}
        if start:
            date_query["$gte"] = normalize_posting_date(start)
        if end:
            date_query["$lte"] = normalize_posting_date(end)
        query["date"] = date_query
    entries = await db.gl_journal_entries.find(query, {"_id": 0}).to_list(100000)
    accounts = await db.gl_accounts.find(
        {"tenant_id": tenant_id, "type": {"$in": ["revenue", "expense"]}},
        {"_id": 0},
    ).to_list(5000)
    account_by_code = {account["code"]: account for account in accounts}
    activity: dict[str, dict[str, int]] = {}
    for entry in entries:
        for line in entry.get("lines", []):
            code = line.get("account_code")
            account = account_by_code.get(code)
            if not account:
                continue
            row = activity.setdefault(code, {"debit_minor": 0, "credit_minor": 0})
            debit_minor = line.get("debit_minor")
            credit_minor = line.get("credit_minor")
            row["debit_minor"] += int(debit_minor) if debit_minor is not None else _money_to_minor(line.get("debit", 0))
            row["credit_minor"] += int(credit_minor) if credit_minor is not None else _money_to_minor(line.get("credit", 0))

    revenue_rows = []
    expense_rows = []
    total_revenue_minor = total_expense_minor = 0
    for code in sorted(activity):
        account = account_by_code[code]
        amounts = activity[code]
        if account.get("type") == "revenue":
            amount_minor = amounts["credit_minor"] - amounts["debit_minor"]
            total_revenue_minor += amount_minor
            target = revenue_rows
        else:
            amount_minor = amounts["debit_minor"] - amounts["credit_minor"]
            total_expense_minor += amount_minor
            target = expense_rows
        target.append(
            {
                "account_code": code,
                "account_name": account.get("name") or code,
                "amount": _minor_to_float(amount_minor),
                "amount_minor": amount_minor,
                "normal_balance": account.get("normal_balance") or normal_balance(account.get("type")),
                "is_contra": (account.get("normal_balance") or normal_balance(account.get("type")))
                != normal_balance(account.get("type")),
            }
        )
    net_income_minor = total_revenue_minor - total_expense_minor
    return {
        "start": start,
        "end": end,
        "revenue": revenue_rows,
        "expenses": expense_rows,
        "totals": {
            "revenue": _minor_to_float(total_revenue_minor),
            "revenue_minor": total_revenue_minor,
            "expenses": _minor_to_float(total_expense_minor),
            "expenses_minor": total_expense_minor,
            "net_income": _minor_to_float(net_income_minor),
            "net_income_minor": net_income_minor,
        },
    }


async def compute_balance_sheet(db, tenant_id: str, *, as_of: str | None = None) -> dict:
    """Return assets = liabilities + equity + current earnings."""
    trial = await compute_trial_balance(db, tenant_id, as_of=as_of)
    sections = {"assets": [], "liabilities": [], "equity": []}
    totals_minor = {"assets": 0, "liabilities": 0, "equity": 0}
    section_by_type = {"asset": "assets", "liability": "liabilities", "equity": "equity"}
    for row in trial["rows"]:
        section = section_by_type.get(row.get("account_type"))
        if not section:
            continue
        if section == "assets":
            amount_minor = row["debit_balance_minor"] - row["credit_balance_minor"]
        else:
            amount_minor = row["credit_balance_minor"] - row["debit_balance_minor"]
        sections[section].append(
            {
                "account_code": row["account_code"],
                "account_name": row["account_name"],
                "amount": _minor_to_float(amount_minor),
                "amount_minor": amount_minor,
                "normal_balance": row.get("normal_balance") or normal_balance(row.get("account_type")),
                "is_contra": (row.get("normal_balance") or normal_balance(row.get("account_type")))
                != normal_balance(row.get("account_type")),
            }
        )
        totals_minor[section] += amount_minor

    income = await compute_income_statement(db, tenant_id, end=as_of)
    current_earnings_minor = income["totals"]["net_income_minor"]
    right_side_minor = totals_minor["liabilities"] + totals_minor["equity"] + current_earnings_minor
    difference_minor = totals_minor["assets"] - right_side_minor
    return {
        "as_of": as_of,
        **sections,
        "current_earnings": {
            "amount": _minor_to_float(current_earnings_minor),
            "amount_minor": current_earnings_minor,
        },
        "totals": {
            "assets": _minor_to_float(totals_minor["assets"]),
            "liabilities": _minor_to_float(totals_minor["liabilities"]),
            "equity": _minor_to_float(totals_minor["equity"]),
            "liabilities_and_equity": _minor_to_float(right_side_minor),
            "difference": _minor_to_float(difference_minor),
            "balanced": difference_minor == 0,
        },
    }
