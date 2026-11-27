from datetime import date

from modules.pms_core.property_expense_report import property_expense_report

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
DAY = "2026-11-12"
FIRST = date.fromisoformat(DAY)


async def test_expense_report_values_all_sources_at_posting_day_without_mutation(ledger_db):
    await ledger_db.currency_rates.insert_many([
        {"tenant_id": "A", "effective_date": DAY, "from_currency": "USD", "to_currency": "TRY", "rate": 50},
        {"tenant_id": "A", "effective_date": "2026-11-27", "from_currency": "USD", "to_currency": "TRY", "rate": 70}])
    rows = [{"tenant_id": "A", "id": "native", "business_date": DAY, "currency": "TRY", "amount": 100, "category": "food"},
        {"tenant_id": "A", "id": "fx", "expense_date": DAY, "currency": "USD", "total_amount": 20, "category": "food"},
        {"tenant_id": "A", "id": "void", "date": DAY, "voided": True, "amount": 999},
        {"tenant_id": "B", "id": "other", "date": DAY, "amount": 999},
        {"tenant_id": "A", "id": "later", "date": "2026-11-13", "amount": 999}]
    await ledger_db.expenses.insert_many(rows)
    before = await ledger_db.expenses.find_one({"id": "fx"})
    result = await property_expense_report(ledger_db, "A", FIRST, FIRST, "TRY")
    assert result["by_currency"] == {"TRY": 1100}
    assert result["count"] == 2 and result["categories"]["food"]["amount"] == 1100
    assert result["daily_average"] == 1100 and result["top_expense"] == "food"
    assert await ledger_db.expenses.find_one({"id": "fx"}) == before


async def test_missing_fx_never_shows_a_complete_partial_expense_total(ledger_db):
    await ledger_db.expenses.insert_many([
        {"tenant_id": "A", "date": DAY, "currency": "TRY", "amount": 100, "category": "food"},
        {"tenant_id": "A", "date": DAY, "currency": "EUR", "amount": 20, "category": "food"}])
    result = await property_expense_report(ledger_db, "A", FIRST, FIRST, "TRY")
    assert result["by_currency"] == {"TRY": None} and result["categories"]["food"]["amount"] is None
    assert result["top_expense"] is None and result["daily_average"] is None
    assert result["currency_policy"]["missing_rate_count"] == 1


async def test_daily_currency_groups_are_rounded_once(ledger_db):
    await ledger_db.currency_rates.insert_one({"tenant_id": "A", "effective_date": DAY, "from_currency": "USD", "to_currency": "TRY", "rate": 3})
    await ledger_db.expenses.insert_many([{"tenant_id": "A", "date": DAY, "currency": "USD", "amount": 0.005, "category": "food"} for _ in range(2)])
    result = await property_expense_report(ledger_db, "A", FIRST, FIRST, "TRY")
    assert result["total_expenses"] == result["categories"]["food"]["amount"] == 0.03


async def test_empty_eur_property_is_a_verified_eur_zero(ledger_db):
    result = await property_expense_report(ledger_db, "A", FIRST, FIRST, "EUR")
    assert result["by_currency"] == {"EUR": 0} and result["count"] == 0
