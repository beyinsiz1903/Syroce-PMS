import { expect, it } from 'vitest';
import { AGENCY_ADMIN_RETURN_PATH, agencyVoucherPath } from './agencyPortalNavigation';

it('returns to the registered admin route', () => {
  expect(AGENCY_ADMIN_RETURN_PATH).toBe('/admin/agencies');
});
it.each(['marketplace', 'hotel'])('routes voucher operations for %s', mode => {
  const prefix = mode === 'hotel' ? '/agency-portal' : '/marketplace/v1';
  expect(agencyVoucherPath(mode, 'a/b')).toBe(`${prefix}/reservations/a%2Fb/voucher.pdf`);
  expect(agencyVoucherPath(mode, 'abc', true)).toBe(`${prefix}/reservations/abc/voucher-email`);
});
it('rejects missing identity or unknown portal modes', () => {
  expect(() => agencyVoucherPath('unknown', 'abc')).toThrow();
  expect(() => agencyVoucherPath('hotel', '')).toThrow();
});
