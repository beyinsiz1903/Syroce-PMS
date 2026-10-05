/**
 * User-facing screens must not fall back to database identifiers. API
 * responses do not always contain a readable number/name, so centralise the
 * safe fallbacks used by operational views here.
 */
export function firstReadableValue(record, fields, fallback = '—') {
  for (const field of fields) {
    const value = record?.[field];
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim();
    }
  }
  return fallback;
}

export const roomLabel = (record, fallback = 'Oda bilgisi yok') =>
  firstReadableValue(record, ['room_number', 'room_name', 'room_label'], fallback);

export const reservationLabel = (record, fallback = 'Rezervasyon kaydı') =>
  firstReadableValue(record, [
    'reservation_number',
    'reservation_no',
    'booking_reference',
    'booking_code',
    'confirmation_number',
  ], fallback);

export const folioLabel = (record, fallback = 'Folyo kaydı') =>
  firstReadableValue(record, ['folio_number', 'folio_no', 'folio_reference'], fallback);

export const guestLabel = (record, fallback = 'Misafir') =>
  firstReadableValue(record, ['guest_name', 'name', 'full_name'], fallback);
