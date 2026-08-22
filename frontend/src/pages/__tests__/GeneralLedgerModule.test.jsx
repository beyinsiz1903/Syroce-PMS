import { describe, expect, it } from 'vitest';

import {
  collectIntegrationAccountCodes,
  formatAccountMapping,
  getJournalValidationError,
  GL_ENDPOINTS,
  mergeAccountBalances,
  normalizeTrialBalance,
  parseAccountMapping,
  toJournalPayload,
} from '@/pages/GeneralLedgerModule';

describe('GeneralLedgerModule persistent GL contract', () => {
  it('uses the tenant-scoped persistent journal endpoint', () => {
    expect(GL_ENDPOINTS).toEqual({
      accounts: '/gl/accounts',
      initializeAccounts: '/gl/accounts/initialize',
      journal: '/gl/journal',
      sequenceAudit: '/gl/sequence-audit',
      trialBalance: '/gl/trial-balance',
      periods: '/gl/periods',
      initializePeriods: '/gl/periods/initialize',
      yearEnd: '/gl/year-end',
      closeYear: '/gl/year-end/close',
      incomeStatement: '/gl/statements/income-statement',
      balanceSheet: '/gl/statements/balance-sheet',
      comparativeIncome: '/gl/statements/comparative-income-statement',
      comparativeBalance: '/gl/statements/comparative-balance-sheet',
      exportReport: '/gl/reports/export',
      fxRevalue: '/gl/fx/revalue',
      chainConsolidated: '/gl/chain/consolidated',
      intercompanyRules: '/gl/chain/intercompany-rules',
      eledgerSettings: '/gl/e-ledger/settings',
      eledgerPreflight: '/gl/e-ledger/preflight',
      eledgerSourcePackage: '/gl/e-ledger/source-package',
      operationalMapping: '/gl/integrations/operational/mapping',
      operationalStatus: '/gl/integrations/operational/status',
      nilveraSettings: '/gl/integrations/nilvera/settings',
      nilveraQueue: '/gl/integrations/nilvera/queue',
      apGLMapping: '/ap/gl-mapping',
      fixedAssetGLMapping: '/fixed-assets/gl-mapping',
    });
  });

  it('passes the stable manual-post idempotency key to the backend', () => {
    expect(toJournalPayload({
      date: '2026-08-13',
      type: 'Mahsup',
      description: 'Tekrar güvenli fiş',
      idempotency_key: 'manual-request-123',
      lines: [
        { account_code: '100', debit: 10, credit: 0, description: '' },
        { account_code: '600', debit: 0, credit: 10, description: '' },
      ],
    }).idempotency_key).toBe('manual-request-123');
  });

  it('maps the form to the durable journal payload', () => {
    expect(toJournalPayload({
      date: '2026-08-13',
      type: 'Mahsup',
      description: ' Test fişi ',
      lines: [
        { account_code: ' 100 ', debit: 100, credit: 0, description: ' Borç ' },
        { account_code: '600', debit: 0, credit: 100, description: '' },
      ],
    })).toEqual({
      date: '2026-08-13',
      memo: 'Test fişi',
      source: 'manual',
      source_ref: 'Mahsup',
      lines: [
        { account_code: '100', debit: 100, credit: 0, memo: 'Borç' },
        { account_code: '600', debit: 0, credit: 100, memo: null },
      ],
    });
  });

  it('keeps the journal save action disabled until the form is valid', () => {
    expect(getJournalValidationError({ description: '', lines: [
      { account_code: '', debit: 0, credit: 0 },
      { account_code: '', debit: 0, credit: 0 },
    ] })).toBe('Fiş toplamı 0 olamaz.');
    expect(getJournalValidationError({ description: 'Dengeli fiş', lines: [
      { account_code: '100', debit: 100, credit: 0 },
      { account_code: '600', debit: 0, credit: 100 },
    ] })).toBe('');
  });

  it('adds validated foreign-currency metadata when present', () => {
    const payload = toJournalPayload({
      date: '2026-08-13',
      type: 'Mahsup',
      description: 'USD banka',
      lines: [
        { account_code: '102', debit: 3200, credit: 0, description: '', currency: 'usd', foreign_amount: '100', exchange_rate: '32' },
        { account_code: '590', debit: 0, credit: 3200, description: '' },
      ],
    });
    expect(payload.lines[0]).toMatchObject({ currency: 'USD', foreign_amount: 100, exchange_rate: 32 });
    expect(payload.lines[1]).not.toHaveProperty('currency');
  });

  it('normalizes the persistent trial-balance response for the table', () => {
    expect(normalizeTrialBalance({
      rows: [{
        account_code: '100',
        account_name: 'Kasa',
        total_debit: 150,
        total_credit: 50,
        debit_balance: 100,
        credit_balance: 0,
      }],
      totals: { debit_balance: 100, credit_balance: 100, balanced: true },
    })).toEqual({
      lines: [{
        code: '100',
        name: 'Kasa',
        total_debit: 150,
        total_credit: 50,
        balance_type: 'Borç',
        balance: 100,
      }],
      totals: { total_debit: 100, total_credit: 100, balanced: true },
    });
  });

  it('derives current account balances from the durable trial balance', () => {
    expect(mergeAccountBalances(
      [{ code: '100', name: 'Kasa' }, { code: '600', name: 'Satışlar' }],
      {
        rows: [
          { account_code: '100', debit_balance: 125, credit_balance: 0 },
          { account_code: '600', debit_balance: 0, credit_balance: 125 },
        ],
      }
    )).toEqual([
      { code: '100', name: 'Kasa', balance: 125 },
      { code: '600', name: 'Satışlar', balance: -125 },
    ]);
  });

  it('round-trips Nilvera code and rate account mappings', () => {
    const mapping = parseAccountMapping('20=391.20, 10:391.10\n1=391.01', 'KDV');
    expect(mapping).toEqual({ 20: '391.20', 10: '391.10', 1: '391.01' });
    expect(formatAccountMapping(mapping)).toBe('1=391.01, 10=391.10, 20=391.20');
  });

  it('rejects malformed Nilvera account mappings before saving', () => {
    expect(() => parseAccountMapping('20-391.20', 'KDV')).toThrow('kod=hesap');
  });

  it('lists every direct and granular integration account once', () => {
    expect(collectIntegrationAccountCodes(
      {
        incoming_purchase_account_code: '153',
        incoming_vat_account_code: '191',
        outgoing_vat_account_code: '391',
        outgoing_vat_accounts_by_rate: { 20: '391.20' },
      },
      { expense_account_code: '770', input_vat_account_code: '191' },
      { accumulated_depreciation_account_code: '257' },
    )).toEqual(['153', '191', '257', '391', '391.20', '770']);
  });
});
