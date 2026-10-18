import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import InvoiceModule from '../InvoiceModule';

const { get, translate } = vi.hoisted(() => ({ get: vi.fn(), translate: (key, fallback) => typeof fallback === 'string' ? fallback : key }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));
vi.mock('@/context/CurrencyContext', () => ({ useCurrency: () => ({ code: 'TRY' }) }));
vi.mock('@/components/invoice/AccountingDialogs', () => ({ ExpenseDialog: () => null, SupplierDialog: () => null, BankAccountDialog: () => null, InventoryDialog: () => null }));
vi.mock('@/components/invoice/InvoiceFormDialog', () => ({ default: () => null }));
vi.mock('@/components/invoice/IncomingInvoicesTab', () => ({ default: () => null }));
vi.mock('@/components/invoice/InvoiceTemplate', () => ({ default: () => null }));

const report = {
  total_revenue_by_currency: { EUR: 2000.25 }, total_expenses_by_currency: { EUR: 10 },
  gross_profit_by_currency: { EUR: 1990.25 }, profit_margin_by_currency: { EUR: 99.5 },
};
const dashboard = {
  business_date: '2026-09-30', period: { start: '2026-09-01', end: '2026-09-30' }, currency: 'TRY',
  overdue_amount: 0, overdue_amount_by_currency: { EUR: 42.75 }, overdue_invoices: 1,
};

function setup() {
  get.mockImplementation(async url => {
    if (url === '/accounting/invoices') return { data: [] };
    if (url === '/accounting/dashboard') return { data: dashboard };
    if (url === '/accounting/reports/profit-loss') return { data: report };
    if (url === '/accounting/reports/vat-report') return { data: { sales_vat_by_currency: { EUR: 1 } } };
    if (url === '/accounting/reports/balance-sheet') return { data: { assets: {}, liabilities: {}, equity: {}, complete: false } };
    throw new Error(`Unexpected request ${url}`);
  });
  return render(<MemoryRouter initialEntries={['/invoices?tab=reports']}><InvoiceModule user={{ role: 'admin' }} tenant={{ id: 'A' }} /></MemoryRouter>);
}

describe('Invoice reporting contracts', () => {
  beforeEach(() => { get.mockReset(); });

  it('uses the server PMS day without shifting the first day across timezones', async () => {
    const view = setup();
    await waitFor(() => expect(get).toHaveBeenCalledWith('/accounting/reports/profit-loss', {
      params: { start_date: '2026-09-01', end_date: '2026-09-30', nocache: true },
    }));
    expect(await screen.findByText(/Nakit akışı veya genel muhasebe gelir tablosu değildir/)).toBeInTheDocument();
    expect(view.container.textContent).toContain('2.000,25');
    // Foreign-only overdue debt must not disappear just because TRY scalar is zero.
    expect(view.container.textContent).toContain('42,75');
    expect(screen.getByText(/Banka bakiyesi eksik/)).toBeInTheDocument();
    expect(screen.getByText('Operasyonel varlık ve borç özeti')).toBeInTheDocument();
  });

  it('does not leave previous totals visible after a failed refresh', async () => {
    setup();
    await screen.findByText(/Nakit akışı veya genel muhasebe gelir tablosu değildir/);
    get.mockImplementation(async url => {
      if (url === '/accounting/reports/profit-loss') throw new Error('Finans servisi kapalı');
      return { data: {} };
    });
    fireEvent.click(screen.getByRole('button', { name: 'Raporları yenile' }));
    expect(await screen.findByText(/Raporlar yüklenemedi: Finans servisi kapalı/)).toBeInTheDocument();
    expect(screen.queryByText(/Nakit akışı veya genel muhasebe gelir tablosu değildir/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Raporları yenile' })).toBeEnabled();
  });
});
