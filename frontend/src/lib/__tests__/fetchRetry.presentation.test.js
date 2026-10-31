import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchJsonWithRetry } from '../fetchRetry';
import { PRESENTATION_TENANT as tenant } from '../frontdeskPresentation';

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
const context = () => {
  localStorage.setItem('user', JSON.stringify({ tenant_id: tenant }));
  localStorage.setItem('tenant', JSON.stringify({ id: tenant }));
};
const raw = { name: 'DEMO QA • Gömlek yıkama ve ütü', amount: 75, currency: 'TRY' };

describe('fetch JSON presentation boundary', () => {
  it('projects normal read JSON without changing the fetched source or request', async () => {
    context();
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => raw });
    vi.stubGlobal('fetch', fetcher);
    const opts = { credentials: 'include' };
    expect(await fetchJsonWithRetry('/api/laundry/items', opts)).toEqual({ ...raw, name: 'Gömlek yıkama ve ütü' });
    expect(raw.name).toBe('DEMO QA • Gömlek yıkama ve ütü');
    expect(fetcher).toHaveBeenCalledExactlyOnceWith('/api/laundry/items', opts);
  });
  it('preserves official guest lists, mutation responses and another tenant', async () => {
    context();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => raw }));
    expect(await fetchJsonWithRetry('/api/reports/official-guest-list')).toBe(raw);
    expect(await fetchJsonWithRetry('/api/laundry/items', { method: 'POST' })).toBe(raw);
    localStorage.setItem('tenant', JSON.stringify({ id: 'other' }));
    expect(await fetchJsonWithRetry('/api/laundry/items')).toBe(raw);
  });
  it('does not project a response after a tenant switch while the request was pending', async () => {
    context();
    let finish;
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(resolve => { finish = resolve; })));
    const result = fetchJsonWithRetry('/api/laundry/items');
    localStorage.setItem('tenant', JSON.stringify({ id: 'other' }));
    finish({ ok: true, json: async () => raw });
    expect(await result).toBe(raw);
  });
});
