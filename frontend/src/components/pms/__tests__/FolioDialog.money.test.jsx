import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import FolioDialog from '../FolioDialog';

const { post, error } = vi.hoisted(() => ({ post: vi.fn(), error: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
vi.mock('sonner', () => ({ toast: { error, success: vi.fn() } }));
const folio = { charges: [], payments: [], total_charges: 0, total_paid: 0, balance: 100, unposted_room_amount: 100, currency: 'USD' };
beforeEach(() => { post.mockReset().mockResolvedValue({ data: {} }); error.mockReset(); });

it('explains unposted room amount and never substitutes a missing foreign rate', () => {
  render(<FolioDialog open folio={folio} bookingId="b" onClose={vi.fn()} />);
  expect(screen.getByText('Henüz tahakkuk etmemiş konaklama:')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Folyo tahsilat tutarı'), { target: { value: '10' } });
  fireEvent.submit(screen.getByLabelText('Folyo tahsilat tutarı').closest('form'));
  expect(post).not.toHaveBeenCalled();
  expect(error).toHaveBeenCalledWith(expect.stringContaining('TL kuru gerekli'));
});

it('sends the folio currency and explicit transaction-time rate exactly once', async () => {
  render(<FolioDialog open folio={folio} bookingId="b" onClose={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Folyo tahsilat tutarı'), { target: { value: '10' } });
  fireEvent.change(screen.getByLabelText('Tahsilat TL kuru'), { target: { value: '40' } });
  const form = screen.getByLabelText('Folyo tahsilat tutarı').closest('form');
  fireEvent.submit(form); fireEvent.submit(form);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenCalledWith('/frontdesk/folio/b/payment', expect.objectContaining({ amount: 10, currency: 'USD', received_to_try_rate: 40 }), expect.any(Object));
});
