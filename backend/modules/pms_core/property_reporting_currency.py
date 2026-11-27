"""Read-only property-currency reporting at original posting-day rates.

Never calls a live conversion API, inserts rates, or rewrites source ledgers.
Missing rates make an affected metric unavailable, rather than a partial zero.
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from modules.pms_core.report_money import currency_code, money, rounded


def positive(value):
    try:
        number = money(value)
        return number if number > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def source_day(source):
    for field in ("business_date", "date", "charge_date", "payment_date", "posted_at", "created_at"):
        value = str(source.get(field) or "")[:10]
        try:
            if date.fromisoformat(value).isoformat() == value:
                return value
        except ValueError:
            pass
    return ""


class HistoricalRates:
    def __init__(self, base_currency, rates=(), valuations=()):
        self.currency = currency_code(base_currency, "")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Property reporting currency is required")
        self.rates = sorted(rates, key=lambda row: (str(row.get("effective_date") or ""),
            str(row.get("created_at") or ""), str(row.get("id") or "")), reverse=True)
        # The loader supplies only sealed, posted valuations, newest first.
        self.valuations = list(valuations)

    def quote(self, code, day, source=None):
        code = currency_code(code, "")
        if code == self.currency:
            return Decimal(1), {"kind": "property_currency", "date": day}
        source = source or {}
        if currency_code(source.get("reporting_currency"), "") == self.currency:
            native = positive(abs(money(source.get("amount") or 0)))
            recorded = positive(abs(money(source.get("reporting_amount") or 0)))
            if native and recorded:
                return recorded / native, {"kind": "recorded_reporting_value",
                    "date": source.get("exchange_rate_date") or day, "id": source.get("id")}
        recorded_code = currency_code(source.get("reporting_currency"), "")
        if recorded_code and recorded_code not in {code, self.currency}:
            native = positive(abs(money(source.get("amount") or 0)))
            recorded = positive(abs(money(source.get("reporting_amount") or 0)))
            if native and recorded:
                recorded_day = str(source.get("exchange_rate_date") or day)[:10]
                leg = self.quote(recorded_code, recorded_day,
                    {key: source[key] for key in ("id", "posted_at", "created_at") if key in source})
                if leg:
                    return recorded / native * leg[0], {"kind": "recorded_reporting_value_cross",
                        "date": recorded_day, "id": source.get("id"), "via": recorded_code, "leg": leg[1]}
        if not day:
            return None
        for valuation in self.valuations:
            if valuation.get("business_date") != day:
                continue
            common = currency_code(valuation.get("base_currency"), "")
            rates = valuation.get("rates_to_try") if common == "TRY" else valuation.get("rates_to_base")
            rates = {**(rates or {}), common: 1}
            left, right = positive(rates.get(code)), positive(rates.get(self.currency))
            if left and right:
                return left / right, {"kind": "sealed_posting_valuation", "date": day,
                    "id": valuation.get("journal_id"), "reference": valuation.get("reference")}
        def pair(left, right):
            for row in self.rates:
                effective = str(row.get("effective_date") or "")[:10]
                if not effective or effective > day:
                    continue
                # A later, backdated rate cannot replace a transaction-time value.
                cutoff = str(source.get("posted_at") or source.get("created_at") or "")
                if cutoff and str(row.get("created_at") or "") > cutoff:
                    continue
                if (currency_code(row.get("from_currency"), ""), currency_code(row.get("to_currency"), "")) == (left, right):
                    rate = positive(row.get("rate"))
                    if rate:
                        return rate, {"kind": "dated_property_rate", "date": effective, "id": row.get("id")}
            return None
        direct = pair(code, self.currency)
        if direct:
            return direct
        inverse = pair(self.currency, code)
        if inverse:
            return Decimal(1) / inverse[0], {**inverse[1], "inverse": True}
        # A property may maintain all dated rates against one accounting
        # currency. Two explicit historical legs prove a cross rate too.
        def leg(left, right):
            direct_leg = pair(left, right)
            if direct_leg:
                return direct_leg
            inverse_leg = pair(right, left)
            return (Decimal(1) / inverse_leg[0], {**inverse_leg[1], "inverse": True}) if inverse_leg else None
        common_codes = sorted({currency_code(row.get(field), "") for row in self.rates
            for field in ("from_currency", "to_currency")} - {"", code, self.currency})
        for common in common_codes:
            left, right = leg(code, common), leg(self.currency, common)
            if left and right:
                return left[0] / right[0], {"kind": "dated_property_cross_rate", "date": day,
                    "via": common, "legs": [left[1], right[1]]}
        return None


class PropertyAccumulator:
    def __init__(self, rates):
        self.rates = rates
        self.currency = rates.currency
        self.groups = defaultdict(Decimal)
        self.unavailable = set()
        self.issues = []
        self.rate_evidence = {}

    def add(self, metric, value, source):
        if value is None:
            self.unavailable.add(metric)
            return
        amount = money(value)
        if not amount:
            return
        day = source_day(source)
        code = currency_code(source.get("currency"), "")
        quote = self.rates.quote(code, day, source)
        if quote is None:
            self.unavailable.add(metric)
            issue = {"id": source.get("id"), "date": day, "currency": code,
                "reporting_currency": self.currency, "reason": "historical_exchange_rate_missing"}
            if issue not in self.issues:
                self.issues.append(issue)
            return
        rate, evidence = quote
        self.groups[(metric, day, code, rate)] += amount
        self.rate_evidence[(day, code, rate)] = evidence

    def total(self, metric):
        if metric in self.unavailable:
            return None
        # Match daily GL grouping and rounding before the multi-day total.
        return rounded(sum((money(rounded(value * rate)) for (key, _day, _code, rate), value
            in self.groups.items() if key == metric), Decimal(0)))

    def average(self, metric, denominator):
        total = self.total(metric)
        return None if total is None else rounded(money(total) / denominator) if denominator else 0.0

    def metadata(self):
        return {"currency": self.currency, "rate_basis": "original_posting_business_date",
            "complete": not self.unavailable, "unavailable_metrics": sorted(self.unavailable),
            "missing_rate_count": len(self.issues), "missing_rates": self.issues[:100],
            "rates": [{"source_currency": code, "rate": str(rate), "business_date": day, **evidence}
                for (day, code, rate), evidence in self.rate_evidence.items() if code != self.currency]}


async def load_historical_rates(database, tenant_id, first, last, *, base_currency=None, currencies=None):
    if base_currency is None:
        collection = getattr(database, "hotel_settings", None)
        settings = await collection.find_one({"tenant_id": tenant_id}, {"_id": 0, "currency": 1}) if collection is not None else None
        # Match the application's property setting default; this is a currency
        # selection only, never a fallback exchange rate.
        base_currency = (settings or {}).get("currency") or "TRY"
    book = HistoricalRates(base_currency)
    if currencies is not None and not {currency_code(code, "") for code in currencies} - {book.currency}:
        return book
    rates = await database.currency_rates.find({"tenant_id": tenant_id,
        "effective_date": {"$lt": (date.fromisoformat(str(last)) + timedelta(days=1)).isoformat()}}, {"_id": 0}).to_list(None)
    entries = await database.gl_journal_entries.find({"tenant_id": tenant_id, "status": "posted",
        "source": {"$in": ["night_audit", "night_audit_correction"]},
        "source_manifest.valuation.business_date": {"$gte": str(first), "$lte": str(last)}},
        {"_id": 0}).sort("posting_sequence", -1).to_list(None)
    from shared_kernel.gl_posting import verify_journal_entry_hash
    valuations = [{**entry["source_manifest"]["valuation"], "journal_id": entry.get("id")}
        for entry in entries if verify_journal_entry_hash(entry) and not entry.get("reversal_status") == "reversed"]
    return HistoricalRates(base_currency, rates, valuations)
