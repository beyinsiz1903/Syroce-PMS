/* global console */
import { test, expect } from '@playwright/test';
import { loginAsDemo } from './fixtures/auth.js';
import {
  CRITICAL_ROUTE_BUDGETS,
  performanceViolations,
  routePerformanceSnapshot,
} from './fixtures/performanceBudget.js';

test.describe('Critical route performance budgets', () => {
  test('dashboard, PMS, calendar, reports and channel manager stay within production budgets', async ({ page }, testInfo) => {
    // This login is deliberately local to the gate: performance results do not
    // depend on file execution order or a stale shared auth artifact. Each
    // page.goto below performs a real route opening against the production
    // frontend build and seeded backend that CI serves.
    await loginAsDemo(page);

    const results = [];
    const failures = [];

    for (const route of CRITICAL_ROUTE_BUDGETS) {
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
