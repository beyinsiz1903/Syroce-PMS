import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { get, post, toastError, toastSuccess, toastFn } = vi.hoisted(() => {
  const toastError = vi.fn();
  const toastSuccess = vi.fn();
  return {
    get: vi.fn(),
    post: vi.fn(),
    toastError,
    toastSuccess,
    toastFn: Object.assign(vi.fn(), { error: toastError, success: toastSuccess }),
  };
});

vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast: toastFn }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

import GroupBookings from '@/pages/GroupBookings';

const group = {
  id: 'group-test',
  group_name: 'Test Grubu',
  total_rooms: 2,
  total_amount: 1000,
  total_paid: 0,
  bookings: [
    { id: 'booking-one', guest_name: 'Test One', room_number: '101', status: 'confirmed' },
    { id: 'booking-two', guest_name: 'Test Two', room_number: '102', status: 'confirmed' },
  ],
};

describe('GroupBookings bulk lifecycle actions', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    toastFn.mockReset();
    get.mockResolvedValue({ data: { groups: [group] } });
  });

  afterEach(() => cleanup());

  it('does not mutate before explicit bulk check-in confirmation', async () => {
    render(<GroupBookings />);

    fireEvent.click(await screen.findByTestId('group-checkin-group-test'));

    expect(post).not.toHaveBeenCalled();
    expect(screen.getByTestId('bulk-action-confirmation')).toBeInTheDocument();
    expect(screen.getByText('Toplu Giriş Onayı')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Vazgeç' }));
    expect(post).not.toHaveBeenCalled();
  });

  it('sends exactly one request after explicit bulk checkout confirmation', async () => {
    post.mockResolvedValue({ data: { checked_out_count: 2, errors: [] } });
    render(<GroupBookings />);

    fireEvent.click(await screen.findByTestId('group-checkout-group-test'));
    expect(post).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Toplu Çıkışı Onayla' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith('/pms/group-bookings/group-test/check-out-all');
  });

  it('redacts booking identifiers and raw backend status from bulk errors', async () => {
    post.mockResolvedValue({
      data: {
        checked_in_count: 0,
        errors: [{
          booking_id: 'private-booking-identifier',
          error: 'Booking private-booking-identifier has current status checked_out',
        }],
      },
    });
    render(<GroupBookings />);

    fireEvent.click(await screen.findByTestId('group-checkin-group-test'));
    fireEvent.click(screen.getByRole('button', { name: 'Toplu Girişi Onayla' }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    const [, options] = toastError.mock.calls[0];
    expect(options.description).toContain('Rezervasyon durumu işlem için uygun değil');
    expect(options.description).not.toContain('private-booking-identifier');
    expect(options.description).not.toContain('checked_out');
  });
});
