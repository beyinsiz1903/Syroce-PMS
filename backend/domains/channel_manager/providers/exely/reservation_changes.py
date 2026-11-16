"""Operator-facing differences, never raw provider XML, contacts or card data."""

from decimal import Decimal, InvalidOperation


def _text(value):
    return ' '.join(str(value or '').split())[:160] or '—'


def _money(value, currency):
    if value is None:
        return '—'
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return '—'
        return f'{amount:.2f} {_text(currency)}'
    except (InvalidOperation, ValueError):
        return '—'


def reservation_changes(before, after):
    """Compare the previous accepted provider snapshot before it is replaced.

    Slot indexes match rooms across reordering. Missing historical baselines
    never become invented zeroes. Private free text is signalled, not copied.
    """
    if not before:
        return []
    changes = []

    def add(label, old, new):
        if old != new:
            changes.append({'label': label, 'from': _text(old), 'to': _text(new)})

    for key, label in [('checkin_date', 'Giriş tarihi'), ('checkout_date', 'Çıkış tarihi'),
                       ('total_rooms', 'Oda sayısı'), ('total_guests', 'Misafir sayısı'),
                       ('guest_name', 'Rezervasyon sahibi')]:
        add(label, before.get(key), after.get(key))
    states = {'confirmed': 'Onaylandı', 'cancelled': 'İptal edildi', 'new': 'Yeni'}
    add('Rezervasyon durumu', states.get(before.get('state'), before.get('state')),
        states.get(after.get('state'), after.get('state')))
    add('Rezervasyon toplamı', _money(before.get('total'), before.get('currency')),
        _money(after.get('total'), after.get('currency')))
    for key, label in [('guest_email', 'E-posta'), ('guest_phone', 'Telefon'), ('note', 'Özel istek / not')]:
        if (before.get(key) or '') != (after.get(key) or ''):
            changes.append({'label': label, 'from': 'Önceki kayıt', 'to': 'Güncellendi'})
    old_rooms = {str(r.get('index_number') or i): r for i, r in enumerate(before.get('rooms') or [])}
    new_rooms = {str(r.get('index_number') or i): r for i, r in enumerate(after.get('rooms') or [])}
    for slot in sorted(old_rooms.keys() | new_rooms.keys()):
        old, new = old_rooms.get(slot), new_rooms.get(slot)
        prefix = f'Oda {slot}'
        if old is None or new is None:
            add(prefix, 'Mevcut' if old else 'Yok', 'Mevcut' if new else 'Kaldırıldı')
            continue
        for key, label in [('room_type_code', 'oda tipi kodu'), ('rate_plan_code', 'tarife kodu'),
                           ('adults', 'yetişkin'), ('children', 'çocuk'), ('guest_name', 'misafir'),
                           ('check_in', 'giriş'), ('check_out', 'çıkış')]:
            add(f'{prefix} · {label}', old.get(key), new.get(key))
        add(f'{prefix} · konaklama tutarı', _money(old.get('amount'), before.get('currency')),
            _money(new.get('amount'), after.get('currency')))
        old_rates = {str(rate.get('date') or ''): rate.get('amount') for rate in old.get('daily_rates') or []}
        new_rates = {str(rate.get('date') or ''): rate.get('amount') for rate in new.get('daily_rates') or []}
        for day in sorted(old_rates.keys() | new_rates.keys()):
            add(f'{prefix} · {day} gecelik fiyat', _money(old_rates.get(day), before.get('currency')),
                _money(new_rates.get(day), after.get('currency')))
        old_names = [_text(g.get('name') or g.get('guest_name') or ' '.join(filter(None, [g.get('guest_firstname'), g.get('guest_lastname')]))) for g in old.get('guests') or []]
        new_names = [_text(g.get('name') or g.get('guest_name') or ' '.join(filter(None, [g.get('guest_firstname'), g.get('guest_lastname')]))) for g in new.get('guests') or []]
        add(f'{prefix} · konaklayanlar', ', '.join(old_names), ', '.join(new_names))
    if before.get('services') != after.get('services'):
        changes.append({'label': 'Ek hizmetler', 'from': 'Önceki hizmetler', 'to': 'Güncellendi'})
    old_pay, new_pay = before.get('prepayment') or {}, after.get('prepayment') or {}
    if old_pay != new_pay:
        for key, label in [('booking_total', 'Kanal rezervasyon bedeli'), ('remaining_amount', 'Kanalda kalan tutar')]:
            add(label, _money(old_pay.get(key), old_pay.get('booking_currency')),
                _money(new_pay.get(key), new_pay.get('booking_currency')))
        old_totals = {row['currency']: row.get('received_amount') for row in old_pay.get('totals') or []}
        new_totals = {row['currency']: row.get('received_amount') for row in new_pay.get('totals') or []}
        for currency in sorted(old_totals.keys() | new_totals.keys()):
            add('Kanalın bildirdiği ön ödeme', _money(old_totals.get(currency), currency),
                _money(new_totals.get(currency), currency))
        if old_pay.get('payments') != new_pay.get('payments') and old_totals == new_totals:
            changes.append({'label': 'Ön ödeme ayrıntıları', 'from': 'Önceki kayıt', 'to': 'Güncellendi'})
    return changes
