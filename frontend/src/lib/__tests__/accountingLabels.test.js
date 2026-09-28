import { describe, expect, it, vi } from 'vitest';

import {
  accountingQueueStatusLabel,
  expenseCategoryLabel,
  invoiceTypeLabel,
  inventoryCategoryLabel,
  inventoryUnitLabel,
  ledgerAccountTypeLabel,
  paymentMethodLabel,
  receivableTransactionTypeLabel,
} from '@/lib/accountingLabels';

const translations = {
  'invoice.supplies': 'Malzemeler',
  'invoice.inventoryCategories.amenity': 'Misafir İkramı',
  'invoice.inventoryUnits.piece': 'Adet',
  'invoice.salesInvoice': 'Satış Faturası',
  'pms.cash': 'Nakit',
  'finance.transactionTypes.charge': 'Tahakkuk',
  'finance.ledgerAccountTypes.asset': 'Varlık',
  'finance.accountingQueueStatuses.posted': 'Muhasebeleştirildi',
};

const t = vi.fn((key, fallback) => translations[key] || fallback);

describe('accounting labels', () => {
  it('localizes stored accounting codes without changing their data values', () => {
    expect(expenseCategoryLabel(t, 'supplies')).toBe('Malzemeler');
    expect(paymentMethodLabel(t, 'cash')).toBe('Nakit');
    expect(invoiceTypeLabel(t, 'sales')).toBe('Satış Faturası');
    expect(receivableTransactionTypeLabel(t, 'charge')).toBe('Tahakkuk');
    expect(ledgerAccountTypeLabel(t, 'asset')).toBe('Varlık');
    expect(accountingQueueStatusLabel(t, 'posted')).toBe('Muhasebeleştirildi');
    expect(inventoryCategoryLabel(t, 'Amenity')).toBe('Misafir İkramı');
    expect(inventoryUnitLabel(t, 'pieces')).toBe('Adet');
  });

  it('turns unknown legacy codes into readable labels', () => {
    expect(inventoryCategoryLabel(t, 'guest_room_supply')).toBe('Guest Room Supply');
  });
});
