import { describe, expect, it } from 'vitest';

import { getCheckoutErrorMessage, normalizeCheckoutResponse } from '@/utils/pmsCheckout';

describe('PMS checkout response guards', () => {
  it('normalizes empty and malformed success responses without throwing', () => {
    expect(normalizeCheckoutResponse(undefined)).toEqual({
      message: 'Çıkış işlemi tamamlandı',
      totalBalance: 0,
      foliosClosed: 0,
    });
    expect(normalizeCheckoutResponse({ data: { total_balance: '12.5', folios_closed: '2' } }))
      .toMatchObject({ totalBalance: 12.5, foliosClosed: 2 });
  });

  it('converts structured API details into a render-safe string', () => {
    expect(getCheckoutErrorMessage({ response: { data: { detail: { message: 'Açık bakiye var' } } } }))
      .toBe('Açık bakiye var');
    expect(getCheckoutErrorMessage({ response: { data: { detail: ['invalid'] } } }))
      .toBe('Çıkış yapılamadı');
  });
});
