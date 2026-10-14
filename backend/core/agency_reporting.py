"""Never add money expressed in different currencies. No implicit FX conversion."""
import re


def currency_code(value):
    code = str(value or '').strip().upper()
    return code if re.fullmatch(r'[A-Z]{3}', code) else 'UNKNOWN'


def combined_summary(buckets):
    rows = list(buckets.values())
    money = ('gross_revenue', 'commission', 'platform_fee', 'net_to_hotels', 'net_to_hotel')
    return {'bookings': sum(row.get('bookings', 0) for row in rows),
            'cancelled': sum(row.get('cancelled', 0) for row in rows),
            'no_show': sum(row.get('no_show', 0) for row in rows),
            'currency': rows[0]['currency'] if len(rows) == 1 else None,
            **{key: round(rows[0].get(key, 0), 2) if len(rows) == 1 else None for key in money}}
