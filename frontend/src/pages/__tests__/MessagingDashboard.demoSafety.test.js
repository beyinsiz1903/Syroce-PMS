import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const dashboardSource = readFileSync(
  resolve(process.cwd(), 'src/pages/MessagingDashboard.jsx'),
  'utf8',
);

describe('MessagingDashboard demo data safety', () => {
  it('never seeds demo records as a page-load side effect', () => {
    expect(dashboardSource).not.toContain("post('/messaging-center/seed-demo'");
    expect(dashboardSource).not.toContain('Auto-seed demo data on first load');
  });
});
