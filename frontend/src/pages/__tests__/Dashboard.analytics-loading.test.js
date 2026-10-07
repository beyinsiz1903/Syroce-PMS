import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/Dashboard.jsx'), 'utf8');

describe('Dashboard analytics loading', () => {
  it('keeps Recharts out of the critical dashboard module and lazy-loads analytics', () => {
    expect(source).toContain("const DashboardAnalytics = lazy(() => import('@/components/DashboardAnalytics'))");
    expect(source).not.toContain("from 'recharts'");
    expect(source).toContain('<DashboardAnalytics occupancyData={occupancyData}');
  });

  it('does not request an unused demand heatmap endpoint during startup', () => {
    expect(source).not.toContain('/rms/demand-heatmap?days=30');
  });

  it('does not block PMS KPIs on invoice statistics', () => {
    const invoiceStart = source.indexOf("const invoiceStatsPromise = axios.get('/invoices/stats')");
    const pmsAwait = source.indexOf("await axios.get('/pms/dashboard')", invoiceStart);
    const firstStatsCommit = source.indexOf('setStats(statsData);', pmsAwait);
    const invoiceHydration = source.indexOf('void invoiceStatsPromise.then(', firstStatsCommit);

    expect(invoiceStart).toBeGreaterThan(-1);
    expect(pmsAwait).toBeGreaterThan(invoiceStart);
    expect(firstStatsCommit).toBeGreaterThan(pmsAwait);
    expect(invoiceHydration).toBeGreaterThan(firstStatsCommit);
  });
});
