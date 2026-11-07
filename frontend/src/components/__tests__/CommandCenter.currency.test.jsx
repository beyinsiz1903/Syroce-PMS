import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { formatCurrency } from '@/lib/currency';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, options) => {
  if (key === 'commandCenter.alerts.pending_payments.description') return `Toplam ${options.amount}`;
  return options?.defaultValue || key;
} }) }));
vi.mock('@/context/CurrencyContext', () => ({ useCurrency: () => ({ format: value => formatCurrency(value, 'TRY') }) }));

import CommandCenter from '@/components/CommandCenter';

const response = (items) => ({ data: { currency: 'TRY', summary: {}, alerts: [{
  type: 'pending_payments', severity: 'medium', count: items.length, items,
  totals_by_currency: { USD: 1642.55, EUR: 1200.25 }, total_amount: null,
}] } });

describe('CommandCenter folio currency and read failures', () => {
  beforeEach(() => { get.mockReset(); });
  afterEach(() => { vi.restoreAllMocks(); });

  it('uses each guest ledger currency and retains cents above 1000, not the tenant currency', async () => {
    get.mockResolvedValue(response([
      { guest_name: 'Emre Kurt', balance: 1642.55, currency: 'USD' },
      { guest_name: 'Deniz Arslan', balance: 1200.25, currency: 'EUR' },
    ]));
    render(<CommandCenter />);
    const card = await screen.findByTestId('cc-alert-pending_payments');
    expect(within(card).getAllByText(formatCurrency(1642.55, 'USD', { decimals: 2 }))).toHaveLength(1);
    expect(within(card).getAllByText(formatCurrency(1200.25, 'EUR', { decimals: 2 }), { normalizer: text => text.trim() })).toHaveLength(1);
    expect(card).not.toHaveTextContent('₺');
    expect(card).toHaveTextContent(`Toplam ${formatCurrency(1642.55, 'USD', { decimals: 2 })} · ${formatCurrency(1200.25, 'EUR', { decimals: 2 })}`.replaceAll('\u00a0', ' '));
  });

  it('does not invent TRY for an item whose currency is absent', async () => {
    get.mockResolvedValue(response([{ guest_name: 'Emre Kurt', balance: 10 }]));
    render(<CommandCenter />);
    const card = await screen.findByTestId('cc-alert-pending_payments');
    expect(card).not.toHaveTextContent('₺');
    expect(card).toHaveTextContent('Para birimi doğrulanamadı');
  });

  it('shows an explicit retry when the initial financial read fails, never all-clear', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    get.mockRejectedValueOnce(new Error('unavailable')).mockResolvedValueOnce({ data: { alerts: [], summary: {} } });
    render(<CommandCenter />);
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('Güncel operasyon bilgileri alınamadı');
    expect(screen.queryByTestId('cc-no-alerts')).not.toBeInTheDocument();
    fireEvent.click(within(error).getByRole('button'));
    expect(await screen.findByTestId('cc-no-alerts')).toBeInTheDocument();
  });

  it('removes stale financial chips after a refresh failure', async () => {
    get.mockResolvedValueOnce(response([{ guest_name: 'Emre Kurt', balance: 10, currency: 'USD' }]))
      .mockRejectedValueOnce(new Error('unavailable'));
    render(<CommandCenter />);
    await screen.findByTestId('cc-alert-pending_payments');
    fireEvent.click(screen.getByTestId('cc-refresh'));
    await screen.findByRole('alert');
    expect(screen.queryByTestId('cc-alert-pending_payments')).not.toBeInTheDocument();
  });
});
