import { afterEach, describe, expect, it } from 'vitest';
import registry from '@/config/frontdeskPresentation.json';
import { PRESENTATION_TENANT as tenant, presentationContextTenant, presentationHotelName, presentationOperatorName, presentFrontdeskResponse, preserveFrontdeskSourceUpdate, projectFrontdeskPresentation, storedPresentationTenant } from '../frontdeskPresentation';

const guest = registry.guests.find(row => row.original === 'Ada AcceptanceTest');
const response = (data, url = '/pms/guests', method = 'get') => ({ data, config: { url, method, _frontdeskPresentationTenant: tenant }, status: 200 });
afterEach(() => { localStorage.clear(); preserveFrontdeskSourceUpdate({}, null); });

describe('reviewed natural frontdesk presentation', () => {
  it('has unique reviewed profile IDs and distinct natural names', () => {
    expect(registry.guests).toHaveLength(46);
    expect(new Set(registry.guests.map(row => row.id)).size).toBe(46);
    expect(new Set(registry.guests.map(row => row.display)).size).toBe(46);
    expect(registry.guests.every(row => !/demo|test|qa|acceptance|synthetic|e2e/i.test(row.display))).toBe(true);
  });

  it('projects linked profile and booking names consistently without touching their source', () => {
    const raw = { guests: [{ id: guest.id, name: guest.original }], bookings: [{ id: 'booking', guest_id: guest.id, guest_name: guest.original, amount: 100, currency: 'USD', status: 'checked_in', tax_rate: null }] };
    const saved = structuredClone(raw);
    const result = projectFrontdeskPresentation(raw, tenant);
    expect(result.guests[0].name).toBe('Ada Erdem');
    expect(result.bookings[0]).toEqual({ ...raw.bookings[0], guest_name: 'Ada Erdem' });
    expect(raw).toEqual(saved);
  });

  it('does not restore a hidden, masked, absent or independently renamed identity', () => {
    for (const name of [undefined, null, '', 'Gizli misafir', 'A*** A***', 'Yeni Kayıt']) {
      const raw = { id: guest.id, name, first_name: 'A***', last_name: 'A***' };
      expect(projectFrontdeskPresentation(raw, tenant)).toBe(raw);
    }
  });

  it('keeps duplicate legacy names distinct when stable guest IDs are available', () => {
    const duplicates = registry.guests.filter(row => row.original === 'TEST E2E Misafir');
    expect(duplicates).toHaveLength(2);
    const result = projectFrontdeskPresentation(duplicates.map(row => ({ id: row.id, name: row.original })), tenant);
    expect(result.map(row => row.name)).toEqual(duplicates.map(row => row.display));
    const ambiguous = { name: 'TEST E2E Misafir' };
    expect(projectFrontdeskPresentation(ambiguous, tenant)).toBe(ambiguous);
  });

  it('does not override a renamed or masked primary identity from stale name companions', () => {
    const raw = { id: guest.id, name: 'Gizli misafir', first_name: 'Ada', last_name: 'AcceptanceTest' };
    expect(projectFrontdeskPresentation(raw, tenant)).toBe(raw);
    expect(projectFrontdeskPresentation({ ...raw, name: 'Queue Tester' }, tenant).name).toBe('Queue Tester');
  });

  it('retains IDs, codes, contacts, money, counts and custom-field values exactly', () => {
    const raw = { id: 'demo-source', tenant_id: tenant, name: 'DEMO QA • Gömlek yıkama ve ütü', code: 'demoqa261030shirt', email: 'test@example.invalid', id_number: 'EXELY-TEST-2026', source_fingerprint: 'hash', price: 75, quantity: 2, currency: 'TRY', values: { demoqa_1470_number: 0, demoqa_1470_boolean: false }, custom_fields: { note: 'Test' } };
    const result = projectFrontdeskPresentation(raw, tenant);
    expect(result).toEqual({ ...raw, name: 'Gömlek yıkama ve ütü' });
    expect(result.values).toBe(raw.values);
    expect(result.custom_fields).toBe(raw.custom_fields);
  });

  it('preserves history, before/after, audit, original source and options branches', () => {
    const source = { name: guest.original, description: 'DEMO QA • Günün çorbası' };
    const raw = { history: [source], audit_logs: [source], before: source, after: source, presentation_archive: { reason: 'Demo' }, features_audit: [source], raw: source, source, options: [guest.original] };
    expect(projectFrontdeskPresentation(raw, tenant)).toBe(raw);
  });

  it('does not change another hotel or a foreign-tenant child', () => {
    const raw = { tenant_id: 'other', name: guest.original };
    expect(projectFrontdeskPresentation(raw, tenant)).toBe(raw);
    expect(projectFrontdeskPresentation([raw], 'other')).toEqual([raw]);
  });

  it('relabels UDF headers while keeping the real key and values', () => {
    const result = projectFrontdeskPresentation({ key: 'demoqa_1470_number', label: 'DEMO QA • Sayısal kabul değeri', section: 'DEMO QA 31 Ekim' }, tenant);
    expect(result).toEqual({ key: 'demoqa_1470_number', label: 'Konaklama Tercih Puanı', section: 'Misafir Tercihleri', presentation_key: 'konaklama_tercih_puani' });
  });

  it('retains rate/source uncertainty instead of inventing a real financial source', () => {
    const raw = { notes: 'Yapay Demo kabul kaydı; gerçek para/POS/banka/mesaj/resmi bildirim yok. Örnek kaynak kur: USD=50.0001 TRY, EUR=55.0001 TRY; güncel piyasa kuru değildir.' };
    expect(projectFrontdeskPresentation(raw, tenant).notes).toBe('Örnek kaynak kur: USD=50.0001 TRY, EUR=55.0001 TRY; güncel piyasa kuru değildir.');
  });

  it('preserves shared source objects and does not overflow on cycles', () => {
    const row = { name: guest.original };
    const result = projectFrontdeskPresentation([row, row], tenant);
    expect(result[0]).toBe(result[1]);
    expect(row.name).toBe(guest.original);
    const cycle = {}; cycle.self = cycle;
    expect(() => projectFrontdeskPresentation(cycle, tenant)).not.toThrow();
  });
});

