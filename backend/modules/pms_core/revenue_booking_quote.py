"""Explicit operator-approved pricing. No automatic OTA push or oversell."""
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException

from modules.pms_core.report_money import money, rounded

DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def calendar_day(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except (ValueError, TypeError):
        raise HTTPException(422, 'Geçerli giriş/çıkış tarihi gereklidir') from None


async def quote(database, tenant_id, room_id, arrival, departure, currency):
    if not isinstance(room_id, str) or not room_id.strip() or not isinstance(arrival, str) or not isinstance(departure, str):
        raise HTTPException(422, 'Oda ve tarih alanları metin olmalıdır')
    room = await database.rooms.find_one({'tenant_id': tenant_id, 'id': room_id}, {'_id': 0})
    if not room or room.get('is_active') is False or room.get('is_virtual'):
        raise HTTPException(404, 'Aktif fiziksel oda bulunamadı')
    start, end = calendar_day(arrival), calendar_day(departure)
    nights = (end - start).days
    if not 1 <= nights <= 365:
        raise HTTPException(422, 'Konaklama 1–365 gece olmalıdır')
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise HTTPException(422, 'Para birimi gereklidir')
    currency = currency.upper()
    # Revenue Controls displays prices in the hotel's configured currency.
    # A booking selector must not reinterpret TRY plan numbers as USD/EUR.
    # Read the explicit source, not a cached/silent TRY fallback on failure.
    hotel = await database.hotel_settings.find_one({'tenant_id': tenant_id}, {'_id': 0, 'currency': 1}) or {}
    plan_currency = hotel.get('currency')
    if not isinstance(plan_currency, str) or len(plan_currency) != 3 or not plan_currency.isascii() or not plan_currency.isalpha():
        raise HTTPException(409, 'Gelir planı için otelin kayıtlı para birimini doğrulayın; kur tahmini yapılmaz')
    if currency != plan_currency.upper():
        raise HTTPException(409, f'Gelir planı {plan_currency.upper()} cinsindedir; seçili {currency} için manuel fiyat girin. Otomatik kur çevrimi yapılmaz.')
    settings = await database.revenue_settings.find_one({'tenant_id': tenant_id}, {'_id': 0}) or {}
    kind = str(room.get('room_type_id') or room.get('type_id') or room.get('room_type') or room.get('type') or '').strip()
    hurdle = (settings.get('hurdle_rates') or {}).get(kind) or {}
    by_day = (settings.get('day_pricing') or {}).get(kind) or {}
    rows = []
    try:
        minimum = money(hurdle.get('min_rate') or 0) if hurdle.get('active') is True else Decimal('0')
        minimum_stay = by_day.get(DAYS[start.weekday()], {}).get('min_stay', 1)
        if type(minimum_stay) is not int or not 1 <= minimum_stay <= 365:
            raise ValueError
        if nights < minimum_stay:
            raise HTTPException(409, f'Giriş günü için en az {minimum_stay} gece gereklidir')
        for index in range(nights):
            day = start + timedelta(days=index)
            row = by_day.get(DAYS[day.weekday()]) or {}
            raw = row['rate'] if 'rate' in row else hurdle.get('bar')
            if isinstance(raw, bool) or raw is None:
                raise ValueError
            rate = money(raw)
            if rate <= 0 or minimum < 0 or rate != money(rounded(rate)) or minimum != money(rounded(minimum)):
                raise ValueError
            rate = max(rate, minimum)
            if rate > Decimal('1000000000'):
                raise ValueError
            rows.append({'date': day.isoformat(), 'amount': rounded(rate)})
    except (ValueError, TypeError, ArithmeticError, AttributeError):
        raise HTTPException(409, 'Bu oda/tarihler için geçerli pozitif BAR/gün fiyatı ve minimum konaklama planını kaydedin') from None
    result = {'room_id': room_id, 'check_in': start.isoformat(), 'check_out': end.isoformat(),
        'currency': currency, 'daily_rates': rows, 'total_amount': rounded(sum(money(row['amount']) for row in rows)),
        'min_stay': minimum_stay, 'source': 'revenue_controls', 'provider_write': False,
        'currency_confirmation_required': True}
    fingerprint = {**result, 'hurdle': hurdle, 'day_pricing': by_day}
    result['quote_hash'] = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return result


async def accept_quote(database, tenant_id, room_id, arrival, departure, currency, amount, expected_hash):
    result = await quote(database, tenant_id, room_id, arrival, departure, currency)
    try:
        if isinstance(amount, bool) or amount is None:
            raise ValueError
        agrees = money(amount) == money(result['total_amount'])
    except (ValueError, ArithmeticError, TypeError):
        raise HTTPException(422, 'Geçerli rezervasyon tutarı gereklidir') from None
    if expected_hash != result['quote_hash'] or not agrees:
        raise HTTPException(409, 'Gelir planı veya rezervasyon tutarı değişti; fiyatı yeniden hesaplayın')
    return result
