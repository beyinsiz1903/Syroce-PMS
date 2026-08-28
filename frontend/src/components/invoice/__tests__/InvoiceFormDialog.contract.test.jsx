import { describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import { createAccountingInvoice } from '@/components/invoice/InvoiceFormDialog';

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
    };
    axios.post.mockResolvedValue({ data: { id: 'invoice-1' } });

    await createAccountingInvoice(invoice);

    expect(axios.post).toHaveBeenCalledWith('/accounting/invoices', invoice);
  });
});
