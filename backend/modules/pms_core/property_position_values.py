"""Value a remaining account position only from original debit evidence."""
from modules.pms_core.property_reporting_currency import PropertyAccumulator, source_day
from modules.pms_core.report_money import currency_code, money


def property_position_value(position, rates, folio_values, evidence):
    code = currency_code(position["currency"])
    if code == rates.currency:
        return position["balance"]
    if position.get("valuation_parts") is not None:
        parts = position["valuation_parts"]
        if sum((money(part["amount"]) for part in parts), money(0)) != money(position["balance"]):
            return None
        acc = PropertyAccumulator(rates)
        for part in parts:
            source = part["source"]
            source = {**source, "currency": code, "business_date": source.get("business_date") or source.get("transaction_date")}
            acc.add("balance", part["amount"], source)
        evidence.extend({**row, "account_id": position.get("account_key")} for row in acc.metadata()["rates"])
        return acc.total("balance")
    if position.get("valuation_candidates") is not None:
        candidates = [{**row, "currency": code, "business_date": row.get("business_date") or row.get("transaction_date")} for row in position["valuation_candidates"]]
        quotes = [rates.quote(code, source_day(source), source) for source in candidates]
        known = {quote[0] for quote in quotes if quote is not None}
        if not quotes or any(quote is None for quote in quotes) or len(known) != 1:
            return None
        acc = PropertyAccumulator(rates)
        acc.add("balance", position["balance"], candidates[0])
        evidence.extend({**row, "account_id": position.get("account_key")} for row in acc.metadata()["rates"])
        return acc.total("balance")
    return folio_values.get((str(position["folio"].get("id")), code))
