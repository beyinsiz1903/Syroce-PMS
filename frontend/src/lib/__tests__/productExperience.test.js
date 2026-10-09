import { describe, expect, it, beforeEach } from 'vitest';
import { applicationPresentation, experienceScope, normalizeWorkItems, readExperiencePreference, roleStartItems, writeExperiencePreference } from '../productExperience';
import { resolvePostLoginDestination } from '../postLoginWorkspace';

describe('product experience boundaries', () => {
  beforeEach(() => sessionStorage.clear());
  it('never adds destinations to the authorized role shortlist', () => {
    const items = [{ key: 'tasks_workspace', navGroup: 'operations', path: '/app/tasks' }];
    expect(roleStartItems({ role: 'housekeeping' }, items)).toEqual(items);
    expect(roleStartItems({ role: 'super_admin' }, [])).toEqual([]);
  });
  it('uses scoped POS permissions for a custom staff role', () => {
    const items = [{ key: 'pos_dashboard', navGroup: 'fb', path: '/pos' }, { key: 'pms', navGroup: 'frontdesk', path: '/app/pms' }];
    expect(roleStartItems({ role: 'staff', module_scopes: ['pos'] }, items)[0].path).toBe('/pos');
    expect(roleStartItems({ role: 'waiter' }, [...items].reverse())[0].path).toBe('/pos');
  });
  it('groups restaurant work by task, not its commercial package', () => {
    const item = applicationPresentation({ key: 'pos_fnb', label: 'Restoran', hint: 'abonelik anahtarı', groupTitle: 'İK paketi' });
    expect(item.navGroup).toBe('fb');
    expect(item.hint).not.toMatch(/abonelik|anahtar/);
  });
  it('isolates preferences by both operator and property', () => {
    const first = experienceScope({ id: 'u1' }, { id: 'h1' });
    const otherHotel = experienceScope({ id: 'u1' }, { id: 'h2' });
    const otherUser = experienceScope({ id: 'u2' }, { id: 'h1' });
    writeExperiencePreference(first, 'compact', true);
    expect(readExperiencePreference(first, 'compact', false)).toBe(true);
    expect(readExperiencePreference(otherHotel, 'compact', false)).toBe(false);
    expect(readExperiencePreference(otherUser, 'compact', false)).toBe(false);
  });
  it('keeps acknowledged handovers open until explicitly resolved', () => {
    const rows = normalizeWorkItems({ handover: { items: [
      { id: 'a', acknowledged: true, note: 'Follow up' }, { id: 'b', status: 'resolved', note: 'Done' },
    ] }, tasks: { tasks: [{ id: 'a', status: 'pending', title: 'Repair', priority: 'urgent' }] } });
    expect(rows.map(r => r.key)).toEqual(['task:a', 'handover:a']);
    expect(rows[1].status).toBe('acknowledged');
  });
  it('never trusts arbitrary server-provided action URLs', () => {
    expect(normalizeWorkItems({ alerts: { alerts: [{ type: 'x', action: 'https://external.test' }] } })).toEqual([]);
  });
  it('does not route a role to a disabled or denied hotel module', async () => {
    const user = { role: 'housekeeping', id: 'u', tenant_id: 'h', module_scopes: [], effective_permissions: [] };
    expect(await resolvePostLoginDestination({ api: {}, user, tenant: { modules: { pms: true } } })).toBeNull();
    expect(await resolvePostLoginDestination({ api: {}, user: { ...user, module_scopes: ['housekeeping'] }, tenant: { modules: { pms: false } } })).toBeNull();
  });
});
