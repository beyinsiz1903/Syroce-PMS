import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import FlashReportContent from '../FlashReportContent';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/context/CurrencyContext', () => ({ useCurrency: () => ({ code: 'TRY' }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-09-15' }));

describe('Flash report accounting UI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uses the PMS day, keeps cents, and selects one currency for every money section', async () => {
    axios.get.mockResolvedValue({ data: { date: '2026-09-15', occupancy: { total: 10, occupied: 2, rate: 20 },
      revenue: { total: null, total_by_currency: { TRY: 1000.49, EUR: 20.25 }, collected_by_currency: { TRY: 200, EUR: 5 } },
      kpi: { adr_by_currency: { TRY: 500.245, EUR: 10.125 }, revpar_by_currency: { TRY: 100.049, EUR: 2.025 } },
      departments: [{ name: 'Oda Geliri', amount_by_currency: { TRY: 1000.49, EUR: 20.25 } }] } });
    render(<FlashReportContent showDatePicker />);
    const selector = await screen.findByRole('combobox', { name: /Rapor para birimi/ });
    expect(axios.get).toHaveBeenCalledWith('/reports/flash-report?date=2026-09-15');
    expect(within(screen.getByTestId('flash-collection')).getByText('₺1.000,49')).toBeInTheDocument();
    fireEvent.change(selector, { target: { value: 'EUR' } });
    expect(within(screen.getByTestId('flash-collection')).getByText(/20,25/)).toBeInTheDocument();
    expect(within(screen.getByTestId('flash-collection')).queryByText(/1\.000,49/)).not.toBeInTheDocument();
  });

  it('does not fabricate financial totals from reservation props after a server failure', async () => {
    axios.get.mockRejectedValue(new Error('Sunucuya ulaşılamadı'));
    render(<FlashReportContent rooms={[{ id: 'r' }]} bookings={[{ total_amount: 999999 }]} />);
    expect(await screen.findByTestId('flash-error')).toHaveTextContent('Sunucuya ulaşılamadı');
    expect(screen.queryByTestId('flash-collection')).not.toBeInTheDocument();
  });

  it('shows pending room prices separately and includes their currency even without posted room revenue', async () => {
    axios.get.mockResolvedValue({ data: { date: '2026-09-15', occupancy: { total: 10, occupied: 2, rate: 20 },
      revenue: { total_by_currency: { TRY: 20 }, collected_by_currency: {}, posting_pending: true,
        operational_adr_by_currency: { EUR: 2750 }, reservation_room_revenue_by_currency: { EUR: 5500 } },
      kpi: { adr_by_currency: {}, revpar_by_currency: {} } } });
    render(<FlashReportContent />);
    const selector = await screen.findByRole('combobox', { name: /Rapor para birimi/ });
    fireEvent.change(selector, { target: { value: 'EUR' } });
    expect(screen.getByTestId('flash-posting-pending')).toHaveTextContent(/2\.750,00/);
    expect(screen.getByTestId('flash-posting-pending')).toHaveTextContent(/5\.500,00/);
    expect(screen.getByTestId('flash-kpi-adr')).toHaveTextContent('İşlenen ADR (vergi dahil)');
    expect(screen.getByRole('link', { name: 'Doluluk / Forecast’i aç' })).toHaveAttribute('href', '/app/raporlar?section=forecast_reports');
  });
});
