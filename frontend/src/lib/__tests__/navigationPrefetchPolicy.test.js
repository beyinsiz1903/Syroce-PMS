import { describe, expect, it } from 'vitest';
import { shouldPrefetchOnGroupOpen } from '../navigationPrefetchPolicy';

describe('navigation prefetch policy', () => {
  it('does not start every route request merely because a menu group opens', () => {
    expect(shouldPrefetchOnGroupOpen()).toBe(false);
  });
});
