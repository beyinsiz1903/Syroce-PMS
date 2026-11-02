import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import BookingDialog from '@/components/pms/BookingDialog';
import tr from '@/locales/tr.json';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => key.split('.').reduce((o, k) => o?.[k], tr) || fallback || key }) }));
vi.mock('axios', () => ({ default: { get: vi.fn() } }));

const props = {
  open: true, onClose: vi.fn(), guests: [], rooms: [{ id: 'r1', room_number: '101', status: 'occupied' }], companies: [], ratePlans: [], packages: [],
  newBooking: { check_in: '2026-10-09', check_out: '2026-10-11', currency: 'TRY', children: 0 },
  setNewBooking: vi.fn(), multiRoomBooking: [{ id: 'line', adults: 2, children: 0, room_id: 'r1', base_rate: 100, total_amount: 200 }],
  isLite: true, handleCreateBooking: vi.fn(), addRoomToMultiBooking: vi.fn(), setOpenDialog: vi.fn(),
};
beforeEach(() => { axios.get.mockReset(); axios.get.mockResolvedValue({ data: [{ id: 'r1', room_number: '101', status: 'occupied', available: true }] }); });

describe('booking experience', () => {
  it('puts dates before guest selection and localizes room labels', () => {
    render(<BookingDialog {...props} />);
    const arrival = screen.getByLabelText('Giriş tarihi *');
    const departure = screen.getByLabelText('Çıkış tarihi *');
    expect(departure).toHaveAttribute('min', '2026-10-09');
    expect(arrival.compareDocumentPosition(screen.getByTestId('booking-dialog-guest-search')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText('Room *')).not.toBeInTheDocument();
    expect(screen.getByText('Oda *')).toBeInTheDocument();
  });
  it('preserves the submit contract while suppressing duplicate pending requests', async () => {
    let finish;
    const submit = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    render(<BookingDialog {...props} handleCreateBooking={submit} />);
    const button = screen.getByRole('button', { name: 'Rezervasyonu oluştur' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.submit(button.closest('form'));
    fireEvent.submit(button.closest('form'));
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit.mock.calls[0][1]).toBe('');
    expect(button).toBeDisabled();
    await act(async () => finish());
    expect(button).toBeEnabled();
  });
});
