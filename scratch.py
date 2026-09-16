from decimal import Decimal, ROUND_HALF_UP

def _money_cents(value) -> int:
    try:
        return int(
            (Decimal(str(value or 0)) * 100).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )
    except Exception:
        return 0

print(_money_cents(833.33))
print(_money_cents(833.3333333333334))
