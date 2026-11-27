import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';

const readProjectFile = relativePath => readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8');

function worker() {
  const handlers = {};
  const stale = { oldCurrencyPolicy: true, total: 50 };
  const cache = { put: vi.fn(), match: vi.fn().mockResolvedValue(stale) };
  const caches = { open: vi.fn().mockResolvedValue(cache), match: vi.fn().mockResolvedValue(stale) };
  const fetch = vi.fn();
  runInNewContext(readProjectFile('../../../public/service-worker.js'), {
    self: { location: { origin: 'https://pms.example' }, addEventListener: (name, handler) => { handlers[name] = handler; } },
    URL, fetch, caches, console,
  });
  const request = path => {
    const req = { url: `https://pms.example${path}`, method: 'GET', mode: 'cors' };
    let response;
    handlers.fetch({ request: req, respondWith: promise => { response = promise; } });
    return { req, response };
  };
  return { request, fetch, cache, caches };
}

const paths = ['/api/reports/revenue?start_date=2026-11-12', '/api/reports/basic-dashboard',
  '/api/reports/folio-income/excel', '/api/finance/financial-summary', '/api/pms/financial-summary',
  '/api/accounting/trial-balance', '/api/dashboard/summary', '/api/kpis/adr', '/api/widgets/revenue'];

describe('financial report cache isolation', () => {
  it.each(paths)('returns current server values rather than a cached old currency snapshot: %s', async path => {
    const sw = worker();
    const current = { reporting_currency: 'TRY', total: 7985 };
    sw.fetch.mockResolvedValue(current);
    const { req, response } = sw.request(path);
    expect(await response).toBe(current);
    expect(sw.fetch).toHaveBeenCalledWith(req, { cache: 'no-store' });
    expect(sw.caches.open).not.toHaveBeenCalled();
    expect(sw.caches.match).not.toHaveBeenCalled();
    expect(sw.cache.put).not.toHaveBeenCalled();
  });

  it('does not turn an offline monetary report into an old successful result', async () => {
    const sw = worker();
    sw.fetch.mockRejectedValue(new Error('offline'));
    await expect(sw.request(paths[0]).response).rejects.toThrow('offline');
    expect(sw.caches.open).not.toHaveBeenCalled();
    expect(sw.caches.match).not.toHaveBeenCalled();
  });
});
