import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import axios from 'axios';
import AccountsView from '../AccountsView';
vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
const accounts = [{ id: 'c', name: 'Kurumsal müşteri', currency: 'TRY' }];
beforeEach(() => vi.clearAllMocks());
it('restricts financial statement access', () => {
  render(<AccountsView accounts={accounts} reload={vi.fn()} />);
  expect(screen.queryByRole('button', { name: 'Hesap dökümü' })).not.toBeInTheDocument();
});
it('loads a fresh verified statement separately from contacts', async () => {
  axios.get.mockResolvedValue({ data: { notice: 'Teklif borç değildir.', rows: [{ event_id: 'e', name: 'Çalıştay', currency: 'TRY', quoted_total: 3000, posted_total: null, net_collected: 0, outstanding: null, customer_credit: null, issues: ['Mutabakat bekliyor'] }], totals_by_currency: {}, excluded_count: 1 } });
  render(<AccountsView accounts={accounts} reload={vi.fn()} canFinance />);
  fireEvent.click(screen.getByRole('button', { name: 'Hesap dökümü' }));
  expect(await screen.findByText('Mutabakat bekliyor')).toBeInTheDocument();
  expect(screen.getByText(/Kalan alacak: Doğrulanmadı/)).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith('/mice/accounts/c/statement');
  expect(axios.get).toHaveBeenCalledTimes(1);
});
it('shows failure instead of a zero balance', async () => {
  axios.get.mockRejectedValue(new Error('offline'));
  render(<AccountsView accounts={accounts} reload={vi.fn()} canFinance />);
  fireEvent.click(screen.getByRole('button', { name: 'Hesap dökümü' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Hesap dökümü yüklenemedi');
});
