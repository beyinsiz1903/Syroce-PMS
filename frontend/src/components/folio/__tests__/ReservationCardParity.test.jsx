import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { toast } from 'sonner';
import FolioCardTools from '../FolioCardTools';
import ReservationFolioDetails from '../ReservationFolioDetails';
import FolioViewDialog from '@/components/pms/FolioViewDialog';
import { FoliosTab } from '@/pages/reservation-detail/FoliosTab';
import ReservationOccupancyEditor from '@/pages/reservation-detail/ReservationOccupancyEditor';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k, f) => f || k }) }));
const booking = { id: 'b1', currency: 'TRY', adults: 2, children: 1, children_ages: [8], check_in: '2026-11-15', check_out: '2026-11-17', total_amount: 1000 };
const folios = [
  { id: 'f1', booking_id: 'b1', folio_number: 'F1', status: 'open', balance: 100, currency: 'TRY' },
  { id: 'f2', booking_id: 'b1', folio_number: 'F2', status: 'open', balance: -20, currency: 'TRY' },
  { id: 'closed', booking_id: 'b1', folio_number: 'CLOSED', status: 'closed', balance: 0, currency: 'TRY' },
  { id: 'usd', booking_id: 'b1', folio_number: 'DOLLAR', status: 'open', balance: 0, currency: 'USD' },
];
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { resolve, promise }; };
beforeEach(() => { vi.clearAllMocks(); axios.get.mockResolvedValue({ data: [] }); axios.post.mockResolvedValue({ data: {} }); axios.put.mockResolvedValue({ data: {} }); });
afterEach(cleanup);
const chooseMerge = () => {
  fireEvent.change(screen.getByLabelText('Kaynak hesap'), { target: { value: 'f1' } });
  fireEvent.change(screen.getByLabelText('Hedef hesap'), { target: { value: 'f2' } });
  fireEvent.change(screen.getByLabelText('İşlem açıklaması'), { target: { value: 'Misafir isteği' } });
  fireEvent.click(screen.getByLabelText('Kaynak, hedef ve işlem kapsamını kontrol ettim.'));
};

