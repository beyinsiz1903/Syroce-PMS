/* global document, performance */
import { expect } from '@playwright/test';

const KiB = 1024;

// These are intentionally user-perceived limits, not an arbitrary Lighthouse
// score. The e2e job runs a production build against the seeded API, so a
// route has to render a real operational surface under the same auth and data
// conditions as the rest of the smoke suite.
export const CRITICAL_ROUTE_BUDGETS = [
  {
    id: 'dashboard',
    path: '/app/dashboard',
    readySelector: '[data-testid="app-shell"]',
    readyMs: 6_000,
    scriptBytes: 1_500 * KiB,
    interactionMs: 2_000,
    async interact(page) {
      // A newly provisioned or empty hotel dashboard can fit entirely in the
      // viewport, so scrolling is not a reliable interaction. Toggling a
      // dashboard module group is both a real user action and independent of
      // the seed data's page height.
      const trigger = page.locator('[role="main"] button[data-state]').first();
      await expect(trigger).toBeVisible();
      const before = await trigger.getAttribute('data-state');
      await trigger.click();
      await expect(trigger).not.toHaveAttribute('data-state', before || '');
    },
  },
  {
    id: 'pms',
    path: '/app/pms',
    readySelector: '[data-testid="tab-frontdesk"]',
    readyMs: 7_500,
    // CI's production baseline is 2.34 MiB, including the shared authenticated
    // shell and the PMS workspace. Leave a 20% regression allowance.
    scriptBytes: 2_800 * KiB,
    interactionMs: 2_500,
    async interact(page) {
      const tab = page.locator('[data-testid="tab-rooms"]');
      await expect(tab).toBeVisible();
      await tab.click();
      await expect(tab).toHaveAttribute('data-state', 'active');
    },
  },
  {
    id: 'calendar',
    path: '/app/reservation-calendar',
    readySelector: '[data-testid="calendar-sticky-header"]',
    readyMs: 8_000,
    // Baseline: 2.06 MiB. This captures the calendar grid without treating the
    // current production payload as a failure.
    scriptBytes: 2_500 * KiB,
    interactionMs: 1_500,
    async interact(page) {
      const header = page.locator('[data-testid="calendar-sticky-header"]');
      const before = await header.innerText();
      await page.locator('[data-testid="calendar-nav-next"]').click();
      await expect.poll(() => header.innerText()).not.toBe(before);
    },
  },
  {
    id: 'reports',
    path: '/app/raporlar',
    readySelector: '[data-testid="reports-sidebar"]',
    readyMs: 8_000,
    // Baseline: 2.49 MiB. Report visualisation dependencies are intentionally
    // loaded only for this route; the cap protects that boundary.
    scriptBytes: 3_000 * KiB,
    interactionMs: 2_500,
    async interact(page) {
      const report = page.locator('[data-testid="report-nav-revenue"]');
      await expect(report).toBeVisible();
      await report.click();
      await expect(report).toHaveClass(/bg-blue-50/);
    },
  },
  {
    id: 'channel-manager',
    path: '/app/channel-manager',
    readySelector: '[role="tablist"]',
    readyMs: 7_000,
    // Baseline: 1.92 MiB for the authenticated shell plus channel workspace.
    scriptBytes: 2_400 * KiB,
    interactionMs: 2_000,
    async interact(page) {
      const tab = page.getByRole('tab', { name: /room mappings/i });
      await expect(tab).toBeVisible();
      await tab.click();
      await expect(tab).toHaveAttribute('data-state', 'active');
    },
  },
];

export async function routePerformanceSnapshot(page) {
  return page.evaluate(() => {
    const navigation = performance.getEntriesByType('navigation')[0];
    const resources = performance.getEntriesByType('resource');
    const scripts = resources.filter((entry) => entry.initiatorType === 'script' || /\.js(?:\?|$)/.test(entry.name));
    const longTasks = performance.getEntriesByType('longtask');
    return {
      navigation: navigation ? {
        domContentLoadedMs: Math.round(navigation.domContentLoadedEventEnd),
        responseStartMs: Math.round(navigation.responseStart),
      } : null,
      scriptBytes: scripts.reduce((sum, entry) => sum + (entry.transferSize || entry.encodedBodySize || 0), 0),
      scriptCount: scripts.length,
      longTaskMs: Math.round(longTasks.reduce((sum, entry) => sum + entry.duration, 0)),
      domNodes: document.getElementsByTagName('*').length,
    };
  });
}

export function performanceViolations(route, measurement) {
  const violations = [];
  if (measurement.readyMs > route.readyMs) {
    violations.push(`ready ${measurement.readyMs}ms > ${route.readyMs}ms`);
  }
  if (measurement.interactionMs > route.interactionMs) {
    violations.push(`interaction ${measurement.interactionMs}ms > ${route.interactionMs}ms`);
  }
  if (measurement.scriptBytes > route.scriptBytes) {
    violations.push(`scripts ${measurement.scriptBytes}B > ${route.scriptBytes}B`);
  }
  return violations;
}
