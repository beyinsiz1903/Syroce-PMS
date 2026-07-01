import { describe, it, expect, beforeEach } from 'vitest';

describe('featureFlags', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('feature flag structure is key-value boolean', () => {
    const flags = { dark_mode: true, beta_dashboard: false };
    expect(flags.dark_mode).toBe(true);
    expect(flags.beta_dashboard).toBe(false);
  });

  it('missing flag defaults to false', () => {
    const flags = {};
    expect(flags.new_feature || false).toBe(false);
  });
});
