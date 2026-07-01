import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'node:fs';

const BASE = process.env.APP_URL || 'http://localhost:5000';
const API = process.env.API_URL || 'http://localhost:8000';
const EMAIL = 'info@syroce.com';
const PASS = 'Syroce2026';
const OUT = '/tmp/audit_screenshots';
mkdirSync(OUT, { recursive: true });

const MODULES = [
  { name: 'dashboard', path: '/' },
  { name: 'profile', path: '/profile' },
  { name: 'settings', path: '/settings' },
  { name: 'early-late-pricing', path: '/settings/early-late-pricing' },
  { name: 'hr', path: '/hr' },
  { name: 'rms', path: '/rms' },
  { name: 'system-health', path: '/system-health' },
  { name: 'security', path: '/security' },
  { name: 'xchange', path: '/app/xchange' },
  { name: 'mailing', path: '/app/mailing' },
  { name: 'onboarding', path: '/app/onboarding' },
  { name: 'report-builder', path: '/app/rapor-olusturucu' },
  { name: 'concierge', path: '/ai-whatsapp-concierge' },
];

// 1) Get JWT
const loginRes = await fetch(`${API}/api/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: EMAIL, password: PASS }),
});
if (!loginRes.ok) {
  console.error('Login failed', loginRes.status, await loginRes.text());
  process.exit(1);
}
const loginData = await loginRes.json();
const { access_token, refresh_token, user, tenant } = loginData;
console.log(`Logged in as ${user.email} (tenant ${user.tenant_id?.slice(0,8)})`);

// Fetch modules (subscription) so the tenant context has them
let modules = null;
try {
  const sRes = await fetch(`${API}/api/subscription/current`, { headers: { Authorization: `Bearer ${access_token}` } });
  if (sRes.ok) {
    const j = await sRes.json();
    modules = j?.modules || null;
  }
} catch {}

// 2) Browser session: set token in localStorage and visit each module
const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();

// Initial visit to set localStorage on origin
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.evaluate(({ tok, refresh, u, t, mods }) => {
  localStorage.setItem('token', tok);
  localStorage.setItem('token_ts', String(Date.now()));
  if (refresh) localStorage.setItem('refresh_token', refresh);
  localStorage.setItem('user', JSON.stringify(u));
  localStorage.setItem('tenant', t ? JSON.stringify(t) : 'null');
  if (mods) localStorage.setItem('modules', JSON.stringify(mods));
  localStorage.setItem('language', 'tr');
}, { tok: access_token, refresh: refresh_token, u: user, t: tenant, mods: modules });

const report = [];
for (const mod of MODULES) {
  const url = `${BASE}${mod.path}`;
  const consoleErrors = [];
  const consoleWarns = [];
  const failedRequests = [];

  const onConsole = (msg) => {
    const t = msg.type();
    const txt = msg.text();
    if (t === 'error') consoleErrors.push(txt.slice(0, 300));
    else if (t === 'warning') consoleWarns.push(txt.slice(0, 300));
  };
  const onResponse = (resp) => {
    const status = resp.status();
    if (status >= 400) {
      failedRequests.push(`${status} ${resp.request().method()} ${resp.url().slice(0, 200)}`);
    }
  };
  const onPageError = (err) => {
    consoleErrors.push(`PAGE_ERROR: ${err.message}`.slice(0, 300));
  };

  page.on('console', onConsole);
  page.on('response', onResponse);
  page.on('pageerror', onPageError);

  const t0 = Date.now();
  let navOk = true;
  let navErr = null;
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
  } catch (e) {
    // networkidle may timeout for endlessly-polling pages — fall back to load
    navErr = String(e.message).slice(0, 200);
    try {
      await page.waitForLoadState('load', { timeout: 5000 });
      navOk = true;
      navErr = null;
    } catch {
      navOk = false;
    }
  }
  // Wait a bit for late renders + late XHRs
  await page.waitForTimeout(1500);

  const elapsed = Date.now() - t0;
  const finalUrl = page.url();
  const title = await page.title();
  const screenshotPath = `${OUT}/${mod.name}.png`;
  try {
    await page.screenshot({ path: screenshotPath, fullPage: false });
  } catch (e) {
    consoleErrors.push(`SCREENSHOT_ERR: ${e.message}`);
  }

  // Detect "blank" or stuck-loading screen heuristically
  const bodyText = await page.evaluate(() => (document.body.innerText || '').slice(0, 200));
  const visibleChars = bodyText.replace(/\s+/g, '').length;

  page.off('console', onConsole);
  page.off('response', onResponse);
  page.off('pageerror', onPageError);

  report.push({
    module: mod.name,
    path: mod.path,
    finalUrl: finalUrl.replace(BASE, ''),
    title,
    elapsedMs: elapsed,
    navOk,
    navErr,
    visibleChars,
    bodyPreview: bodyText.slice(0, 120),
    consoleErrors,
    consoleWarns: consoleWarns.slice(0, 5),
    failedRequests,
    screenshot: screenshotPath,
  });
  console.log(`✓ ${mod.name}: ${elapsed}ms, errors=${consoleErrors.length}, 4xx/5xx=${failedRequests.length}, finalUrl=${finalUrl.replace(BASE,'')}`);
}

writeFileSync('/tmp/audit_report.json', JSON.stringify(report, null, 2));
console.log(`\nReport: /tmp/audit_report.json`);
await browser.close();
