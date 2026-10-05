import { describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import {
  SUPPORTED_INVOICE_CURRENCIES,
  createAccountingInvoice,
  withSubmittedDueDate,
} from '@/components/invoice/InvoiceFormDialog';

vi.mock('axios', () => ({
  default: { post: vi.fn() },
}));

describe('InvoiceFormDialog accounting contract', () => {
  it('posts the invoice as the JSON request body used by the existing accounting endpoint', async () => {
    const invoice = {
      invoice_type: 'sales',
      customer_name: 'Test Cari',
      customer_email: '',
      customer_tax_office: '',
      customer_tax_number: '1234567890',
      customer_address: '',
      items: [
        {
          description: 'Konaklama',
          quantity: 1,
          unit_price: 1000,
          vat_rate: 20,
        },
      ],
      due_date: '2026-08-28',
      notes: '',
      currency: 'EUR',
      exchange_rate: 48.25,
    };
    axios.post.mockResolvedValue({ data: { id: 'invoice-1' } });

    await createAccountingInvoice(invoice);

    expect(axios.post).toHaveBeenCalledWith('/accounting/invoices', invoice);
  });

  it('offers every accounting currency supported by the invoice backend', () => {
    expect(SUPPORTED_INVOICE_CURRENCIES).toEqual(['TRY', 'EUR', 'USD', 'GBP']);
  });

  it('uses the date currently submitted by the form instead of a stale dialog state value', () => {
    expect(withSubmittedDueDate({ due_date: '' }, '2026-09-15')).toEqual({ due_date: '2026-09-15' });
    expect(withSubmittedDueDate({ due_date: '2026-09-15' }, null)).toEqual({ due_date: '2026-09-15' });
  });
});
