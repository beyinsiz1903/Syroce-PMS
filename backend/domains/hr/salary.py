"""Versioned Turkish wage calculation. Never infer an employee's opening tax base.

Scope: TRY, 2026, ordinary private-sector 4/a employee, one monthly payment.
Sources and exclusions: docs/qa/hr-salary-agreements.md.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

D = Decimal
CENT = D("0.01")
MIN_WAGE = D("33030")
DAILY_CEILING = D("9909")
MIN_BASE = D("28075.50")
VERSION = "tr-2026-standard-4a-v1"


def money(value):
    return D(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class SalaryAgreement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    unit: Literal["monthly", "hourly"]
    basis: Literal["gross", "net"]
    amount: Decimal = Field(gt=0, le=10000000, decimal_places=2)
    # Explicit period-bound inputs, not defaults masquerading as actual history.
    period_month: str = Field(pattern=r"^2026-(0[1-9]|1[0-2])$")
    opening_tax_base: Decimal = Field(ge=0, le=1000000000, decimal_places=2)
    opening_exemption_base: Decimal = Field(ge=0, le=400000, decimal_places=2)
    minimum_wage_exemption: bool
    insurance_days: int = Field(ge=1, le=30)
    paid_hours: Decimal = Field(gt=0, le=400, decimal_places=2)
    source_note: str = Field(min_length=3, max_length=300)
    standard_4a_confirmed: Literal[True]

    @model_validator(mode="after")
    def check_context(self):
        month = int(self.period_month[-2:])
        if month == 1 and (self.opening_tax_base or self.opening_exemption_base):
            raise ValueError("Ocak açılış matrahları sıfır olmalı; önceki yıl taşınamaz")
        if self.opening_exemption_base > MIN_BASE * (month - 1):
            raise ValueError("Asgari ücret istisna matrahı önceki ayların üst sınırını aşıyor")
        if len(self.source_note.strip()) < 3:
            raise ValueError("Matrahın bordro/belge kaynağını belirtin")
        return self


def tariff(base):
    """2026 GVK103 wage (not non-wage) brackets, unrounded running tax."""
    total, lower = D(0), D(0)
    for upper, rate in [(190000, "0.15"), (400000, "0.20"), (1500000, "0.27"), (5300000, "0.35"), (None, "0.40")]:
        taxable = max(D(0), min(base, D(upper)) - lower) if upper else max(D(0), base - lower)
        total += taxable * D(rate)
        if upper is None or base <= upper:
            break
        lower = D(upper)
    return total


def from_gross(gross, agreement):
    a = agreement
    gross = money(gross)
    # Below-floor wages need employer-paid shortfall handling, not excess employee withholding.
    if gross < MIN_WAGE / 30 * a.insurance_days:
        raise ValueError("Brüt ücret SGK gün tabanının altında; ücret/gün bilgilerini kontrol edin")
    premium_base = min(gross, DAILY_CEILING * a.insurance_days)
    sgk, unemployment = money(premium_base * D(".14")), money(premium_base * D(".01"))
    base = gross - sgk - unemployment
    computed_tax = money(tariff(a.opening_tax_base + base) - tariff(a.opening_tax_base))
    exemption = D(0)
    if a.minimum_wage_exemption:
        exemption = min(computed_tax, money(tariff(a.opening_exemption_base + MIN_BASE) - tariff(a.opening_exemption_base)))
    income_tax = computed_tax - exemption
    stamp = money(max(D(0), gross - (MIN_WAGE if a.minimum_wage_exemption else 0)) * D(".00759"))
    deductions = sgk + unemployment + income_tax + stamp
    return {
        "gross_pay": gross,
        "net_salary": gross - deductions,
        "sgk_employee": sgk,
        "unemployment": unemployment,
        "income_tax": income_tax,
        "stamp_tax": stamp,
        "total_deductions": deductions,
        "tax_deductions": deductions,
        "tax_calculation": {
            "version": VERSION,
            "period_month": a.period_month,
            "opening_tax_base": a.opening_tax_base,
            "current_tax_base": base,
            "closing_tax_base": a.opening_tax_base + base,
            "opening_exemption_base": a.opening_exemption_base,
            "income_tax_before_exemption": computed_tax,
            "income_tax_exemption": exemption,
            "premium_base": premium_base,
            "insurance_days": a.insurance_days,
            "source_note": a.source_note,
        },
    }


def calculate(agreement):
    a = agreement
    target = money(a.amount * (a.paid_hours if a.unit == "hourly" else D(a.insurance_days) / 30))
    if a.basis == "gross":
        return from_gross(target, a)
    # Search cents, not floats; choose a gross giving the promised net to a cent.
    low = int(MIN_WAGE / 30 * a.insurance_days * 100)
    high = max(low, int(target * 300))
    if from_gross(D(low) / 100, a)["net_salary"] > target:
        raise ValueError("Net ücret SGK gün tabanının altında; ücret/gün bilgilerini kontrol edin")
    while low < high:
        mid = (low + high) // 2
        if from_gross(D(mid) / 100, a)["net_salary"] < target:
            low = mid + 1
        else:
            high = mid
    result = from_gross(D(low) / 100, a)
    if abs(result["net_salary"] - target) > CENT:
        raise ValueError("Net/brüt dönüşümü kuruş toleransında çözülemedi")
    return result


def json_values(value):
    """Decimal-safe wire/BSON projection; all calculations above remain Decimal."""
    if isinstance(value, D):
        return float(value)
    if isinstance(value, dict):
        return {k: json_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_values(v) for v in value]
    return value
