import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReportBuilder from '../ReportBuilder';
import { fetchJsonWithRetry, fetchWithRetry } from '@/lib/fetchRetry';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
vi.mock('@/lib/fetchRetry', () => ({ fetchJsonWithRetry: vi.fn(), fetchWithRetry: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const response = {
  data: [{ total_amount: 100, currency: 'EUR' }, { total_amount: 200, currency: 'USD' }],
  columns: ['total_amount', 'currency'], column_labels: { total_amount: 'Tutar', currency: 'Para Birimi' },
  total_count: 2, matched_count: 20, truncated: true,
  summary: { total_amount: { sum: null, by_currency: {
    EUR: { sum: 100, avg: 100, min: 100, max: 100 }, USD: { sum: 200, avg: 200, min: 200, max: 200 },
  } } },
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchJsonWithRetry.mockImplementation(async url => url.endsWith('/config') ? {
    currency_code: 'TRY', data_sources: { reservations: { label: 'Rezervasyonlar', columns: {
      total_amount: { label: 'Tutar', type: 'currency' }, currency: { label: 'Para Birimi', type: 'text' },
    } } },
  } : { templates: [] });
  fetchWithRetry.mockResolvedValue({ ok: true, json: async () => response });
});

async function configure() {
  render(<ReportBuilder />);
  fireEvent.click(await screen.findByTestId('source-reservations'));
  fireEvent.click(screen.getByTestId('col-total_amount'));
}

describe('Report Builder financial integrity', () => {
  it('shows server-added currencies, currency-specific summaries and bounded report notice', async () => {
    await configure();
    fireEvent.click(screen.getByTestId('generate-report-btn'));
    const table = await screen.findByTestId('report-table');
    expect(within(table).getByText('EUR')).toBeInTheDocument();
    expect(within(table).getByText('USD')).toBeInTheDocument();
    expect(table.textContent).not.toContain('₺');
    const summary = screen.getByTestId('summary-total_amount');
    expect(summary.textContent).toContain('€');
    expect(summary.textContent).toContain('$');
    expect(summary.textContent).not.toContain('300');
    expect(screen.getByRole('status')).toHaveTextContent('20 kaydın ilk 2 satırı');
  });

  it('does not display stale responses after the requested columns change', async () => {
    let resolve;
    fetchWithRetry.mockReturnValue(new Promise(done => { resolve = done; }));
    await configure();
    fireEvent.click(screen.getByTestId('generate-report-btn'));
    fireEvent.click(screen.getByTestId('col-currency'));
    await act(async () => { resolve({ ok: true, json: async () => response }); });
    await waitFor(() => expect(screen.queryByTestId('report-table')).not.toBeInTheDocument());
  });
});
