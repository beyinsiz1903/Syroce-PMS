import { normalizeTier } from '@/lib/planCatalog';

// Needs-based hotel creation: the operator says what the hotel does, the
// screen derives the modules and the lowest plan that covers them. Plan scope
// comes from the server catalogue (defaults_by_tier); paid add-ons never raise
// the plan — they are switched on and priced in the quote instead.

export const TIER_ORDER = ['mini', 'basic', 'professional', 'enterprise'];

export const NEEDS = [
  { group: 'Satış', id: 'ota', label: "OTA'lar (Booking, Expedia…)", modules: ['channel_manager'] },
  { group: 'Satış', id: 'agencies', label: 'Acenteler (Acente Extranet)', modules: ['agency_extranet'] },
  { group: 'Satış', id: 'website', label: 'Kendi web sitesinden rezervasyon', modules: ['booking_engine'] },
  // The commercial plan includes pos_basic; POS endpoints use the canonical
  // pos_fnb entitlement. Its explicit Basic SKU grants access, not Pro features.
  { group: 'Tesiste', id: 'restaurant', label: 'Restoran / bar', modules: ['pos_basic', 'pos_fnb_basic'], planModules: ['pos_basic'] },
  { group: 'Tesiste', id: 'spa', label: 'SPA', modules: ['spa'], paid: true },
  { group: 'Tesiste', id: 'events', label: 'Toplantı / etkinlik', modules: ['mice'], paid: true },
  { group: 'Tesiste', id: 'parking', label: 'Transfer / otopark', modules: ['parking'], paid: true },
  { group: 'Tesiste', id: 'staff', label: 'Personel yönetimi (İK)', modules: ['hr'], paid: true },
  { group: 'İşletme', id: 'einvoice', label: 'E-fatura', modules: ['invoices'] },
  { group: 'İşletme', id: 'revenue', label: 'Gelir yönetimi (dinamik fiyat)', modules: ['revenue_management'] },
  { group: 'İşletme', id: 'quick_id', label: 'Kimlik tarama (Quick-ID)', modules: ['quick_id'], paid: true },
];

const BY_ID = Object.fromEntries(NEEDS.map((need) => [need.id, need]));
const rank = (tier) => Math.max(0, TIER_ORDER.indexOf(normalizeTier(tier)));

/**
 * Lowest plan (not below ``minTier``) whose server defaults include every
 * plan module the needs ask for, with the reason for each step up.
 * Returns { tier, reasons: [{ need, tier }], uncovered: [moduleKey] }.
 */
export function recommendTier(needIds, catalog, minTier = 'mini') {
  const floor = rank(minTier);
  const reasons = [];
  const uncovered = [];
  let tier = floor;
  for (const id of needIds) {
    const need = BY_ID[id];
    if (!need || need.paid) continue;
    for (const key of need.planModules || need.modules) {
      const first = TIER_ORDER.findIndex((name) => catalog?.[name]?.[key] === true);
      if (first < 0) { uncovered.push(key); continue; }
      if (first > tier) tier = first;
      if (first > floor) reasons.push({ need: need.label, tier: TIER_ORDER[first] });
    }
  }
  return { tier: TIER_ORDER[tier], reasons, uncovered };
}

/** Modules the needs switch on (plan modules and paid add-ons alike). */
export function needModules(needIds) {
  return [...new Set(needIds.flatMap((id) => BY_ID[id]?.modules || []))];
}

export function applyNeeds(modules, needIds) {
  const next = { ...modules };
  for (const key of needModules(needIds)) next[key] = true;
  return next;
}
