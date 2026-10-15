import { describe, expect, it } from 'vitest';
import { endsCurrentSession } from '@/pages/AgencyPortalDashboard';

const error = (token, status = 401, url = '/marketplace/v1/reservations') => ({
  response: { status }, config: { url, headers: { Authorization: `Bearer ${token}` } },
});

describe('agency session expiry', () => {
  it('ends the session only for a 401 sent with the current token', () => {
    expect(endsCurrentSession(error('new'), 'new')).toBe(true);
    expect(endsCurrentSession(error('old'), 'new')).toBe(false); // late answer of a signed-out session
    expect(endsCurrentSession(error('new', 403), 'new')).toBe(false);
    expect(endsCurrentSession(error('new', 401, '/marketplace/v1/extranet/auth/login'), 'new')).toBe(false);
    expect(endsCurrentSession(error('new'), null)).toBe(false);
  });
});
