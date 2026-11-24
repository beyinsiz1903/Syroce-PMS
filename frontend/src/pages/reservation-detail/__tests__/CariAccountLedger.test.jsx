import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import CariAccountLedger from '../CariAccountLedger';
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../helpers', () => ({ fmtCurrency: (value, currency) => `${value} ${currency}`, fmtTs: value => value || '—' }));
const accounts = [
  { id: 'company', name: 'Company', currency: 'TRY', balance: 0, account_source: 'cari_accounts' },
  { id: 'agency', name: 'Agency', currency: 'TRY', balance: 150, account_source: 'cari_accounts' },
  { id: 'old', name: 'Legacy', currency: 'TRY', balance: 20, account_source: 'city_ledger_accounts' },
];
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);
it('reads agency transfer sources and balances without creating a collection or mixing legacy ledgers', async () => {
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pms/cari-accounts'
    ? { accounts } : { transactions: [{ id: 'transfer:in', transaction_type: 'transfer_in', amount: 150, currency: 'TRY', business_date: '2026-11-12', description: 'NOV24-CARI-AGENCY-001' }] } }));
  render(<CariAccountLedger />);
  await screen.findByRole('option', { name: 'Agency (TRY)' });
  expect(screen.queryByRole('option', { name: 'Legacy (TRY)' })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Hareketleri gösterilecek cari hesap'), { target: { value: 'agency' } });
  expect(await screen.findByText('NOV24-CARI-AGENCY-001')).toBeInTheDocument();
  expect(screen.getByText('Acenteye devralınan alacak')).toBeInTheDocument();
  expect(screen.getByText('2026-11-12')).toBeInTheDocument();
  expect(screen.getAllByText('150 TRY')).toHaveLength(2);
  expect(axios.post).not.toHaveBeenCalled();
});
it('clears previous account rows on a failed refresh instead of displaying stale acceptance evidence', async () => {
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pms/cari-accounts' ? { accounts } : { transactions: [{ id: 't', description: 'old evidence', amount: 150, currency: 'TRY' }] } }));
  render(<CariAccountLedger />);
  await screen.findByRole('option', { name: 'Agency (TRY)' });
  fireEvent.change(screen.getByLabelText('Hareketleri gösterilecek cari hesap'), { target: { value: 'agency' } });
  await screen.findByText('old evidence');
  axios.get.mockRejectedValue(new Error('offline'));
  fireEvent.click(screen.getByText('Hareketleri yenile'));
  await act(async () => {});
  expect(screen.getByRole('alert')).toHaveTextContent('yüklenemedi');
  expect(screen.queryByText('old evidence')).not.toBeInTheDocument();
  expect(screen.queryByText('Bu hesap için kayıtlı hareket yok.')).not.toBeInTheDocument();
});
