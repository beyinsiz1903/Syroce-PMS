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
});
