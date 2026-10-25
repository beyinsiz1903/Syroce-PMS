"""Read-only account debt, separate from the folio credit used to transfer it.

Never infer which invoice an unallocated account payment settled. Its remaining
debt is visible in an unknown-age bucket rather than assigned a guessed age.
Account projections without matching sources remain explicitly incomplete.
"""
from collections import defaultdict

from modules.pms_core.receivable_reporting import report_day
from modules.pms_core.report_money import currency_code, money, rounded

DEBITS = {"charge", "transfer_in"}
CREDITS = {"payment", "adjustment", "transfer_out"}


def account_id(account):
    return str(account.get("id") or account.get("account_id") or account.get("legacy_id") or account.get("_id") or "")


def account_positions(accounts, transactions, *, source, fallback_currency, today):
    """Use durable debt sources once, with tenant filtering owned by the loader."""
    positions, failures, issues = [], set(), []
    grouped = defaultdict(list)
    field = "cari_account_id" if source == "cari_accounts" else "account_id"
    for row in transactions:
        grouped[str(row.get(field) or "")].append(row)
    seen = set()
    for account in accounts:
        key = account_id(account)
        public_key = source + ":" + key
        if not key or key in seen:
            failures.add(public_key)
            issues.append({"account_id": public_key, "reason": "missing_or_ambiguous_account_identity"})
            continue
        seen.add(key)
        aliases = {str(account[k]) for k in ("id", "account_id", "legacy_id", "_id") if account.get(k) is not None}
        rows = [row for alias in aliases for row in grouped.get(alias, [])]
        by_currency, credits, dates = defaultdict(list), set(), defaultdict(list)
        source_ids = set()
        try:
            native = currency_code(account.get("currency"), fallback_currency)
            opening = money(account.get("opening_balance") or 0)
            if opening:
                by_currency[native].append(opening)
                dates[native].append(None)
            for row in rows:
                if row.get("voided") or row.get("deleted") or row.get("status") not in {None, "completed", "posted"}:
                    continue
                identity = str(row.get("id") or row.get("_id") or "")
                if not identity or identity in source_ids:
                    raise ValueError("Missing/duplicate account transaction identity")
                source_ids.add(identity)
                kind = str(row.get("transaction_type") or "").strip().lower()
                amount = money(row.get("amount"))
                if kind not in DEBITS | CREDITS or amount <= 0:
                    raise ValueError("Unknown account transaction amount/type")
                code = currency_code(row.get("currency") or native)
                by_currency[code].append(amount if kind in DEBITS else -amount)
                if kind in CREDITS:
                    credits.add(code)
                else:
                    # Missing dates are never substituted with the report day.
                    dates[code].append(report_day(row.get("due_date") or row.get("business_date") or row.get("transaction_date") or row.get("created_at")))
            ledger = {code: money(rounded(sum(values))) for code, values in by_currency.items()}
            cached_value = account.get("current_balance") if account.get("current_balance") is not None else account.get("balance")
            if cached_value is not None:
                cached = money(rounded(cached_value))
                nonzero = {code: value for code, value in ledger.items() if value}
                if any(code != native for code in nonzero) or cached != ledger.get(native, 0):
                    failures.add(public_key)
                    issues.append({"account_id": public_key, "reason": "account_projection_differs_from_sources",
                        "account_currency": native, "account_balance": rounded(cached),
                        "source_balance_by_currency": {code: rounded(value) for code, value in ledger.items()}})
                    # A legacy nonzero projection must not disappear because
                    # its historical movements were never migrated.
                    if not rows and not opening and cached > 0:
                        ledger[native] = cached
                        dates[native].append(None)
            name = str(account.get("name") or account.get("account_name") or account.get("company_name") or "Cari hesap kaydı")
            for code, balance in ledger.items():
                if balance <= 0:
                    continue
                anchors = dates.get(code, [])
                # Charge-only sources can be aged independently. Once an
                # unallocated credit exists, claiming an invoice age is unsafe.
                age_unknown = code in credits or not anchors or any(day is None for day in anchors) or public_key in failures
                if age_unknown:
                    chunks = [(balance, None)]
                else:
                    chunks = [(value, anchor) for value, anchor in zip(by_currency[code], anchors, strict=True) if value > 0]
                for index, (value, anchor) in enumerate(chunks):
                    positions.append({"currency": code, "balance": rounded(value), "source": source,
                        "account_id": key, "account_key": public_key, "company_id": account.get("company_id"),
                        "company_name": name, "corporate_code": account.get("corporate_code") or key,
                        "age_unknown": anchor is None, "age_days": max((today - anchor).days, 0) if anchor else None,
                        "document_id": f"{public_key}:{code}:{index}", "transaction_count": len(source_ids),
                        "source_complete": public_key not in failures})
        except (ValueError, TypeError, ArithmeticError, KeyError):
            failures.add(public_key)
            issues.append({"account_id": public_key, "reason": "invalid_account_source"})
    orphaned = sorted(set(grouped) - {str(account[k]) for account in accounts for k in ("id", "account_id", "legacy_id", "_id") if account.get(k) is not None})
    for key in orphaned:
        if any(not row.get("voided") and not row.get("deleted") and row.get("status") in {None, "completed", "posted"} for row in grouped[key]):
            public_key = source + ":" + key
            failures.add(public_key)
            issues.append({"account_id": public_key, "reason": "transaction_account_missing"})
    return positions, sorted(failures), issues


async def load_account_positions(database, tenant_id, *, fallback_currency, today):
    positions, failures, issues = [], [], []
    identities = {}
    for source, transaction_source in (("cari_accounts", "cari_transactions"), ("city_ledger_accounts", "city_ledger_transactions")):
        accounts = await getattr(database, source).find({"tenant_id": tenant_id}).to_list(None)
        transactions = await getattr(database, transaction_source).find({"tenant_id": tenant_id}).to_list(None)
        for account in accounts:
            key = account_id(account)
            if key in identities:
                failures.extend([source + ":" + key, identities[key] + ":" + key])
                issues.append({"account_id": key, "reason": "ambiguous_cross_collection_account_identity"})
            identities[key] = source
        rows, failed, source_issues = account_positions(accounts, transactions,
            source=source, fallback_currency=fallback_currency, today=today)
        positions.extend(rows)
        failures.extend(failed)
        issues.extend(source_issues)
    return positions, sorted(set(failures)), issues
