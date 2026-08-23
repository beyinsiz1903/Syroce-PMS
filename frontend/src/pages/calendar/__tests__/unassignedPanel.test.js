import { describe, expect, it } from 'vitest';

import { resetUnassignedListScroll } from '../unassignedPanel';

describe('resetUnassignedListScroll', () => {
  it('restores the drawer to the first reservation', () => {
    const listElement = { scrollTop: 180 };

    expect(resetUnassignedListScroll(listElement)).toBe(true);
    expect(listElement.scrollTop).toBe(0);
  });

  it('is safe before the drawer element is mounted', () => {
    expect(resetUnassignedListScroll(null)).toBe(false);
  });
});
