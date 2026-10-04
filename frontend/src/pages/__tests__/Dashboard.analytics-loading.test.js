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
});
