import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const dashboardSource = readFileSync(resolve(process.cwd(), 'src/pages/Dashboard.jsx'), 'utf8');

describe('dashboard language-aware briefing cache', () => {
  it('scopes the cached briefing and request to the selected interface language', () => {
    expect(dashboardSource).toContain('aiBriefingLanguage: null');
    expect(dashboardSource).toContain('dashboardCache.aiBriefingLanguage === interfaceLanguage');
    expect(dashboardSource).toContain('loadAIBriefing(tenantCacheKey, interfaceLanguage)');
    expect(dashboardSource).toContain('lang=${encodeURIComponent(requestLanguage)}');
  });
});
