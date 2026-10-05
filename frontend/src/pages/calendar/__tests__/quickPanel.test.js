import { describe, expect, it } from 'vitest';

import { mergeQuickPanelDetail, primaryQuickPanelFolio } from '../quickPanel';

describe('calendar quick panel detail', () => {
  it('replaces compact masked fields with canonical reservation detail', () => {
    const compact = {
      id: 'booking-1',
      guest_name: 'Yadigar Öztürk',
      guest_email: 'SYR1:masked-email',
      guest_phone: 'SYR1:masked-phone',
      remaining_balance: null,
    };
    const detail = {
      booking: { id: 'booking-1', status: 'confirmed', currency: 'TRY' },
      guest: { name: 'Yadigar Öztürk', email: 'guest@example.com', phone: '905551112233' },
      summary: { reservation_total_due: 3695, pricing_reconciliation_required: true },
      folios: [{ id: 'folio-1', balance: 3695, currency: 'TRY' }],
    };

    expect(mergeQuickPanelDetail(compact, detail)).toEqual(expect.objectContaining({
      id: 'booking-1',
      status: 'confirmed',
      currency: 'TRY',
      guest_email: 'guest@example.com',
      guest_phone: '905551112233',
      remaining_balance: 3695,
      pricing_reconciliation_required: true,
    }));
    expect(primaryQuickPanelFolio(detail)).toEqual(detail.folios[0]);
  });

  it('preserves valid compact values when optional detail fields are absent', () => {
    const compact = { id: 'booking-2', guest_name: 'Ada', guest_email: 'ada@example.com' };
    expect(mergeQuickPanelDetail(compact, { booking: { status: 'confirmed' } })).toEqual(expect.objectContaining({
      id: 'booking-2',
      guest_name: 'Ada',
      guest_email: 'ada@example.com',
      status: 'confirmed',
    }));
  });
});
