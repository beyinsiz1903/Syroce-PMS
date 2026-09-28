import { describe, expect, it } from 'vitest';

import {
  DEFAULT_EXPENSE_VAT_RATE,
  createBankAccountInitialState,
} from '@/components/invoice/AccountingDialogs';
import tr from '@/locales/tr.json';
import en from '@/locales/en.json';

describe('accounting dialog defaults', () => {
  it('uses the current standard VAT rate for a new expense', () => {
    expect(DEFAULT_EXPENSE_VAT_RATE).toBe(20);
  });

  it('starts a bank account in the tenant currency instead of fixed TRY', () => {
    expect(createBankAccountInitialState('EUR')).toMatchObject({ currency: 'EUR', balance: 0 });
    expect(createBankAccountInitialState('USD')).toMatchObject({ currency: 'USD', balance: 0 });
  });

  it('has native labels for every accounting dialog in Turkish and English', () => {
    const keys = [
      'recordExpense', 'amountExclVAT', 'currency', 'supplierOptional', 'selectSupplier',
      'totalInclVAT', 'addSupplier', 'taxOffice', 'addBankAccount', 'accountName',
      'bankName', 'accountNumber', 'openingBalance', 'addInventoryItem', 'itemName',
      'unit', 'reorderLevel',
    ];
    keys.forEach((key) => {
      expect(tr.invoice[key]).toBeTruthy();
      expect(en.invoice[key]).toBeTruthy();
    });
  });
});
