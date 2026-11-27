import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import CostAnalyticsView from '../CostAnalyticsView';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr-TR' } }) }));
vi.mock('@/context/CurrencyContext', () => ({ useCurrency: () => ({ code: 'TRY' }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-11-13' }));

const payload = { reporting_currency: 'TRY', total_expenses: 1100, count: 2,
  categories: { food: { amount: 1100, count: 2 } }, currency_policy: { complete: true } };

describe('property-currency expense analytics', () => {
  beforeEach(() => { vi.clearAllMocks(); axios.get.mockResolvedValue({ data: payload }); });

  it('uses one server-valued result for the PMS period without a native-currency selector', async () => {
    render(<CostAnalyticsView />);
    expect(await screen.findByText(/Rapor para birimi: TRY/)).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledWith('/reports/expense-accruals', { params: { start_date: '2026-11-01', end_date: '2026-11-13' } });
    expect((await screen.findAllByText('₺1.100,00')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('exports the same server-valued total and currency in CSV', async () => {
    let captured;
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(blob => { captured = blob; return 'blob:test'; });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    try {
      render(<CostAnalyticsView />);
      await screen.findAllByText('₺1.100,00');
      fireEvent.click(screen.getByRole('button', { name: 'costAnalytics.exportCsv' }));
      const csv = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsText(captured);
      });
      expect(csv).toContain('"TRY","costAnalytics.categories.food","2","1100.00","550.00","100.00%"');
      expect(csv).not.toContain('USD');
      expect(click).toHaveBeenCalledOnce();
    } finally {
      click.mockRestore();
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
    }
  });

  it('shows unavailable FX and never turns an incomplete total into zero', async () => {
    axios.get.mockResolvedValue({ data: { ...payload, total_expenses: null,
      categories: { food: { amount: null, count: 2 } }, currency_policy: { complete: false } } });
    render(<CostAnalyticsView />);
    expect(await screen.findByText(/Tarihî kur veya tutar kanıtı eksik/)).toBeInTheDocument();
    expect(screen.getAllByText('Doğrulanamadı').length).toBeGreaterThan(0);
    expect(screen.queryByText('₺0,00')).not.toBeInTheDocument();
  });

  it('keeps a failed report visibly unavailable', async () => {
    axios.get.mockRejectedValue(new Error('offline'));
    render(<CostAnalyticsView />);
    expect(await screen.findByRole('alert')).toHaveTextContent('costAnalytics.loadError');
    expect(screen.queryByText('₺0,00')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'costAnalytics.exportCsv' })).toBeDisabled();
  });
});
