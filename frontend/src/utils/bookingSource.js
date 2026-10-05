const cleanSource = (value) => String(value || '').trim();

const sourceValue = (booking = {}) => {
  const source = booking.source && typeof booking.source === 'object' ? booking.source : {};
  const primitiveSource = typeof booking.source === 'string' ? booking.source : '';
  return booking.ota_channel || booking.source_channel || booking.channel || booking.booking_source
    || booking.source_system || booking.provider || source.provider || source.channel
    || source.name || primitiveSource || '';
};

const exactLabels = {
  direct: 'Doğrudan', direct_booking: 'Doğrudan', phone: 'Telefon', telephone: 'Telefon',
  walkin: 'Walk-in', walk_in: 'Walk-in', 'walk-in': 'Walk-in', website: 'Web Sitesi',
  web: 'Web Sitesi', online: 'Online', hotelrunner: 'HotelRunner', exely: 'Exely',
  agency: 'Acente', acente: 'Acente', corporate: 'Kurumsal',
};

const brandPatterns = [
  [/booking(?:dot)?com|booking_com|booking/, 'Booking.com'],
  [/hotels(?:dot)?com|hotels_com/, 'Hotels.com'],
  [/expedia/, 'Expedia'], [/agoda/, 'Agoda'], [/airbnb/, 'Airbnb'],
  [/trip(?:dot)?com|trip_com/, 'Trip.com'], [/traveloka/, 'Traveloka'], [/tiket/, 'Tiket.com'],
  [/ostrovok/, 'Ostrovok'], [/zenhotels?/, 'ZenHotels'],
  [/tatilbudur/, 'Tatilbudur'], [/tatilsepeti/, 'Tatilsepeti'], [/odamax/, 'Odamax'],
  [/etstur|etsapi|^ets$/, 'Etstur'], [/setur/, 'Setur'], [/jolly/, 'Jolly'],
  [/touristica/, 'Touristica'], [/anitur/, 'Anı Tur'], [/pronto/, 'Pronto Tour'],
  [/corendon/, 'Corendon'], [/hotelrunner/, 'HotelRunner'], [/exely/, 'Exely'],
];

export const bookingSourceLabel = (booking = {}) => {
  if (booking.agency_name && (booking.agency_id || ['agency', 'acente'].includes(String(booking.source_channel || booking.channel || '').toLowerCase()))) {
    return `Acente · ${booking.agency_name}`;
  }

  const raw = sourceValue(booking);
  if (raw && typeof raw === 'object') return cleanSource(raw.name || raw.label || raw.code) || 'Belirtilmemiş';
  const normalized = cleanSource(raw).toLocaleLowerCase('tr-TR').replace(/[\s.-]+/g, '_');
  if (!normalized) return 'Belirtilmemiş';
  if (exactLabels[normalized]) return exactLabels[normalized];

  const compact = normalized.replace(/[^a-z0-9çğıöşü]/g, '');
  const match = brandPatterns.find(([pattern]) => pattern.test(compact));
  if (match) return match[1];

  return cleanSource(raw);
};

export const rawBookingSource = sourceValue;
