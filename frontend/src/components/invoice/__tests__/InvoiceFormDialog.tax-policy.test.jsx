import { describe, expect, it } from 'vitest';

import {
  INVOICE_ITEM_CATEGORIES,
  createInvoiceItem,
} from '@/components/invoice/InvoiceFormDialog';

describe('invoice item tax policy', () => {
  it('uses the accommodation VAT rate for the initial invoice line', () => {
    expect(createInvoiceItem()).toMatchObject({
      category: 'accommodation',
      description: 'Konaklama Bedeli',
      vat_rate: 10,
    });
  });

  it('keeps food and alcoholic beverage VAT rates separate', () => {
    expect(INVOICE_ITEM_CATEGORIES.food_beverage.vatRate).toBe(10);
    expect(INVOICE_ITEM_CATEGORIES.alcoholic_beverage.vatRate).toBe(20);
    expect(createInvoiceItem('other').vat_rate).toBe(20);
  });
});
