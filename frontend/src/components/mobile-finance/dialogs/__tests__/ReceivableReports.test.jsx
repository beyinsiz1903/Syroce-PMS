import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { formatCurrency } from '@/lib/currency';
import RiskModal from '../RiskModal';
import FolioExtractModal from '../FolioExtractModal';
import InvoicesModal from '../InvoicesModal';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
const format = (amount, currency) => formatCurrency(amount, currency, { decimals: 2 });

describe('Receivable report currency contracts', () => {
  it('shows the overdue summary in each original currency, not a TRY sum', () => {
    render(<RiskModal riskModalOpen setRiskModalOpen={() => {}} formatCurrency={format}
      getRiskColor={() => ''} getRiskIcon={() => null} loadFolioExtract={() => {}}
      overdueAccounts={{ overdue_accounts: [{ folio_id: 'f', balance: 80, currency: 'EUR', days_overdue: 31, checkout_date: '2026-09-01' }],
        summary: { total_count: 1, total_amount: null, totals_by_currency: { EUR: 80, TRY: 100 } } }} />);
    expect(screen.getByText(/EUR:.*80,00.*TRY:.*100,00/)).toBeInTheDocument();
    expect(screen.queryByText('₺180,00')).not.toBeInTheDocument();
  });

  it('preserves mixed-currency balance and signed refunds on the folio statement', () => {
    render(<FolioExtractModal folioExtractModalOpen setFolioExtractModalOpen={() => {}} formatCurrency={format}
      selectedFolioExtract={{ folio: { currency: 'TRY' }, charges: [], payments: [{ id: 'r', amount: -10, currency: 'EUR' }],
        summary: { total_charges: null, total_payments: -10, current_balance: null,
          charges_by_currency: { EUR: 100, TRY: 50 }, payments_by_currency: { EUR: -10 }, balance_by_currency: { EUR: 110, TRY: 50 } } }} />);
    expect(screen.getByText(/EUR:.*110,00.*TRY:.*50,00/)).toBeInTheDocument();
    expect(screen.getAllByText(/-€10,00/).length).toBeGreaterThan(0);
    expect(screen.queryByText('₺0,00')).not.toBeInTheDocument();
  });

  it('reads invoice total, creation date and partial outstanding amount from the real API fields', () => {
    render(<InvoicesModal invoicesModalOpen setInvoicesModalOpen={() => {}} formatCurrency={format}
      allInvoices={[{ id: 'i', invoice_number: 'INV-1', total: 1000.49, outstanding_amount: 800.29,
        currency: 'EUR', created_at: '2026-10-02T12:00:00Z', status: 'partial' }]} />);
    expect(screen.getByText(/1\.000,49.*€/)).toBeInTheDocument();
    expect(screen.getByText(/Kalan bakiye:.*800,29.*€/)).toBeInTheDocument();
    expect(screen.getByText(/02\.10\.2026/)).toBeInTheDocument();
    expect(screen.queryByText(/N\/A/)).not.toBeInTheDocument();
  });
});
