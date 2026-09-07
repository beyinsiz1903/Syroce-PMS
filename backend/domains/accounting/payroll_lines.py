"""Build v2 journal lines from immutable payroll snapshots, never current rates."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException


def amount(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError
        return result.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(409, "Bordro tutarı eksik veya geçersiz; yeni revizyon hazırlayın") from None


def detailed_payroll_lines(run, mapping):
    rows = run.get("rows") or []
    if not rows:
        raise HTTPException(409, "Bordro satırları eksik")
    totals = dict.fromkeys(("gross", "net", "tax", "sgk", "employer", "advance", "other"), Decimal(0))
    for row in rows:
        if row.get("calculation_mode") != "statutory_2026" or not row.get("tax_calculation", {}).get("employer_scheme"):
            raise HTTPException(409, "İşveren primi ve gerçek matrahı eksik personel var; ücret anlaşmasını doğrulayıp taslağı yeniden hesaplayın")
        gross, net = amount(row.get("gross_pay")), amount(row.get("net_salary"))
        tax = amount(row.get("income_tax")) + amount(row.get("stamp_tax"))
        employee = amount(row.get("sgk_employee")) + amount(row.get("unemployment"))
        employer = amount(row.get("sgk_employer")) + amount(row.get("unemployment_employer"))
        advance = sum((amount(x.get("amount")) for x in row.get("line_items", []) if x.get("kind") == "advance"), Decimal(0))
        other = sum((amount(x.get("amount")) for x in row.get("line_items", []) if x.get("kind") == "deduction"), Decimal(0))
        if gross != net + tax + employee + advance + other:
            raise HTTPException(409, "Bordro kesinti/net mutabakatı tutmuyor; aktarım yapılmadı")
        if amount(row.get("employer_contributions")) != employer or amount(row.get("employer_cost")) != gross + employer:
            raise HTTPException(409, "İşveren maliyeti mutabakatı tutmuyor")
        for key, value in {"gross": gross, "net": net, "tax": tax, "sgk": employee + employer,
                           "employer": employer, "advance": advance, "other": other}.items():
            totals[key] += value
    summary = run.get("summary") or {}
    if amount(summary.get("total_gross")) != totals["gross"] or amount(summary.get("total_net")) != totals["net"]:
        raise HTTPException(409, "Bordro özeti ve satır toplamları uyuşmuyor")
    if totals["gross"] <= 0:
        raise HTTPException(400, "Brüt tutar sıfır; post edilemez")
    specifications = [
        ("wage_expense_code", "gross", "debit", "Ücret gideri"),
        ("employer_expense_code", "employer", "debit", "İşveren SGK ve işsizlik gideri (teşviksiz)"),
        ("net_payable_code", "net", "credit", "Personele net ödenecek"),
        ("withholding_payable_code", "tax", "credit", "Gelir ve damga vergisi"),
        ("sgk_payable_code", "sgk", "credit", "SGK ve işsizlik işçi + işveren"),
        ("advance_receivable_code", "advance", "credit", "Personel avans mahsubu"),
        ("other_deductions_code", "other", "credit", "Diğer net kesinti karşılığı"),
    ]
    if mapping.get("sgk_payable_code") == mapping.get("withholding_payable_code"):
        raise HTTPException(409, "SGK ve vergi hesapları ayrı olmalı")
    lines = []
    for field, key, side, memo in specifications:
        if totals[key]:
            code = (mapping.get(field) or "").strip()
            if not code:
                raise HTTPException(409, f"Bordro hesap eşlemesi eksik: {field}")
            lines.append({"account_code": code, side: float(totals[key]), "memo": memo})
    return lines
