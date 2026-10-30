import { isEffectivePayment } from './folioPayments';

const normalize = value => String(value || '').toLowerCase();
export const folioPayorLabel = folio => ({ guest: 'Misafir', agency: 'Acente', company: 'Şirket', master: 'Ana hesap' }[normalize(folio?.payor_type || folio?.folio_type)] || 'Ödeyen belirtilmemiş');
export const folioCategory = item => {
  const category = normalize(item.charge_category || item.category || item.charge_type);
  if (['room', 'room_charge', 'accommodation'].includes(category)) return 'accommodation';
  if (['food', 'beverage', 'dessert', 'appetizer', 'food_beverage', 'food_and_beverage', 'restaurant', 'room_service', 'pos_fnb'].includes(category)) return 'food_beverage';
  return category;
};
export const folioCategoryLabel = item => ({ accommodation: 'Konaklama', food_beverage: 'Yiyecek ve içecek', minibar: 'Minibar', spa: 'Spa', laundry: 'Çamaşırhane', concierge: 'Concierge', transfer: 'Transfer', parking: 'Otopark', mice: 'Toplantı ve etkinlik', activity: 'Aktivite', function_space: 'Salon kiralama', upsell: 'Ek hizmet teklifi', tax: 'Vergi', city_tax: 'Vergi', other: 'Diğer hizmet' }[folioCategory(item)] || 'Ek hizmet');

export function serviceTimingLabel(item) {
  const date = String(item.service_date || '').slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    const [year, month, day] = date.split('-');
    return `${day}.${month}.${year}${item.service_time ? ` · ${item.service_time}` : ' · saat belirtilmemiş'}${item.service_timing_source === 'pos_order' ? ' (sipariş)' : item.service_timing_source === 'spa_appointment' ? ' (randevu)' : ''}${item.service_timezone === 'UTC' ? ' · UTC' : ''}`;
  }
  if (folioCategory(item) === 'accommodation' && /^\d{4}-\d{2}-\d{2}$/.test(item.business_date || '')) {
    const [year, month, day] = item.business_date.split('-');
    return `${day}.${month}.${year} · konaklama günü`;
  }
  return 'Hizmet tarihi belirtilmemiş';
}

export function folioItemInScope(item, folios, selectedIds) {
  if (item.folio_id) return selectedIds.includes(item.folio_id);
  // Booking-wide legacy entries cannot be assigned to one of several payers
  // by guesswork. Only a single, selected account is unambiguous.
  return folios.length === 1 && selectedIds.includes(folios[0].id);
}

export function buildFolioStatement({ folios = [], charges = [], extraCharges = [], payments = [], booking = {}, property, scope = 'guest', category = 'all', selectedIds = null, audience = 'guest' }) {
  const isGuest = folio => normalize(folio.payor_type || folio.folio_type) === 'guest';
  const matchesScope = folio => scope === 'all' || (scope === 'guest' ? isGuest(folio) : folio.id === scope);
  const selected = folios.filter(folio => matchesScope(folio)
    && (audience === 'internal' || isGuest(folio)));
  const folioIds = selected.map(folio => folio.id);
  const seen = new Set();
  const all = [...charges, ...extraCharges].filter(item => {
    if (item.voided) return false;
    const id = item.id || item.charge_id;
    if (id && seen.has(id)) return false;
    if (id) seen.add(id);
    return true;
  });
  const scoped = all.filter(item => folioItemInScope(item, folios, folioIds));
  const filtered = scoped.filter(item => (category === 'all' || folioCategory(item) === category) && (!selectedIds || selectedIds.includes(item.id || item.charge_id)));
  const partial = category !== 'all' || Boolean(selectedIds && filtered.length !== scoped.length);
  const currency = selected[0]?.currency || booking.currency || 'TRY';
  const code = value => String(value || currency).toUpperCase().replace(/^TL$/, 'TRY');
  const scopedPayments = partial ? [] : payments.filter(item => isEffectivePayment(item) && folioItemInScope(item, folios, folioIds));
  const mixedCurrency = selected.some(folio => code(folio.currency) !== code(currency)) || [...filtered, ...scopedPayments].some(item => code(item.currency) !== code(currency));
  // Only the authenticated, matching property's display name may supplement
  // missing booking metadata (never another tenant's branding in admin views).
  const propertyId = property?.id || property?.tenant_id || property?._id;
  const propertyName = property?.property_name;
  const text = value => typeof value === 'string' && value.trim() ? value : undefined;
  const hotelName = text(booking.hotel_name) || text(booking.property_name) || (booking.tenant_id && propertyId === booking.tenant_id ? text(propertyName) : undefined);
  return {
    charges: filtered, payments: scopedPayments, extra_charges: [], booking,
    currency, mixedCurrency, statement_only: partial, hotel_name: hotelName,
    document_title: partial ? 'Seçili Hizmetler Dökümü' : audience === 'internal' ? 'İç Kullanım Hesap Dökümü' : 'Misafir Hesap Dökümü',
    folio_number: selected.map(folio => folio.folio_number).filter(Boolean).join(', '),
    opening_balance: partial ? 0 : selected.reduce((sum, folio) => sum + Number(folio.opening_balance || 0), 0),
    // A partial statement is NOT a receipt or the booking's remaining debt.
    ...(partial ? {} : { balance: selected.reduce((sum, folio) => sum + Number(folio.balance || 0), 0) }),
    excluded_unassigned: all.filter(item => !item.folio_id && folios.length !== 1).length,
    selected_folio_ids: folioIds,
    selection_note: partial ? 'Yalnız seçili hizmetler gösterilir. Bu döküm genel hesap bakiyesi veya tahsilat belgesi değildir.' : 'Yalnız yukarıda belirtilen hesapların hareketleri gösterilir.',
  };
}
