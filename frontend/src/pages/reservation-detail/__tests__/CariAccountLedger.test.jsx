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

it('distinguishes a source charge from the same amount transferred out of the company', async () => {
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pms/cari-accounts' ? { accounts } : { transactions: [
    { id: 'charge', transaction_type: 'charge', amount: 150, currency: 'TRY', description: 'Original receivable' },
    { id: 'out', transaction_type: 'transfer_out', amount: 150, currency: 'TRY', description: 'Agency transfer' },
  ] } }));
  render(<CariAccountLedger />);
  await screen.findByRole('option', { name: 'Company (TRY)' });
  fireEvent.change(screen.getByLabelText('Hareketleri gösterilecek cari hesap'), { target: { value: 'company' } });
  await screen.findByText('Original receivable');
  const charge = screen.getByText('Original receivable').closest('tr');
  const transfer = screen.getByText('Agency transfer').closest('tr');
  expect(charge).toHaveTextContent('Hesaba eklenen alacak');
  expect(charge).toHaveTextContent('+150 TRY');
  expect(transfer).toHaveTextContent('−150 TRY');
  expect(screen.getByRole('columnheader', { name: 'İşlem tutarı' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Bakiyeye etkisi' })).toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
});

it('uses explicit debit and credit kinds without changing currency or negative reversal signs', async () => {
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pms/cari-accounts' ? { accounts } : { transactions: [
    { id: 'in', transaction_type: 'transfer_in', amount: 20, currency: 'EUR', description: 'incoming' },
    { id: 'payment', transaction_type: 'payment', amount: 10, currency: 'TRY', description: 'paid' },
    { id: 'adjustment', transaction_type: 'adjustment', amount: 5, currency: 'TRY', description: 'credit adjustment' },
    { id: 'reverse', transaction_type: 'payment', amount: -10, currency: 'TRY', description: 'reversed payment' },
  ] } }));
  render(<CariAccountLedger />);
  await screen.findByRole('option', { name: 'Agency (TRY)' });
  fireEvent.change(screen.getByLabelText('Hareketleri gösterilecek cari hesap'), { target: { value: 'agency' } });
  await screen.findByText('incoming');
  expect(screen.getByText('incoming').closest('tr')).toHaveTextContent('+20 EUR');
  expect(screen.getByText('paid').closest('tr')).toHaveTextContent('−10 TRY');
  expect(screen.getByText('credit adjustment').closest('tr')).toHaveTextContent('−5 TRY');
  expect(screen.getByText('reversed payment').closest('tr')).toHaveTextContent('+10 TRY');
});

it('does not guess a balance effect for unknown, missing or invalid source values', async () => {
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pms/cari-accounts' ? { accounts } : { transactions: [
    { id: 'unknown', transaction_type: 'future_kind', amount: 10, currency: 'TRY', description: 'unknown' },
    { id: 'missing', transaction_type: 'charge', amount: 10, description: 'missing currency' },
    { id: 'invalid', transaction_type: 'charge', amount: null, currency: 'TRY', description: 'missing amount' },
  ] } }));
  render(<CariAccountLedger />);
  await screen.findByRole('option', { name: 'Agency (TRY)' });
  fireEvent.change(screen.getByLabelText('Hareketleri gösterilecek cari hesap'), { target: { value: 'agency' } });
  await screen.findByText('unknown');
  expect(screen.getAllByText('Etki doğrulanamadı')).toHaveLength(3);
  expect(screen.getByText('Diğer cari hareket')).toBeInTheDocument();
});

it('does not present voided, deleted or unposted sources as active balance changes', async () => {
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pms/cari-accounts' ? { accounts } : { transactions: [
    { id: 'void', transaction_type: 'charge', amount: 150, currency: 'TRY', voided: true },
    { id: 'deleted', transaction_type: 'payment', amount: 20, currency: 'TRY', deleted: true },
    { id: 'pending', transaction_type: 'payment', amount: 30, currency: 'TRY', status: 'pending' },
  ] } }));
  render(<CariAccountLedger />);
  await screen.findByRole('option', { name: 'Agency (TRY)' });
  fireEvent.change(screen.getByLabelText('Hareketleri gösterilecek cari hesap'), { target: { value: 'agency' } });
  expect(await screen.findAllByText('Bakiyeye dahil değil')).toHaveLength(3);
  expect(screen.queryByText('+150 TRY')).not.toBeInTheDocument();
  expect(screen.queryByText('−20 TRY')).not.toBeInTheDocument();
});
