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

import uuid
from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError

from shared_kernel.pos_idem import ensure_compound_unique

# Hesap tipleri ve normal bakiye yönü.
ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
_NORMAL_DEBIT = {"asset", "expense"}
_NORMAL_CREDIT = {"liability", "equity", "revenue"}

_EPS = 0.005


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


def _normalize_lines(lines: list[dict]) -> tuple[list[dict], float, float]:
    if not lines:
        raise GLPostingError("Fiş satırı yok")
    out: list[dict] = []
    tot_debit = tot_credit = 0.0
    for idx, ln in enumerate(lines):
        code = (ln.get("account_code") or "").strip()
        if not code:
            raise GLPostingError(f"Satır {idx}: hesap kodu zorunlu")
        debit = round(float(ln.get("debit", 0) or 0), 2)
        credit = round(float(ln.get("credit", 0) or 0), 2)
        if debit < 0 or credit < 0:
            raise GLPostingError(f"Satır {idx}: negatif tutar")
        if (debit > 0) == (credit > 0):
            raise GLPostingError(f"Satır {idx}: debit XOR credit (>0) olmalı")
        tot_debit += debit
        tot_credit += credit
        out.append(
            {
                "line_no": idx,
                "account_code": code,
                "account_name": (ln.get("account_name") or "").strip() or None,
                "debit": debit,
                "credit": credit,
                "memo": (ln.get("memo") or "").strip() or None,
            }
        )
    tot_debit = round(tot_debit, 2)
    tot_credit = round(tot_credit, 2)
    if tot_debit <= 0:
        raise GLPostingError("Toplam tutar sıfır")
    if abs(tot_debit - tot_credit) > _EPS:
        raise GLPostingError(f"Fiş dengesiz: debit={tot_debit} credit={tot_credit}")
    return out, tot_debit, tot_credit


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
) -> dict:
    """Dengeli yevmiye fişini doğrular, COA'ya göre zenginleştirir ve yazar.

    Döner: yazılan (veya idempotent mevcut) fiş dökümanı (_id'siz).
    """
    norm_lines, tot_debit, tot_credit = _normalize_lines(lines)

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

    if idempotency_key:
        await ensure_gl_idem_index(db)

    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "entry_no": f"JE-{(date or now)[:10]}-{uuid.uuid4().hex[:8]}",
        "date": date or now[:10],
        "memo": memo,
        "lines": norm_lines,
        "total_debit": tot_debit,
        "total_credit": tot_credit,
        "source": source,
        "source_ref": source_ref,
        "status": "posted",
        "idempotency_key": idempotency_key,
        "created_at": now,
        "created_by": actor,
    }
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
            row = agg.setdefault(code, {"debit": 0.0, "credit": 0.0, "name": ln.get("account_name")})
            row["debit"] += float(ln.get("debit", 0) or 0)
            row["credit"] += float(ln.get("credit", 0) or 0)

    accts = await db.gl_accounts.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)
    type_by_code = {a["code"]: a.get("type") for a in accts}
    name_by_code = {a["code"]: a.get("name") for a in accts}

    rows = []
    tot_debit_bal = tot_credit_bal = 0.0
    for code in sorted(agg):
        d = round(agg[code]["debit"], 2)
        c = round(agg[code]["credit"], 2)
        net = round(d - c, 2)
        debit_bal = net if net > 0 else 0.0
        credit_bal = -net if net < 0 else 0.0
        tot_debit_bal += debit_bal
        tot_credit_bal += credit_bal
        rows.append(
            {
                "account_code": code,
                "account_name": name_by_code.get(code) or agg[code].get("name") or code,
                "account_type": type_by_code.get(code),
                "total_debit": d,
                "total_credit": c,
                "debit_balance": round(debit_bal, 2),
                "credit_balance": round(credit_bal, 2),
            }
        )
    return {
        "as_of": as_of,
        "rows": rows,
        "totals": {
            "debit_balance": round(tot_debit_bal, 2),
            "credit_balance": round(tot_credit_bal, 2),
            "balanced": abs(tot_debit_bal - tot_credit_bal) <= _EPS,
        },
    }