describe('in-card merge and routing', () => {
  it('requires deliberate source/target and confirmation, excludes closed/other-currency targets, sends exact balances', async () => {
    const onChanged = vi.fn(), onClose = vi.fn();
    render(<FolioCardTools {...{ booking, folios, onChanged, onClose }} />);
    expect(screen.getByRole('button', { name: 'Birleştir', exact: true })).toBeDisabled();
    chooseMerge();
    const target = screen.getByLabelText('Hedef hesap');
    expect([...target.options].map(o => o.value)).toEqual(['', 'f2']);
    fireEvent.click(screen.getByRole('button', { name: 'Birleştir', exact: true }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(axios.post).toHaveBeenCalledWith('/folio-windows/merge', expect.objectContaining({ booking_id: 'b1', source_folio_id: 'f1', target_folio_id: 'f2', expected_source_balance: 100, expected_target_balance: -20, reason: 'Misafir isteği', request_id: expect.any(String) }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
  it('locks double clicks and retries uncertain merge with the same operation ID', async () => {
    const first = deferred(); axios.post.mockReturnValueOnce(first.promise);
    render(<FolioCardTools booking={booking} folios={folios} onClose={vi.fn()} />);
    chooseMerge();
    fireEvent.click(screen.getByRole('button', { name: 'Birleştir', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: 'İşleniyor…' }));
    expect(axios.post).toHaveBeenCalledTimes(1);
    await act(async () => first.resolve(Promise.reject(new Error('Network lost'))));
    fireEvent.click(screen.getByRole('button', { name: 'Birleştir', exact: true }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[1][1].request_id).toBe(axios.post.mock.calls[0][1].request_id);
  });
  it('saves a category/date routing rule without silently applying charges', async () => {
    render(<FolioCardTools booking={booking} folios={folios} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Masrafları yönlendir' }));
    chooseMerge();
    fireEvent.change(screen.getByLabelText('Masraf türü'), { target: { value: 'ROOM' } });
    fireEvent.change(screen.getByLabelText('İlk iş günü'), { target: { value: '2026-11-15' } });
    fireEvent.change(screen.getByLabelText('Son iş günü'), { target: { value: '2026-11-17' } });
    fireEvent.click(screen.getByLabelText('Kaynak, hedef ve işlem kapsamını kontrol ettim.'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kuralı kaydet' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Kuralı kaydet' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post).toHaveBeenCalledWith('/folio-routing', { source_folio_id: 'f1', dest_folio_id: 'f2', charge_codes: ['ROOM'], from_date: '2026-11-15', to_date: '2026-11-17', note: 'Misafir isteği' });
  });
  it('preserves custom routing codes and never treats an empty custom selection as all charges', async () => {
    render(<FolioCardTools booking={booking} folios={folios} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Masrafları yönlendir' }));
    chooseMerge();
    fireEvent.change(screen.getByLabelText('Masraf türü'), { target: { value: '__custom' } });
    fireEvent.click(screen.getByLabelText('Kaynak, hedef ve işlem kapsamını kontrol ettim.'));
    expect(screen.getByRole('button', { name: 'Kuralı kaydet' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Masraf kodları'), { target: { value: ' tax, TRANSPORT, TAX, ' } });
    fireEvent.click(screen.getByLabelText('Kaynak, hedef ve işlem kapsamını kontrol ettim.'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kuralı kaydet' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Kuralı kaydet' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/folio-routing', expect.objectContaining({ charge_codes: ['TAX', 'TRANSPORT'] })));
  });
});

describe('legacy folio tools inside reservation card', () => {
  it('loads only selected booking folio and keeps read-only cards non-mutating', async () => {
    axios.get.mockResolvedValue({ data: { folio: folios[0], charges: [], payments: [] } });
    const onClose = vi.fn();
    render(<ReservationFolioDetails booking={booking} folios={folios} initialFolioId="f1" readOnly onClose={onClose} />);
    await screen.findByRole('button', { name: 'İşlem Ekle' });
    expect(axios.get).toHaveBeenCalledWith('/folio/f1');
    expect(screen.getByRole('button', { name: 'İşlem Ekle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Ödeme Ekle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Aktar/ })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();
  });
  it('rejects another booking payload and lets a failed selected folio be retried', async () => {
    axios.get.mockResolvedValueOnce({ data: { folio: { ...folios[0], booking_id: 'other' }, charges: [] } }).mockResolvedValueOnce({ data: { folio: folios[0], charges: [], payments: [] } });
    render(<ReservationFolioDetails booking={booking} folios={[folios[0]]} initialFolioId="f1" onClose={vi.fn()} />);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('bu rezervasyona ait değil')));
    expect(screen.queryByRole('button', { name: 'Ödeme Ekle' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/F1 ·/).closest('button'));
    await screen.findByRole('button', { name: 'Ödeme Ekle' });
    expect(axios.get).toHaveBeenCalledTimes(2);
  });
});

it('occupancy edits preserve all prices/dates and send explicit children ages', async () => {
  const onSaved = vi.fn();
  render(<ReservationOccupancyEditor booking={booking} onSaved={onSaved} />);
  fireEvent.click(screen.getByRole('button', { name: 'Konuk sayısını düzenle' }));
  fireEvent.change(screen.getByLabelText('Yetişkin sayısı'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('Çocuk sayısı'), { target: { value: '2' } });
  expect(screen.getByLabelText('1. çocuk yaşı')).toHaveValue(8);
  expect(screen.getByLabelText('2. çocuk yaşı')).toHaveValue(null);
  fireEvent.change(screen.getByLabelText('2. çocuk yaşı'), { target: { value: '4' } });
  fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(axios.put).toHaveBeenCalledWith('/pms/bookings/b1', { adults: 3, children: 2, children_ages: [8, 4] });
});


it('opens folio tools above the guest card and returns to the mounted card after closing a nested action', async () => {
  axios.get.mockResolvedValue({ data: { folio: folios[0], charges: [], payments: [] } });
  const onRefresh = vi.fn();
  render(<div data-testid="guest-card" className="z-[60]">
    <FoliosTab booking={booking} folios={[folios[0]]} charges={[]} payments={[]} extra_charges={[]}
      summary={{ total_amount: 100, total_charges: 100, balance: 100 }} onRefresh={onRefresh} />
  </div>);
  fireEvent.click(screen.getByRole('button', { name: 'Aktarım, iade ve hesap ayrıntıları' }));
  const folioDialog = await screen.findByRole('dialog');
  await screen.findByRole('button', { name: 'Ödeme Ekle' });
  expect(folioDialog).toHaveClass('z-[80]');
  expect([...document.querySelectorAll('div[data-state="open"]')].some(el => el.classList.contains('z-[70]'))).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Ödeme Ekle' }));
  const paymentDialog = screen.getByRole('dialog', { name: 'Ödeme Ekle' });
  expect(paymentDialog).toHaveClass('z-[100]');
  expect([...document.querySelectorAll('div[data-state="open"]')].some(el => el.classList.contains('z-[90]'))).toBe(true);
  fireEvent.click(within(paymentDialog).getByRole('button', { name: 'Kapat' }));
  expect(screen.queryByRole('dialog', { name: 'Ödeme Ekle' })).not.toBeInTheDocument();
  expect(screen.getByTestId('guest-card')).toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Kapat' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByTestId('guest-card')).toBeInTheDocument();
  expect(onRefresh).not.toHaveBeenCalled();
  expect(axios.post).not.toHaveBeenCalled();
});

it.each(['Proforma Fatura', 'İşlem Aktar'])('ignores a late %s response after switching folios', async action => {
  const pending = deferred();
  if (action === 'Proforma Fatura') axios.post.mockReturnValueOnce(pending.promise);
  else axios.get.mockReturnValueOnce(pending.promise);
  const props = { open: true, onClose: vi.fn(), folios, folioCharges: [], folioPayments: [], bookings: [booking] };
  const { rerender } = render(<FolioViewDialog {...props} selectedFolio={folios[0]} />);
  fireEvent.click(screen.getByRole('button', { name: action }));
  rerender(<FolioViewDialog {...props} selectedFolio={folios[1]} />);
  await act(async () => pending.resolve({ data: action === 'Proforma Fatura' ? { folio: folios[0] } : { folios: [folios[0]] } }));
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  expect(screen.queryByRole('dialog', { name: action === 'İşlem Aktar' ? 'İşlem Aktar' : 'Proforma Fatura' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Proforma Fatura' })).toBeEnabled();
});
