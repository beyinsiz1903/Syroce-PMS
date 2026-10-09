import { describe, expect, it } from 'vitest';

import { usesExpandedAriLayout } from '../constants';

describe('rate manager responsive layout', () => {
  it('keeps compact selections in the standard three-column layout', () => {
    expect(usesExpandedAriLayout(0)).toBe(false);
    expect(usesExpandedAriLayout(3)).toBe(false);
  });

  it('expands the editor before ARI fields require horizontal scrolling', () => {
    expect(usesExpandedAriLayout(4)).toBe(true);
    expect(usesExpandedAriLayout(8)).toBe(true);
  });
});
