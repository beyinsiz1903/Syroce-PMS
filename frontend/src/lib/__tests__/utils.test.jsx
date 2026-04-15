import { describe, it, expect } from 'vitest';
import { cn } from '../utils';

describe('cn utility', () => {
  it('merges class names', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1');
  });

  it('handles conditional classes', () => {
    const result = cn('base', false && 'hidden', 'visible');
    expect(result).toBe('base visible');
  });

  it('resolves tailwind conflicts (last wins)', () => {
    const result = cn('p-4', 'p-2');
    expect(result).toBe('p-2');
  });

  it('handles empty input', () => {
    expect(cn()).toBe('');
  });

  it('handles undefined and null', () => {
    expect(cn(undefined, null, 'valid')).toBe('valid');
  });
});
