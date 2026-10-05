import { describe, expect, it } from 'vitest';
import { isMoneyInput, parseMoneyInput } from '../moneyInput';

describe('money input', () => {
  it('accepts Turkish and dot decimal separators without changing the typed value', () => {
    expect(isMoneyInput('150,74')).toBe(true);
    expect(isMoneyInput('150.74')).toBe(true);
    expect(parseMoneyInput('150,74')).toBe(150.74);
    expect(parseMoneyInput('150.74')).toBe(150.74);
  });

  it('allows an in-progress decimal but rejects it until the amount is complete', () => {
    expect(isMoneyInput('150,')).toBe(true);
    expect(parseMoneyInput('150,')).toBeNull();
  });

  it('keeps payments to two decimal places and one separator', () => {
    expect(isMoneyInput('150,741')).toBe(false);
    expect(isMoneyInput('150,74,1')).toBe(false);
    expect(parseMoneyInput('150,741')).toBeNull();
  });
});
