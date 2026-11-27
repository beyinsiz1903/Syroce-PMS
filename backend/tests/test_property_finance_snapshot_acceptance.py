from datetime import date

from modules.pms_core.property_finance_snapshot import property_finance_snapshot
from tests.test_property_currency_reporting_acceptance import DAY, seed

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


def payload():
    return {"pending_ar": {"complete": True, "overdue_invoices_count": 1, "source_issues": []},
        "todays_collections": {}, "mtd_collections": {}, "accounting_invoices": {"pending_count": 1}}


async def test_finance_cards_share_posting_values_without_reducing_ar_by_cash_fx(ledger_db):
    await seed(ledger_db)
    await ledger_db.payments.update_one({"id": "paid"}, {"$set": {"reporting_amount": 600}})
    folios = await ledger_db.folios.find({}, {"_id": 0}).to_list(None)
    payments = await ledger_db.payments.find({}, {"_id": 0}).to_list(None)
    charges = await ledger_db.folio_charges.find({}, {"_id": 0}).to_list(None)
    result = await property_finance_snapshot(ledger_db, "A", payload(),
        [{"folio": folios[0], "currency": "USD", "balance": 20}], folios, payments, payments, charges,
        [], date.fromisoformat(DAY), date.fromisoformat(DAY), "TRY")
    assert result["pending_ar"]["by_currency"]["TRY"]["total"] == 1000
    assert result["todays_collections"]["amount"] == result["mtd_collections"]["amount"] == 600
    assert result["mtd_collections"]["revenue_by_currency"] == {"TRY": 1500}
    assert result["mtd_collections"]["collection_rate_percentage"] == 40
    assert result["accounting_invoices"]["by_currency"] == {"TRY": 0}


async def test_unproven_foreign_account_balance_is_unavailable_not_added_or_offset(ledger_db):
    await seed(ledger_db)
    result = await property_finance_snapshot(ledger_db, "A", payload(),
        [{"folio": {"id": "cari:A"}, "account_key": "cari:A", "currency": "EUR", "balance": 20, "age_days": 10},
         {"folio": {"id": "native"}, "currency": "TRY", "balance": 100}], [], [], [], [], [],
        date.fromisoformat(DAY), date.fromisoformat(DAY), "TRY")
    assert result["pending_ar"]["total"] is None
    assert result["pending_ar"]["by_currency"]["TRY"]["0-30_days"] is None
    assert result["pending_ar"]["complete"] is False
    assert result["pending_ar"]["source_issues"][-1]["id"] == "cari:A"


async def test_eur_property_and_invoice_uses_invoice_day_not_current_day(ledger_db):
    await seed(ledger_db)
    await ledger_db.currency_rates.insert_many([
        {"tenant_id": "A", "effective_date": DAY, "from_currency": "USD", "to_currency": "EUR", "rate": 2},
        {"tenant_id": "A", "effective_date": "2026-11-27", "from_currency": "USD", "to_currency": "EUR", "rate": 3},
    ])
    result = await property_finance_snapshot(ledger_db, "A", payload(), [], [], [], [], [],
        [{"id": "invoice", "currency": "USD", "total": 30, "amount_paid": 10, "invoice_date": DAY}],
        date.fromisoformat(DAY), date.fromisoformat(DAY), "EUR")
    assert result["accounting_invoices"]["pending_total"] == 40
    assert result["accounting_invoices"]["by_currency"] == {"EUR": 40}


async def test_company_aging_merges_valued_currencies_but_counts_folios_once(ledger_db):
    from modules.pms_core.property_company_aging import property_company_aging
    await seed(ledger_db)
    folios = await ledger_db.folios.find({}, {"_id": 0}).to_list(None)
    folios[0]["company_id"] = "c"
    other = {"id": "native", "company_id": "c"}
    positions = [{"folio": folios[0], "currency": "USD", "balance": 20}, {"folio": other, "currency": "TRY", "balance": 100}]
    template = {"company_name": "Company", "aging": {"0-7 days": 0, "8-14 days": 0, "15-30 days": 0, "30+ days": 0}, "source": "company_folio"}
    result = await property_company_aging(ledger_db, "A", {"complete": True, "aging_complete": True}, positions, folios,
        {("c", "USD"): template, ("c", "TRY"): template}, date.fromisoformat(DAY), "TRY")
    assert result["total_ar_by_currency"] == {"TRY": 1100}
    assert result["company_count"] == 1 and len(result["companies"]) == 1
    assert result["companies"][0]["folio_count"] == 2
    assert result["companies"][0]["aging"]["30+ days"] == 1100


async def test_explicit_account_allocations_keep_each_debits_original_rate(ledger_db):
    from modules.pms_core.cari_receivable_reporting import account_positions
    from modules.pms_core.property_company_aging import property_company_aging
    await seed(ledger_db)
    await ledger_db.currency_rates.insert_one({"tenant_id": "A", "effective_date": "2026-11-13", "from_currency": "USD", "to_currency": "TRY", "rate": 60})
    account = {"id": "a", "name": "Company", "company_id": "c", "currency": "USD", "balance": 70}
    rows = [{"id": key, "cari_account_id": "a", "transaction_type": "charge", "currency": "USD", "amount": 50,
        "business_date": day, "due_date": day} for key, day in [("a1", DAY), ("a2", "2026-11-13")]]
    credit = {"id": "paid", "cari_account_id": "a", "transaction_type": "payment", "currency": "USD", "amount": 30,
        "allocations": [{"transaction_id": "a1", "amount": 25}, {"transaction_id": "a2", "amount": 5}]}
    positions, failed, _ = account_positions([account], [*rows, credit], source="cari_accounts", fallback_currency="TRY", today=date(2026, 11, 14))
    assert not failed
    for position in positions:
        position["folio"] = {"id": position["document_id"], "company_id": "c"}
    template = {"company_name": "Company", "aging": {"0-7 days": 0, "8-14 days": 0, "15-30 days": 0, "30+ days": 0}, "source": "cari_accounts"}
    result = await property_company_aging(ledger_db, "A", {"complete": True, "aging_complete": True}, positions, [],
        {("cari_accounts:a", "USD"): template}, date(2026, 11, 14), "TRY")
    assert result["total_ar"] == 3950  # remaining 25 USD at 50 + 45 USD at 60
    assert result["companies"][0]["aging"]["0-7 days"] == 3950
    assert {row["rate"] for row in result["currency_policy"]["rates"]} == {"50", "60"}
