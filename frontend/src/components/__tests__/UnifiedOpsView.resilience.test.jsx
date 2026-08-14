import { describe, expect, it } from 'vitest';

import { compactObjectRecords } from '@/components/UnifiedOpsView';

describe('UnifiedOpsView provider data resilience', () => {
  it('removes null and undefined records before rendering provider data', () => {
    const records = compactObjectRecords([
      undefined,
      null,
      { id: 'first' },
      false,
      { id: 'second' },
    ]);

    expect(records).toEqual([{ id: 'first' }, { id: 'second' }]);
  });

  it('returns an empty list for non-array provider responses', () => {
    expect(compactObjectRecords(undefined)).toEqual([]);
    expect(compactObjectRecords({ id: 'unexpected-shape' })).toEqual([]);
  });
});
