import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
vi.mock('@/lib/currency', () => ({ formatCurrency: (amount, currency) => `${amount} ${currency}` }));
import RevenueBookingQuote from '@/components/pms/RevenueBookingQuote';

const quote = () => ({ currency: 'USD', total_amount: 190, quote_hash: 'a'.repeat(64), min_stay: 2,
  daily_rates: [{ date: '2026-12-01', amount: 90 }, { date: '2026-12-02', amount: 100 }] });
const props = () => ({ roomId: 'r1', arrival: '2026-12-01', departure: '2026-12-03', currency: 'USD', onApply: vi.fn() });
beforeEach(() => { post.mockReset(); });
afterEach(cleanup);

it('quotes the explicit currency and requires a separate operator confirmation to apply', async () => {
  const p = props(); post.mockResolvedValue({ data: quote() });
  render(<RevenueBookingQuote {...p} />);
  fireEvent.click(screen.getByRole('button', { name: 'Planı USD olarak hesapla' }));
  await screen.findByText('2 gece · 190 USD · Minimum 2 gece');
  expect(post.mock.calls[0][1]).toEqual({ room_id: 'r1', check_in: p.arrival, check_out: p.departure, currency: 'USD', confirm_currency: true });
  expect(p.onApply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Onayla ve rezervasyona uygula' }));
  expect(p.onApply).toHaveBeenCalledWith(quote());
});

it('does not apply a late quote to another room/date/currency or after closing', async () => {
  let resolve; post.mockReturnValue(new Promise(done => { resolve = done; }));
  const p = props(); const view = render(<RevenueBookingQuote {...p} />);
  fireEvent.click(screen.getByRole('button', { name: 'Planı USD olarak hesapla' }));
  view.rerender(<RevenueBookingQuote {...p} roomId="r2" currency="EUR" />);
  await act(async () => resolve({ data: quote() }));
  expect(screen.queryByRole('button', { name: 'Onayla ve rezervasyona uygula' })).not.toBeInTheDocument();
  expect(p.onApply).not.toHaveBeenCalled();
});

it('shows a rejected minimum stay without success and can return to manual pricing', async () => {
  post.mockRejectedValue({ response: { data: { detail: 'En az 3 gece gereklidir' } } });
  const p = props(); render(<RevenueBookingQuote {...p} applied />);
  fireEvent.click(screen.getByRole('button', { name: 'Planı USD olarak hesapla' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('En az 3 gece');
  expect(p.onApply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Manuel fiyata dön' }));
  expect(p.onApply).toHaveBeenCalledWith(null);
});
