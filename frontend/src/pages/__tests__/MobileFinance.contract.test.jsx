import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));

import MobileFinance from '@/pages/MobileFinance';

describe('MobileFinance modal contract', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation((url) => {
      if (url === '/finance/mobile/daily-collections') {
        return Promise.resolve({ data: { total_collected: 0, payment_count: 0 } });
      }
      if (url === '/finance/mobile/monthly-collections') {
        return Promise.resolve({ data: { total_collected: 0, collection_rate: 0 } });
      }
      if (url === '/finance/mobile/pending-receivables') {
        return Promise.resolve({ data: { total_pending: 0, receivables_count: 0, receivables: [] } });
      }
      if (url === '/finance/mobile/monthly-costs') {
        return Promise.resolve({ data: { total_costs: 0 } });
      }
      if (url === '/notifications/mobile/finance') {
        return Promise.resolve({ data: { notifications: [] } });
      }
      if (url === '/finance/mobile/invoices') {
        return Promise.resolve({ data: { invoices: [] } });
      }
      if (url === '/finance/mobile/cash-flow-summary') {
        return Promise.resolve({ data: null });
      }
      if (url === '/finance/mobile/risk-alerts') {
        return Promise.resolve({
          data: {
            summary: { total_alerts: 1 },
            alerts: [{ id: 'risk-1', severity: 'high', title: 'Risk', message: 'Review' }],
          },
        });
      }
      if (url === '/finance/mobile/daily-expenses') {
        return Promise.resolve({ data: null });
      }
      if (url === '/finance/mobile/bank-balances') {
        return Promise.resolve({ data: null });
      }
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  afterEach(cleanup);

  it('renders provider risk data without an undefined modal helper crash', async () => {
    render(
      <MemoryRouter>
        <MobileFinance user={{ name: 'Test Operator' }} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(get).toHaveBeenCalledTimes(10));
    expect(await screen.findByText('Risk Yönetimi')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
  });

  it('preserves cents on finance amounts above one thousand', async () => {
    const defaultGet = get.getMockImplementation();
    get.mockImplementation(url => url === '/finance/mobile/daily-collections'
      ? Promise.resolve({ data: { total_collected: 1000.49, totals_by_currency: { TRY: 1000.49 }, payment_count: 1 } })
      : defaultGet(url));
    render(<MemoryRouter><MobileFinance user={{ name: 'Test Operator' }} /></MemoryRouter>);
    expect((await screen.findAllByText('₺1.000,49')).length).toBeGreaterThan(0);
    expect(screen.queryByText('₺1.000')).not.toBeInTheDocument();
  });

  it('does not present failed finance data as a zero balance', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const defaultGet = get.getMockImplementation();
    get.mockImplementation(url => url === '/finance/mobile/pending-receivables'
      ? Promise.reject(new Error('ledger unavailable')) : defaultGet(url));
    render(<MemoryRouter><MobileFinance /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Gösterilmeyen tutarlar sıfır bakiye değildir');
    expect(screen.queryByText('₺0,00')).not.toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it('makes receivables beyond the first ten reachable and searchable by guest or folio', async () => {
    const defaultGet = get.getMockImplementation();
    const receivables = Array.from({ length: 17 }, (_, index) => ({
      folio_id: `folio-${index}`, folio_number: `F-${index}`, guest_name: `Guest ${index}`,
      balance: 50, currency: 'TRY',
    }));
    receivables[10] = { ...receivables[10], folio_number: 'F-2026-00411', guest_name: 'Deniz Karaca' };
    get.mockImplementation(url => url === '/finance/mobile/pending-receivables'
      ? Promise.resolve({ data: { receivables_count: 17, receivables, total_pending: 850 } }) : defaultGet(url));
    render(<MemoryRouter><MobileFinance /></MemoryRouter>);
    await screen.findByText('Bekleyen Alacaklar (17)');
    expect(screen.queryByText('Deniz Karaca')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Diğer alacakları göster (7)' }));
    expect(screen.getByText('Deniz Karaca')).toBeVisible();
    expect(screen.getByText('Guest 16')).toBeVisible();
    expect(screen.queryByRole('button', { name: /Diğer alacakları göster/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Alacaklarda misafir veya folyo ara' }), { target: { value: '00411' } });
    expect(screen.getByText('Deniz Karaca')).toBeVisible();
    expect(screen.queryByText('Guest 0')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Alacaklarda misafir veya folyo ara' }), { target: { value: 'bilinmeyen' } });
    expect(screen.getByText('Aramayla eşleşen alacak yok.')).toBeVisible();
  });

  it('refreshes the cash-flow card together with current collections', async () => {
    render(<MemoryRouter><MobileFinance /></MemoryRouter>);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(10));
    expect(get).toHaveBeenCalledWith('/finance/mobile/cash-flow-summary', { params: { nocache: true } });
    get.mockClear();
    fireEvent.click(screen.getByRole('button', { name: /Yenile/ }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(10));
    expect(get).toHaveBeenCalledWith('/finance/mobile/cash-flow-summary', { params: { nocache: true } });
  });

});
