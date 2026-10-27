import { describe, expect, it } from 'vitest';
import { buildFolioStatement, folioItemInScope, serviceTimingLabel } from '../folioPresentation';

const folios = [
  { id: 'guest', folio_type: 'guest', currency: 'USD', balance: 70, opening_balance: 5, folio_number: 'F-G' },
  { id: 'agency', payor_type: 'agency', currency: 'USD', balance: 900, folio_number: 'F-A' },
];
const charges = [
  { id: 'food', folio_id: 'guest', category: 'food', total: 12, service_date: '2026-10-24', service_time: '19:30' },
  { id: 'drink', folio_id: 'guest', category: 'beverage', total: 4.4 },
  { id: 'room', folio_id: 'guest', charge_type: 'room_charge', total: 50 },
  { id: 'agency-room', folio_id: 'agency', category: 'room', total: 900 },
  { id: 'ambiguous', category: 'food', total: 800 },
  { id: 'void', folio_id: 'guest', category: 'food', total: 100, voided: true },
];
const input = { folios, charges, payments: [{ id: 'p', folio_id: 'guest', amount: 1.4 }, { id: 'ap', folio_id: 'agency', amount: 900 }], booking: { currency: 'USD', total_amount: 99999 } };

describe('payer-safe folio statements', () => {
  it('defaults to guest accounts, not the booking total or agency account', () => {
    const result = buildFolioStatement({ ...input, payments: [...input.payments, { folio_id: 'guest', currency: 'EUR', amount: 100, voided: true }] });
    expect(result.charges.map(c => c.id)).toEqual(['food', 'drink', 'room']);
    expect(result.payments.map(p => p.id)).toEqual(['p']);
    expect(result.balance).toBe(70);
    expect(result.opening_balance).toBe(5);
    expect(result.excluded_unassigned).toBe(1);
    expect(result.mixedCurrency).toBe(false);
  });
  it('prints food and drinks without accommodation, agency prices, payment or full balance', () => {
    const result = buildFolioStatement({ ...input, category: 'food_beverage' });
    expect(result.charges.map(c => c.id)).toEqual(['food', 'drink']);
    expect(result.statement_only).toBe(true);
    expect(result).not.toHaveProperty('balance');
    expect(result.opening_balance).toBe(0);
    expect(result.payments).toEqual([]);
  });
  it('requires explicit internal audience even if an agency id or all scope is supplied', () => {
    expect(buildFolioStatement({ ...input, scope: 'agency' }).charges).toEqual([]);
    expect(buildFolioStatement({ ...input, scope: 'all' }).selected_folio_ids).toEqual(['guest']);
    expect(buildFolioStatement({ ...input, scope: 'agency', audience: 'internal' }).charges.map(c => c.id)).toEqual(['agency-room']);
  });
  it('does not guess an unassigned line when multiple payers exist', () => {
    expect(folioItemInScope({ total: 800 }, folios, ['guest'])).toBe(false);
    expect(folioItemInScope({ total: 800 }, [folios[0]], ['guest'])).toBe(true);
    expect(folioItemInScope({ total: 800 }, [folios[1]], [])).toBe(false);
  });
  it('deduplicates legacy copies and supports an individual subset without implying settlement', () => {
    const result = buildFolioStatement({ ...input, extraCharges: [charges[0]], selectedIds: ['food'] });
    expect(result.charges).toHaveLength(1);
    expect(result.statement_only).toBe(true);
    expect(result.payments).toEqual([]);
  });
  it('refuses a combined total across currencies including conflicting payments', () => {
    expect(buildFolioStatement({ ...input, charges: [...charges, { id: 'fx', folio_id: 'guest', currency: 'EUR', total: 40 }] }).mixedCurrency).toBe(true);
    expect(buildFolioStatement({ ...input, payments: [{ folio_id: 'guest', currency: 'EUR', amount: 2 }] }).mixedCurrency).toBe(true);
    expect(buildFolioStatement({ ...input, folios: [{ ...folios[0], currency: 'TL' }], booking: { currency: 'TRY' }, payments: [] }).mixedCurrency).toBe(false);
  });
  it('does not assume an unknown payer is the guest', () => {
    expect(buildFolioStatement({ ...input, folios: [{ ...folios[0], folio_type: 'unknown' }] }).charges).toEqual([]);
  });
  it('supplements only a matching property name and never crosses tenant branding', () => {
    expect(buildFolioStatement({ ...input, booking: { tenant_id: 'tenant-a' }, property: { id: 'tenant-a', property_name: 'Örnek Otel' } }).hotel_name).toBe('Örnek Otel');
    expect(buildFolioStatement({ ...input, booking: { tenant_id: 'tenant-b' }, property: { id: 'tenant-a', property_name: 'Yanlış Otel' } }).hotel_name).toBeUndefined();
    expect(buildFolioStatement({ ...input, property: { id: 'tenant-a', property_name: 'Yanlış Otel' } }).hotel_name).toBeUndefined();
  });
});

describe('service timestamps', () => {
  it('never substitutes a posting timestamp for the service time', () => {
    expect(serviceTimingLabel({ created_at: '2026-10-27T11:15:00Z', category: 'spa' })).toBe('Hizmet tarihi belirtilmemiş');
    expect(serviceTimingLabel(charges[0])).toBe('24.10.2026 · 19:30');
    expect(serviceTimingLabel({ service_date: '2026-10-24' })).toBe('24.10.2026 · saat belirtilmemiş');
  });
  it('labels source appointment/order times and the accommodation business date honestly', () => {
    expect(serviceTimingLabel({ service_date: '2026-10-24', service_time: '14:30', service_timing_source: 'spa_appointment' })).toContain('(randevu)');
    expect(serviceTimingLabel({ service_date: '2026-10-24', service_time: '19:30', service_timing_source: 'pos_order' })).toContain('(sipariş)');
    expect(serviceTimingLabel({ charge_type: 'room_charge', business_date: '2026-10-24', posted_at: '2026-10-27' })).toBe('24.10.2026 · konaklama günü');
  });
});
