import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/PMSModule.jsx'), 'utf8');

describe('PMSModule workspace loading', () => {
  it('keeps secondary workspaces out of the front-desk startup bundle', () => {
    expect(source).toContain("const StaffTaskManager = lazy(() => import('@/components/StaffTaskManager'))");
    expect(source).toContain("const FeedbackSystem = lazy(() => import('@/components/FeedbackSystem'))");
    expect(source).toContain("const AllotmentGrid = lazy(() => import('@/components/AllotmentGrid'))");
    expect(source).not.toContain("import StaffTaskManager from '@/components/StaffTaskManager'");
    expect(source).not.toContain("import FeedbackSystem from '@/components/FeedbackSystem'");
    expect(source).not.toContain("import AllotmentGrid from '@/components/AllotmentGrid'");
  });

  it('does not block the first PMS render on secondary data requests', () => {
    const criticalStart = source.indexOf('const criticalResults = await Promise.allSettled([');
    const firstRenderReady = source.indexOf('setLoading(false);', criticalStart);
    const secondaryStart = source.indexOf('const secondaryDataPromise = Promise.allSettled([');
    const secondaryHydration = source.indexOf('void secondaryDataPromise.then(', firstRenderReady);

    expect(criticalStart).toBeGreaterThan(-1);
    expect(secondaryStart).toBeLessThan(criticalStart);
    expect(firstRenderReady).toBeGreaterThan(criticalStart);
    expect(secondaryHydration).toBeGreaterThan(firstRenderReady);
    expect(source.slice(criticalStart, firstRenderReady)).toContain('/pms/rooms?limit=100');
    expect(source.slice(criticalStart, firstRenderReady)).toContain('/pms/bookings?start_date=');
    expect(source.slice(secondaryStart, criticalStart)).toContain('/pms/guests?limit=100');
    expect(source.slice(secondaryStart, criticalStart)).toContain('/companies?limit=50');
  });
});
