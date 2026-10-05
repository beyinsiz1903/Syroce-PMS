import { describe, expect, it } from 'vitest';
import { maskSecurityActor, safeSecurityEventDetail } from '../securityEventPrivacy';

describe('security event privacy', () => {
  it('masks plain, encrypted and opaque actor identifiers', () => {
    expect(maskSecurityActor('person@example.com')).toBe('p***@example.com');
    expect(maskSecurityActor('SYR1:encrypted-payload')).toBe('Korunan kullanıcı');
    expect(maskSecurityActor('opaque-id')).toBe('Korunan kullanıcı');
  });

  it('does not render token and JTI details', () => {
    expect(safeSecurityEventDetail({ details: 'Token refreshed (jti=secret)' })).toBe('Güvenlik ayrıntısı korundu');
    expect(safeSecurityEventDetail({ details: 'refresh_token=secret' })).toBe('Güvenlik ayrıntısı korundu');
    expect(safeSecurityEventDetail({ details: 'Parola değiştirildi' })).toBe('Parola değiştirildi');
  });
});
