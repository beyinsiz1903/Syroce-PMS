import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet, axiosPatch, axiosPost } = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  axiosPatch: vi.fn(),
  axiosPost: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    get: axiosGet,
    patch: axiosPatch,
    post: axiosPost,
  },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key.split('.').at(-1),
  }),
}));

vi.mock('@/lib/kbsExtensionBridge', () => ({
  pingExtension: vi.fn().mockResolvedValue({
    present: false,
    state: 'absent',
    states: {},
    version: '',
    installId: '',
  }),
  sendViaExtension: vi.fn(),
  buildKbsBody: vi.fn(),
}));

import KBSNotification from '../KBSNotification';

describe('KBSNotification pending guest identity editing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axiosGet.mockResolvedValue({
      data: {
        jobs: [],
        stats: { pending: 0, in_progress: 0, done: 0, failed: 0, dead: 0 },
      },
    });
    axiosPatch.mockResolvedValue({ data: { status: 'updated' } });
    axiosPost.mockResolvedValue({ data: { created: true } });
  });

  it('opens the identity form from the pending-row warning and makes the guest sendable after save', async () => {
    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110',
          guest_id: 'guest-110',
          status: 'checked_in',
          guest_name: 'Abdulhakim Tavlasoğlu',
          room_number: '110',
          nationality: 'TC',
          id_number: '',
          birth_date: '',
        }]}
      />,
    );

    fireEvent.click(screen.getByRole('button', {
      name: 'idMissing: Abdulhakim Tavlasoğlu',
    }));

    expect(screen.getByText('updateTitle')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('idLabel'), {
      target: { value: ' 12345678901 ' },
    });
    fireEvent.change(screen.getByLabelText('birthDateLabel'), {
      target: { value: '1990-05-12' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() => {
      expect(axiosPatch).toHaveBeenCalledWith(
        '/pms/guests/guest-110/preferences',
        { id_number: '12345678901', birth_date: '1990-05-12' },
      );
    });

    await waitFor(() => {
      expect(screen.queryByRole('button', {
        name: 'idMissing: Abdulhakim Tavlasoğlu',
      })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'send' })).toBeEnabled();
  });

  it('queues the booking without submitting or navigating the surrounding page', async () => {
    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110',
          guest_id: 'guest-110',
          status: 'checked_in',
          guest_name: 'Abdulhakim Tavlasoğlu',
          room_number: '110',
          nationality: 'TC',
          id_number: '12345678901',
          birth_date: '1990-05-12',
        }]}
      />,
    );

    const queueButton = screen.getByRole('button', { name: 'addToQueue' });
    expect(queueButton).toHaveAttribute('type', 'button');
    fireEvent.click(queueButton);

    await waitFor(() => {
      expect(axiosPost).toHaveBeenCalledWith('/kbs/queue', {
        booking_id: 'booking-110',
        action: 'checkin',
      });
    });
  });

  it('rehydrates saved identity fields from the linked guest after the page remounts', () => {
    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110',
          guest_id: 'guest-110',
          status: 'checked_in',
          guest_name: 'Abdulhakim Tavlasoğlu',
          room_number: '110',
          nationality: 'TC',
        }]}
        guests={[{
          id: 'guest-110',
          id_number: '12345678901',
          birth_date: '1990-05-12',
        }]}
      />,
    );

    expect(screen.queryByRole('button', {
      name: 'idMissing: Abdulhakim Tavlasoğlu',
    })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'addToQueue' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'send' })).toBeEnabled();
  });
});
