import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/settings/index.jsx'), 'utf8');

describe('Settings lazy data loading', () => {
  it('keeps the plan catalog out of the default hotel subscription request', () => {
    const subscriptionLoader = source.slice(
      source.indexOf('const loadSubscription = useCallback'),
      source.indexOf('const loadPlanCatalog = useCallback')
    );

    expect(subscriptionLoader).toContain("axios.get('/subscription/current', SETTINGS_REQUEST)");
    expect(subscriptionLoader).not.toContain("axios.get('/subscription/plans')");
  });

  it('loads the plan catalog and B2B data only for their active tabs', () => {
    expect(source).toContain("activeTab === 'plan' && planCatalog.length === 0");
    expect(source).toContain("activeTab === 'b2b' && !b2bInfo");
  });

  it('prevents an unresponsive settings endpoint from waiting forever', () => {
    expect(source).toContain('const SETTINGS_REQUEST = { timeout: 10000 }');
    expect(source).toContain("axios.get('/hotel/team', SETTINGS_REQUEST)");
    expect(source).toContain("axios.get('/pms/hotel-settings', SETTINGS_REQUEST)");
    expect(source).toContain("axios.get('/pms/rooms?limit=500', SETTINGS_REQUEST)");
  });
});
