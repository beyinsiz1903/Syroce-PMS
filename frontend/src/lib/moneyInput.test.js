import { describe, expect, it } from 'vitest';
import { isValidMoneyInput, parseMoneyInput } from './moneyInput';

describe('parseMoneyInput', () => {
  it.each([
    ['150,74', 150.74],
    ['150.74', 150.74],
    ['1.500,74', 1500.74],
    ['1,500.74', 1500.74],
    [150.74, 150.74],
  ])('parses %s without silently dropping fractional cents', (value, expected) => {
    expect(parseMoneyInput(value)).toBe(expected);
  });

  it('rejects malformed values instead of coercing them', () => {
    expect(Number.isNaN(parseMoneyInput('150,74,2'))).toBe(true);
    expect(Number.isNaN(parseMoneyInput('150abc'))).toBe(true);
    expect(isValidMoneyInput('150,74', { min: 0.01 })).toBe(true);
    expect(isValidMoneyInput('0', { min: 0.01 })).toBe(false);
  });
});
