import { describe, expect, it, vi } from 'vitest';
import { userAccessScopeLabel, userIdentityLabel, userRoleLabel } from '../userRolePresentation';

describe('user role presentation', () => {
  it('separates identity, translated role and access scope', () => {
    const t = vi.fn((_key, options) => options.defaultValue);
    expect(userIdentityLabel({ name: 'Operator', email: 'info@syroce.com' })).toBe('Operator');
    expect(userRoleLabel('super_admin', t)).toBe('Süper yönetici');
    expect(userAccessScopeLabel('super_admin')).toBe('Platform geneli');
  });

  it('uses safe fallbacks for unknown or missing roles', () => {
    expect(userRoleLabel('night_manager')).toBe('night manager');
    expect(userRoleLabel()).toBe('Tanımsız');
    expect(userIdentityLabel({ email: 'user@example.com' })).toBe('user@example.com');
  });
});
