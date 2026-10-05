import { describe, expect, it } from 'vitest';
import { getReportContract } from '../reportContracts';

describe('report contracts', () => {
  it('keeps ADR and RevPAR definitions explicit and separate from collections', () => {
    const contract = getReportContract('adr_revpar');
    expect(contract.financialScope).toContain('ADR = oda geliri / satılan oda-gecesi');
    expect(contract.financialScope).toContain('RevPAR = oda geliri / satılabilir oda-gecesi');
    expect(contract.financialScope).not.toContain('Tahsilat');
  });

  it('states that payment reports do not treat price corrections as collections', () => {
    expect(getReportContract('payments').financialScope).toContain('fiyat düzeltmeleri hariçtir');
  });

  it('never claims that unlike currencies are arithmetically combined', () => {
    expect(getReportContract('revenue').currencyRule).toContain('toplanmaz');
  });
});
