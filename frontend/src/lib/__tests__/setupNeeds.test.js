import { describe, expect, it } from 'vitest';
import { applyNeeds, needModules, recommendTier } from '../setupNeeds';

// Excerpt of the server's defaults_by_tier.
const CATALOG = {
  mini: { pms: true, channel_manager: false, agency_extranet: false, invoices: false, booking_engine: false, pos_basic: false, revenue_management: false },
  basic: { pms: true, channel_manager: true, agency_extranet: true, invoices: false, booking_engine: false, pos_basic: false, revenue_management: false },
  professional: { pms: true, channel_manager: true, agency_extranet: true, invoices: true, booking_engine: true, pos_basic: true, revenue_management: false },
  enterprise: { pms: true, channel_manager: true, agency_extranet: true, invoices: true, booking_engine: true, pos_basic: true, revenue_management: true },
};

describe('needs-based plan recommendation', () => {
  it('picks the lowest plan that covers every plan need, with the reason', () => {
    expect(recommendTier([], CATALOG).tier).toBe('mini');
    expect(recommendTier(['ota', 'agencies'], CATALOG)).toMatchObject({ tier: 'basic' });
    const withInvoices = recommendTier(['agencies', 'einvoice'], CATALOG);
    expect(withInvoices.tier).toBe('professional');
    expect(withInvoices.reasons).toEqual(expect.arrayContaining([{ need: 'E-fatura', tier: 'professional' }]));
    expect(recommendTier(['revenue'], CATALOG).tier).toBe('enterprise');
  });

  it('never goes below the property type recommendation', () => {
    expect(recommendTier(['ota'], CATALOG, 'professional').tier).toBe('professional');
    expect(recommendTier(['ota'], CATALOG, 'professional').reasons).toEqual([]);
  });

  it('paid add-ons never raise the plan; they are switched on instead', () => {
    expect(recommendTier(['spa', 'events', 'staff', 'quick_id'], CATALOG).tier).toBe('mini');
    expect(needModules(['spa', 'quick_id', 'ota'])).toEqual(['spa', 'quick_id', 'channel_manager']);
    expect(applyNeeds({ pms: true, spa: false }, ['spa'])).toEqual({ pms: true, spa: true });
  });

  it('reports needs no plan covers instead of guessing', () => {
    expect(recommendTier(['ota'], { mini: {}, basic: {}, professional: {}, enterprise: {} })).toMatchObject({ tier: 'mini', uncovered: ['channel_manager'] });
  });
});
