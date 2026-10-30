import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/api/axios', () => ({ default: { get, post } }));
import ScheduledServiceFolioPanel from '../ScheduledServiceFolioPanel';
const source = { id: 'source', activity_id: 'a', status: 'booked', starts_at: '2026-10-30T15:00:00+03:00', ends_at: '2026-10-30T16:00:00+03:00' };
const quote = { gross: '150', currency: 'TRY', tax: null, service_date: '2026-10-30', service_time: '15:00', quote_hash: 'a'.repeat(64) };
beforeEach(() => { vi.clearAllMocks(); get.mockImplementation(url => Promise.resolve({ data: url.includes('folio-quote') ? quote : url.includes('active-by-room') ? { found: true, booking_id: 'booking', guest_name: 'QA Synthetic' } : [
  { folio_id: 'guest', folio_number: 'F-1', status: 'open', currency: 'TRY' }, { folio_id: 'company', folio_number: 'F-2', status: 'open', currency: 'TRY' },
] })); });
afterEach(cleanup);
it('does not guess one of multiple folios or post merely when opening its preview', async () => {
  const changed = vi.fn();
  post.mockResolvedValue({ data: { success: true, charge: { id: 'canonical' } } });
  render(<ScheduledServiceFolioPanel kind="activity" bookings={[source]} names={{ a: 'QA Yoga' }} onChanged={changed} />);
  fireEvent.click(screen.getByText('Tamamla ve folyoya işle'));
  expect(await screen.findByText(/Vergi ayrımı bilinmiyor/)).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Konaklama oda numarası'), { target: { value: '101' } });
  fireEvent.click(screen.getByText('Konaklamayı bul'));
  await screen.findByText('QA Synthetic · Oda 101');
  expect(screen.getByLabelText('Hedef folyo')).toHaveValue('');
  expect(screen.getByText('Hizmeti tamamla ve ücreti işle')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Hedef folyo'), { target: { value: 'company' } });
  fireEvent.click(screen.getByText('Hizmeti tamamla ve ücreti işle'));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(post).toHaveBeenCalledWith('/activities/bookings/source/folio', expect.objectContaining({ reservation_id: 'booking', folio_id: 'company', quote_hash: quote.quote_hash }));
});
it('retains the exact first intent after an uncertain response', async () => {
  post.mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({ data: { success: true, charge: { id: 'same' } } });
  render(<ScheduledServiceFolioPanel kind="activity" bookings={[source]} />);
  fireEvent.click(screen.getByText('Tamamla ve folyoya işle')); await screen.findByText(/Vergi ayrımı bilinmiyor/);
  fireEvent.change(screen.getByLabelText('Konaklama oda numarası'), { target: { value: '101' } }); fireEvent.click(screen.getByText('Konaklamayı bul'));
  await screen.findByText('QA Synthetic · Oda 101'); fireEvent.change(screen.getByLabelText('Hedef folyo'), { target: { value: 'guest' } });
  fireEvent.click(screen.getByText('Hizmeti tamamla ve ücreti işle'));
  await screen.findByText('Aynı aktarımın sonucunu doğrula');
  expect(screen.getByLabelText('Hedef folyo')).toBeDisabled();
  fireEvent.click(screen.getByText('Aynı aktarımın sonucunu doğrula'));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
});
