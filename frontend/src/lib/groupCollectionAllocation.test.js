import { expect, it } from 'vitest';
import { previewGroupCollection } from './groupCollectionAllocation';
it.each([
  ['equal', [50.01, 50]], ['proportional', [46.74, 53.27]], ['balance_only', [100.01, 0]],
])('previews the same exact cents for %s', (mode, expected) => {
  expect(previewGroupCollection(100.01, [2400, 2735], mode)).toEqual(expected);
});
it('caps small debts, ignores settled/credit accounts and rejects invalid totals', () => {
  expect(previewGroupCollection(2, [.01, 100, 0, -50], 'equal')).toEqual([.01, 1.99, 0, 0]);
  expect(previewGroupCollection(2, [.01, 100], 'proportional')).toEqual([0, 2]);
  expect(previewGroupCollection(101, [.01, 100], 'equal')).toBeNull();
  expect(previewGroupCollection(.001, [100], 'equal')).toBeNull();
});
