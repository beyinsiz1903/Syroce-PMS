import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, test } from 'vitest';

const readProjectFile = (relativePath) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8');

describe('complete offline application shell contract', () => {
  test('service worker separates static and tenant data caches', () => {
    const source = readProjectFile('../../../public/service-worker.js');

    expect(source).toContain('hotel-pms-static-');
    expect(source).toContain('hotel-pms-data-');
    expect(source).toContain("if (data.type === 'AUTH_CHANGED')");
    expect(source).toContain('caches.delete(DATA_CACHE_NAME)');
  });

  test('deep links fall back to the cached SPA shell', () => {
    const source = readProjectFile('../../../public/service-worker.js');

    expect(source).toContain("request.mode === 'navigate'");
    expect(source).toContain("cache.match('/index.html')");
  });

  test('build and service worker share the generated offline asset inventory', () => {
    const worker = readProjectFile('../../../public/service-worker.js');
    const viteConfig = readProjectFile('../../../vite.config.js');

    expect(worker).toContain("'/offline-assets.json'");
    expect(viteConfig).toContain("fileName: 'offline-assets.json'");
    expect(viteConfig).toContain('offlineAssetManifest()');
  });

  test('installable PWA manifest is linked from the application shell', () => {
    const html = readProjectFile('../../../index.html');
    const manifest = JSON.parse(readProjectFile('../../../public/manifest.webmanifest'));

    expect(html).toContain('rel="manifest" href="/manifest.webmanifest"');
    expect(manifest.start_url).toBe('/app/dashboard');
    expect(manifest.display).toBe('standalone');
    expect(manifest.icons.some((icon) => icon.sizes === '512x512')).toBe(true);
  });

  test('production entry point actually registers the service worker', () => {
    const entry = readProjectFile('../../index.jsx');

    expect(entry).toContain('register as registerServiceWorker');
    expect(entry).toContain('registerServiceWorker();');
  });

  test('stale deployment chunks recover again after a bounded reload cooldown', () => {
    const html = readProjectFile('../../../index.html');

    expect(html).toContain("var CHUNK_RELOAD_KEY = 'syroce_chunk_reload_at'");
    expect(html).toContain('var CHUNK_RELOAD_COOLDOWN_MS = 60 * 1000');
    expect(html).toContain("sessionStorage.removeItem('syroce_chunk_reload_done')");
    expect(html).toContain('window.__syroceForceFreshReload = forceFreshReload');
    expect(html).toContain("u.searchParams.set('_appreload', String(Date.now()))");
  });
});
