import { describe, expect, it, vi } from 'vitest';

import {
  expenseCategoryLabel,
  invoiceTypeLabel,
  inventoryCategoryLabel,
  inventoryUnitLabel,
  paymentMethodLabel,
} from '@/lib/accountingLabels';

const translations = {
  'invoice.supplies': 'Malzemeler',
  'invoice.inventoryCategories.amenity': 'Misafir İkramı',
  'invoice.inventoryUnits.piece': 'Adet',
  'invoice.salesInvoice': 'Satış Faturası',
  'pms.cash': 'Nakit',
};

const t = vi.fn((key, fallback) => translations[key] || fallback);

describe('accounting labels', () => {
  it('localizes stored accounting codes without changing their data values', () => {
    expect(expenseCategoryLabel(t, 'supplies')).toBe('Malzemeler');
    expect(paymentMethodLabel(t, 'cash')).toBe('Nakit');
    expect(invoiceTypeLabel(t, 'sales')).toBe('Satış Faturası');
    expect(inventoryCategoryLabel(t, 'Amenity')).toBe('Misafir İkramı');
    expect(inventoryUnitLabel(t, 'pieces')).toBe('Adet');
  });

  it('turns unknown legacy codes into readable labels', () => {
    expect(inventoryCategoryLabel(t, 'guest_room_supply')).toBe('Guest Room Supply');
  });
});
