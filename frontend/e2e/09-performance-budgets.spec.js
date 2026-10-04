/* global console */
import { test, expect } from '@playwright/test';
import { loginAsDemo } from './fixtures/auth.js';
import {
  CRITICAL_ROUTE_BUDGETS,
  performanceViolations,
  routePerformanceSnapshot,
} from './fixtures/performanceBudget.js';

test.describe('Critical route performance budgets', () => {
  test('dashboard, PMS, calendar, reports and channel manager stay within production budgets', async ({ browser }, testInfo) => {
    // Create an authenticated storage state inside this test. This keeps the
    // performance gate independent of filename execution order in the smoke
    // suite while every measured route still starts from a cold browser cache.
    const loginContext = await browser.newContext();
    const loginPage = await loginContext.newPage();
    await loginAsDemo(loginPage);
    const storageState = await loginContext.storageState();
    await loginContext.close();

    const results = [];
    const failures = [];

    for (const route of CRITICAL_ROUTE_BUDGETS) {
      const context = await browser.newContext({
        storageState,
        viewport: { width: 1440, height: 900 },
        locale: 'tr-TR',
        timezoneId: 'Europe/Istanbul',
      });
      const page = await context.newPage();
      const start = Date.now();
      await page.goto(route.path, { waitUntil: 'domcontentloaded' });
      await expect(page.locator(route.readySelector)).toBeVisible({ timeout: route.readyMs });
      const readyMs = Date.now() - start;

      const interactionStart = Date.now();
      await route.interact(page);
      const interactionMs = Date.now() - interactionStart;
      const snapshot = await routePerformanceSnapshot(page);
      const measurement = { route: route.id, path: route.path, readyMs, interactionMs, ...snapshot };
      const violations = performanceViolations(route, measurement);
      results.push({ ...measurement, budget: {
        readyMs: route.readyMs,
        interactionMs: route.interactionMs,
        scriptBytes: route.scriptBytes,
      }, violations });
      if (violations.length > 0) failures.push(`${route.id}: ${violations.join(', ')}`);
      await context.close();
    }

    const report = { schemaVersion: 1, generatedAt: new Date().toISOString(), results };
    await testInfo.attach('critical-route-performance.json', {
      body: JSON.stringify(report, null, 2),
      contentType: 'application/json',
    });
    console.table(results.map(({ route, readyMs, interactionMs, scriptBytes, longTaskMs, domNodes, violations }) => ({
      route,
      readyMs,
      interactionMs,
      scriptKiB: Math.round(scriptBytes / 1024),
      longTaskMs,
      domNodes,
      violations: violations.join('; ') || 'OK',
    })));
    expect(failures, failures.join('\n')).toEqual([]);
  });
});
