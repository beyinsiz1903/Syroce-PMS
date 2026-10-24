"""Immutable received-money evidence for the existing TRY cashier drawer.

The ledger amount, received banknotes and TRY cashier value are different
quantities. Never label a USD/EUR ledger amount as TRY or invent an FX rate.
"""
from decimal import Decimal

from fastapi import HTTPException

from modules.pms_core.report_money import currency_code, money, rounded


def cashier_values(payment):
    try:
        ledger = currency_code(payment.get("currency"), "TRY")
        received = currency_code(payment.get("received_currency"), ledger)
        amount = abs(money(payment.get("amount")))
        original = abs(money(payment.get("received_amount") if payment.get("received_amount") is not None else amount))
        rate = money(payment.get("exchange_rate") if payment.get("exchange_rate") is not None else 1)
        if amount <= 0 or original <= 0 or rate <= 0:
            raise ValueError
        if amount != money(rounded(amount)) or original != money(rounded(original)):
            raise ValueError
        if ledger == received:
            if amount != original or rate != 1:
                raise ValueError
        # Existing FoliosTab wire contract: 1 ledger unit = rate received units.
        elif payment.get("exchange_rate") is None or abs(money(rounded(amount * rate)) - original) > Decimal(".01"):
            raise ValueError
        if ledger == "TRY":
            drawer_amount = amount
        elif received == "TRY":
            drawer_amount = original
        else:
            if payment.get("received_to_try_rate") is not None:
                received_to_try = money(payment["received_to_try_rate"])
                if received_to_try <= 0:
                    raise ValueError
                drawer_amount = money(rounded(original * received_to_try))
            elif payment.get("reporting_currency") == "TRY" and payment.get("reporting_amount") is not None:
                drawer_amount = money(payment["reporting_amount"])
            else:
                raise HTTPException(422, "Dövizli folyo için alınan dövizin TL kasa kurunu girin; varsayılan 1:1 kur kullanılmaz.")
        if drawer_amount <= 0:
            raise ValueError
    except (ArithmeticError, ValueError, TypeError):
        raise HTTPException(422, "Alınan tutar, para birimi ve uygulanan kur folyo tutarıyla uyuşmalı") from None
    payment["reporting_currency"] = "TRY"
    payment["reporting_amount"] = rounded(drawer_amount)
    return {"amount": rounded(drawer_amount), "currency": received,
        "original_amount": float(original), "fx_rate": float(drawer_amount / original),
        "extra": {"ledger_currency": ledger, "ledger_amount": float(amount),
            "received_currency": received, "received_amount": float(original),
            "ledger_exchange_rate": float(rate), "exchange_rate_date": payment.get("business_date")}}
