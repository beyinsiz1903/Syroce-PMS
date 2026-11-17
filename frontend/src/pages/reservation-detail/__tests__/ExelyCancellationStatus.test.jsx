import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn() }));

import axios from 'axios';
import { confirmDialog } from '@/lib/dialogs';
import ExelyCancellationStatus from '../ExelyCancellationStatus';

const booking = { id: 'synthetic-cancel', status: 'cancelled', source: { provider: 'exely' }, cancellation_reason: 'Guest request' };
const ready = { state: 'NOT_REQUESTED', can_send: true };

describe('Exely cancellation delivery', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    axios.get.mockResolvedValue({ data: ready });
    confirmDialog.mockResolvedValue(true);
    axios.post.mockResolvedValue({ data: { state: 'PENDING', can_send: false } });
  });

  it.each(['confirmed', 'checked_in'])('does not offer cancellation for an active %s booking', status => {
    render(<ExelyCancellationStatus booking={{ ...booking, status }} />);
    expect(screen.queryByTestId('exely-cancellation-status')).not.toBeInTheDocument();
    expect(axios.get).not.toHaveBeenCalled();
  });

  it('does not offer provider actions for a direct booking', () => {
    render(<ExelyCancellationStatus booking={{ ...booking, source: {} }} />);
    expect(axios.get).not.toHaveBeenCalled();
  });

  it('keeps queued delivery distinct from provider confirmation', async () => {
    axios.get.mockResolvedValue({ data: { state: 'PENDING', can_send: false } });
    render(<ExelyCancellationStatus booking={booking} />);
    expect(await screen.findByText(/Exely’ye gönderim bekleniyor/)).toBeInTheDocument();
    expect(screen.queryByText('Exely iptali onayladı.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'İptali Exely’ye gönder' })).not.toBeInTheDocument();
  });

  it('blocks partial group cancellation with an explanation', async () => {
    axios.get.mockResolvedValue({ data: { state: 'BLOCKED', code: 'EXELY_WHOLE_BOOKING_REQUIRED', can_send: false } });
    render(<ExelyCancellationStatus booking={booking} />);
    expect(await screen.findByText(/Diğer odalar aktif/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'İptali Exely’ye gönder' })).not.toBeInTheDocument();
  });

  it('does not retry an uncertain provider write', async () => {
    axios.get.mockResolvedValue({ data: { state: 'UNKNOWN', can_send: false } });
    render(<ExelyCancellationStatus booking={booking} />);
    expect(await screen.findByText(/Tekrar göndermeden önce/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'İptali Exely’ye gönder' })).not.toBeInTheDocument();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('queues one explicit whole-booking request with the recorded reason', async () => {
    render(<ExelyCancellationStatus booking={booking} />);
    fireEvent.click(await screen.findByRole('button', { name: 'İptali Exely’ye gönder' }));
    await screen.findByText(/Exely’ye gönderim bekleniyor/);
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('/pms-core/bookings/synthetic-cancel/exely-cancellation', { reason: 'Guest request' });
    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('tamamı') }));
  });

  it('does not submit after the operator declines', async () => {
    confirmDialog.mockResolvedValue(false);
    render(<ExelyCancellationStatus booking={booking} />);
    fireEvent.click(await screen.findByRole('button', { name: 'İptali Exely’ye gönder' }));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('reconciles a lost response by reading state without resending', async () => {
    axios.post.mockRejectedValue(new Error('response lost'));
    render(<ExelyCancellationStatus booking={booking} />);
    const send = await screen.findByRole('button', { name: 'İptali Exely’ye gönder' });
    axios.get.mockResolvedValue({ data: { state: 'PENDING', can_send: false } });
    fireEvent.click(send);
    expect(await screen.findByRole('alert')).toHaveTextContent('yeniden kontrol edildi');
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'İptali Exely’ye gönder' })).not.toBeInTheDocument();
  });

  it('clears a previous booking status while the new booking loads', async () => {
    axios.get.mockResolvedValueOnce({ data: { state: 'CONFIRMED', can_send: false } });
    const { rerender } = render(<ExelyCancellationStatus booking={booking} />);
    await screen.findByText('Exely iptali onayladı.');
    axios.get.mockReturnValueOnce(new Promise(() => {}));
    rerender(<ExelyCancellationStatus booking={{ ...booking, id: 'another-booking' }} />);
    expect(screen.queryByText('Exely iptali onayladı.')).not.toBeInTheDocument();
    expect(screen.getByText(/kontrol ediliyor/)).toBeInTheDocument();
  });
});