describe('tenant and transport boundaries', () => {
  it('does not save unchanged presentation names back through an edit form', () => {
    const raw = { id: guest.id, name: guest.original, first_name: 'Ada', last_name: 'AcceptanceTest', phone: '', total_amount: 100 };
    const displayed = presentFrontdeskResponse(response(raw), tenant).data;
    const update = { method: 'put', url: `/pms/guests/${guest.id}`, data: { ...displayed, phone: 'new-contact' } };
    const saved = preserveFrontdeskSourceUpdate(update, tenant);
    expect(saved.data).toEqual({ ...raw, phone: 'new-contact' });
    expect(update.data.name).toBe('Ada Erdem');
    expect(raw.name).toBe(guest.original);
  });

  it('restores only observed, unchanged fields on the same existing resource', () => {
    presentFrontdeskResponse(response({ id: 'service-1', name: 'DEMO QA • Gömlek yıkama ve ütü', price: 75 }, '/laundry/items'), tenant);
    const update = { method: 'patch', url: '/laundry/items/service-1', data: { name: 'Gömlek yıkama ve ütü', price: 80 } };
    expect(preserveFrontdeskSourceUpdate(update, tenant).data).toEqual({ name: 'DEMO QA • Gömlek yıkama ve ütü', price: 80 });
    expect(preserveFrontdeskSourceUpdate({ ...update, url: '/spa/items/service-1' }, tenant)).toEqual({ ...update, url: '/spa/items/service-1' });
    expect(preserveFrontdeskSourceUpdate({ ...update, data: { name: 'Yeni hizmet adı' } }, tenant).data.name).toBe('Yeni hizmet adı');
    expect(preserveFrontdeskSourceUpdate({ ...update, method: 'post' }, tenant).data.name).toBe('Gömlek yıkama ve ütü');
  });

  it('clears stale source observations on context changes and fresh canonical reads', () => {
    presentFrontdeskResponse(response({ id: guest.id, name: guest.original }), tenant);
    presentFrontdeskResponse(response({ id: guest.id, name: 'Yeni isim' }), tenant);
    const update = { method: 'patch', url: `/pms/guests/${guest.id}`, data: { name: guest.display } };
    expect(preserveFrontdeskSourceUpdate(update, tenant)).toBe(update);
    presentFrontdeskResponse(response({ id: guest.id, name: guest.original }), tenant);
    preserveFrontdeskSourceUpdate({}, 'other');
    expect(preserveFrontdeskSourceUpdate(update, tenant)).toBe(update);
  });

  it('does not rewrite custom values, raw audit, new entries or excluded official updates', () => {
    presentFrontdeskResponse(response({ id: guest.id, name: guest.original }), tenant);
    const update = { method: 'patch', url: `/pms/guests/${guest.id}`, data: { values: { name: guest.display }, history: [{ id: guest.id, name: guest.display }] } };
    expect(preserveFrontdeskSourceUpdate(update, tenant)).toBe(update);
    expect(preserveFrontdeskSourceUpdate({ ...update, url: `/invoices/${guest.id}`, data: { name: guest.display } }, tenant).data.name).toBe(guest.display);
    expect(preserveFrontdeskSourceUpdate({ ...update, url: '/pms/guests/new', data: { name: guest.display } }, tenant).data.name).toBe(guest.display);
  });

  it('requires matching user and tenant context, not just a property label', () => {
    expect(presentationContextTenant({ tenant_id: tenant }, { id: tenant })).toBe(tenant);
    expect(presentationContextTenant({ tenant_id: 'other' }, { id: tenant })).toBeNull();
    expect(presentationContextTenant({ tenant_id: tenant }, { id: 'other' })).toBeNull();
    expect(presentationContextTenant(null, null)).toBeNull();
  });

  it('reads only the existing ordinary context and fails closed on invalid JSON', () => {
    localStorage.setItem('user', JSON.stringify({ tenant_id: tenant }));
    localStorage.setItem('tenant', JSON.stringify({ id: tenant }));
    expect(storedPresentationTenant()).toBe(tenant);
    localStorage.setItem('tenant', '{');
    expect(storedPresentationTenant()).toBeNull();
  });

  it('uses a natural hotel/operator header without changing auth identity or roles', () => {
    const user = { tenant_id: tenant, name: 'Demo Kullanıcı', role: 'super_admin' };
    const hotel = { id: tenant, property_name: 'Syroce Demo Hotel' };
    expect(presentationHotelName(hotel, user)).toBe('Syroce Hotel');
    expect(presentationOperatorName(user, hotel)).toBe('Ön Büro Yetkilisi');
    expect(user.name).toBe('Demo Kullanıcı');
    expect(user.role).toBe('super_admin');
    expect(presentationOperatorName(user, { id: 'other' })).toBe('Demo Kullanıcı');
  });

  it('creates a separate successful read response, leaving adapter caches raw', () => {
    const raw = response([{ id: guest.id, name: guest.original }]);
    const result = presentFrontdeskResponse(raw, tenant);
    expect(result).not.toBe(raw);
    expect(result.data[0].name).toBe('Ada Erdem');
    expect(raw.data[0].name).toBe(guest.original);
    expect(result.config).toBe(raw.config);
  });

  it.each(['post', 'put', 'patch', 'delete'])('does not change %s request/result semantics', method => {
    const raw = response({ id: guest.id, name: guest.original }, '/pms/guests', method);
    raw.config.data = { name: guest.original, amount: 100 };
    expect(presentFrontdeskResponse(raw, tenant)).toBe(raw);
    expect(raw.config.data.name).toBe(guest.original);
  });

  it.each(['/audit/chain/verify', '/pms/reservations/x/history', '/invoices/1', '/kbs/guests', '/kvkk/requests', '/auth/me', '/admin/tenants', '/reports/export', '/other'])('leaves %s raw', path => {
    const raw = response({ name: guest.original }, path);
    expect(presentFrontdeskResponse(raw, tenant)).toBe(raw);
  });

  it('does not project stale tenant responses, blobs or another origin', () => {
    const raw = response({ name: guest.original });
    expect(presentFrontdeskResponse(raw, 'other')).toBe(raw);
    raw.config._frontdeskPresentationTenant = 'other';
    expect(presentFrontdeskResponse(raw, tenant)).toBe(raw);
    const blob = response({ name: guest.original }); blob.config.responseType = 'blob';
    expect(presentFrontdeskResponse(blob, tenant)).toBe(blob);
    const external = response({ name: guest.original }, 'https://example.invalid/api/pms/guests');
    expect(presentFrontdeskResponse(external, tenant)).toBe(external);
  });

  it.each(['/profile-udf/definitions', '/spa/services', '/mice/events', '/activities', '/laundry/orders', '/frontdesk/folio/x', '/night-audit/financial-summary'])('covers the linked %s read view', path => {
    const raw = response({ description: 'DEMO QA • Günün çorbası' }, path);
    expect(presentFrontdeskResponse(raw, tenant).data.description).toBe('Günün çorbası');
  });
});
