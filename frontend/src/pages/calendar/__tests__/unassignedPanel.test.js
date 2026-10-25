import { describe, expect, it } from 'vitest';

import { mergeUnassignedAttention, resetUnassignedListScroll } from '../unassignedPanel';

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

it('does not resurrect the named synthetic archive, but preserves real or unreviewed mapping holds', () => {
  const archived = { tenant_id: '5bad4a34-6ee3-4566-9053-741b7375a9cf', id: '2faf1e5b-3d87-4d13-9af5-d49b42e1805e',
    status: 'archived_demo', is_inventory_hold: true, demo_reconstruction: {
      policy_id: 'demo-legacy-source-reconstruction-20261025-v1', basis: 'demo_reconstruction',
    } };
  expect(mergeUnassignedAttention([archived])).toEqual([]);
  for (const changed of [{ tenant_id: 'real-hotel' }, { id: 'another-booking' }, { demo_reconstruction: {} }, { status: 'pending_mapping' }]) {
    expect(mergeUnassignedAttention([{ ...archived, ...changed }])).toHaveLength(1);
  }
});
