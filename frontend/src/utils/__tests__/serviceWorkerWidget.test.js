import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';

const readProjectFile = relativePath => readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8');

function worker() {
  const handlers = {};
  const cache = { put: vi.fn().mockResolvedValue(), match: vi.fn() };
  const caches = { open: vi.fn().mockResolvedValue(cache) };
  const fetch = vi.fn();
  runInNewContext(readProjectFile('../../../public/service-worker.js'), {
    self: { location: { origin: 'https://pms.example' }, addEventListener: (name, handler) => { handlers[name] = handler; } },
    URL, fetch, caches, console,
  });
  const request = (path, mode = 'navigate') => {
    const request = { url: `https://pms.example${path}`, method: 'GET', mode };
    let response;
    handlers.fetch({ request, respondWith: promise => { response = promise; } });
    return { request, response };
  };
  return { request, cache, caches, fetch };
}

describe('widget must not use the shared offline shell', () => {
  it.each(['/agency-widget?key=first', '/agency-widget?key=second', '/api/marketplace/v1/widget/config'])('always fetches a fresh policy/data for %s', async path => {
    const sw = worker();
    const networkResponse = { ok: true };
    sw.fetch.mockResolvedValue(networkResponse);
    const { request, response } = sw.request(path, path.startsWith('/api/') ? 'cors' : 'navigate');
    expect(await response).toBe(networkResponse);
    expect(sw.fetch).toHaveBeenCalledWith(request, { cache: 'no-store' });
    expect(sw.caches.open).not.toHaveBeenCalled();
    expect(sw.cache.put).not.toHaveBeenCalled();
  });

  it('never substitutes a stale offline document when widget policy validation is unavailable', async () => {
    const sw = worker();
    sw.fetch.mockRejectedValue(new Error('offline'));
    await expect(sw.request('/agency-widget?key=first').response).rejects.toThrow('offline');
    expect(sw.caches.open).not.toHaveBeenCalled();
  });

  it('keeps the normal PMS offline navigation unchanged', async () => {
    const sw = worker();
    const shell = { ok: true };
    sw.fetch.mockRejectedValue(new Error('offline'));
    sw.cache.match.mockResolvedValue(shell);
    expect(await sw.request('/app/dashboard').response).toBe(shell);
    expect(sw.cache.match).toHaveBeenCalledWith('/index.html');
  });
});
