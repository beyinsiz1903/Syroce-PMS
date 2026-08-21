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
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pymongo.errors import DuplicateKeyError

from shared_kernel.gl_periods import GLPeriodError, assert_gl_period_open, normalize_posting_date
from shared_kernel.pos_idem import ensure_compound_unique

# Hesap tipleri ve normal bakiye yönü.
ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
_NORMAL_DEBIT = {"asset", "expense"}
_NORMAL_CREDIT = {"liability", "equity", "revenue"}

_CENT = Decimal("0.01")


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
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "entry_no": f"JE-{posting_date}-{uuid.uuid4().hex[:8]}",
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
        existing = await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "idempotency_key": idempotency_key}, {"_id": 0})
        if existing:
            return existing
        raise
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
