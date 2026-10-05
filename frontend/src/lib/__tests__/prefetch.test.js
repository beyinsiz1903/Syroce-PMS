import { describe, expect, it } from 'vitest';
import { canPrefetchHeavyModules } from '../prefetch';

describe('automatic heavy-route prefetch policy', () => {
  it('does not compete with the active workspace on data-saving or slow connections', () => {
    expect(canPrefetchHeavyModules({ saveData: true, effectiveType: '4g' })).toBe(false);
    expect(canPrefetchHeavyModules({ saveData: false, effectiveType: '3g' })).toBe(false);
  });

  it('keeps automatic warming on a normal connection', () => {
    expect(canPrefetchHeavyModules({ saveData: false, effectiveType: '4g' })).toBe(true);
    expect(canPrefetchHeavyModules(null)).toBe(true);
  });
});
