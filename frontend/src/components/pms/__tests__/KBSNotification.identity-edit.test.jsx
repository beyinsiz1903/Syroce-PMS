import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  axiosGet, axiosPatch, axiosPost, toastError, toastSuccess, toastInfo,
  pingExtension, sendViaExtension, buildKbsBody,
} = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  axiosPatch: vi.fn(),
  axiosPost: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
  pingExtension: vi.fn(),
  sendViaExtension: vi.fn(),
  buildKbsBody: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    get: axiosGet,
    patch: axiosPatch,
    post: axiosPost,
  },
}));

vi.mock('sonner', () => ({
  toast: { success: toastSuccess, error: toastError, info: toastInfo },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key.split('.').at(-1),
  }),
}));

vi.mock('@/lib/kbsExtensionBridge', () => ({
  pingExtension,
  sendViaExtension,
  buildKbsBody,
}));

import KBSNotification from '../KBSNotification';

describe('KBSNotification pending guest identity editing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.removeItem('kbs_ext_authority');
    localStorage.removeItem('kbs_ext_autosend');
    axiosGet.mockResolvedValue({
      data: {
        jobs: [],
        stats: { pending: 0, in_progress: 0, done: 0, failed: 0, dead: 0 },
      },
    });
    axiosPatch.mockResolvedValue({ data: { status: 'updated' } });
    axiosPost.mockResolvedValue({ data: { created: true } });
    pingExtension.mockResolvedValue({
      present: false,
      state: 'absent',
      states: {},
      version: '',
      installId: '',
    });
    buildKbsBody.mockReturnValue({ action: 'checkin' });
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

  it('renders a structured enqueue validation error as text without crashing the page', async () => {
    axiosPost.mockRejectedValueOnce({
      response: {
        data: {
          detail: {
            error: 'kbs_payload_incomplete',
            missing_fields: ['check_in'],
            message: 'KBS bildirimi için zorunlu alanlar eksik: check_in',
          },
        },
      },
    });

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
          birth_date: '',
        }]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'addToQueue' }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        'KBS bildirimi için zorunlu alanlar eksik: check_in',
      );
    });
    expect(screen.getByRole('button', { name: 'addToQueue' })).toBeInTheDocument();
  });

  it('does not require a birth date for a Turkish guest with a valid identity number', () => {
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
          birth_date: '',
        }]}
      />,
    );

    expect(screen.getByRole('button', { name: 'send' })).toBeEnabled();
    expect(screen.getByRole('tab', { name: 'missingTab (0)' })).toBeInTheDocument();
  });

  it('never calls the retired fake endpoint and does not show success when no live extension is present', async () => {
    axiosPost.mockResolvedValueOnce({
      data: {
        created: true,
        job: { id: 'job-110', booking_id: 'booking-110', action: 'checkin', payload: {} },
      },
    });

    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110',
          guest_id: 'guest-110',
          status: 'checked_in',
          guest_name: 'Test Guest',
          room_number: '110',
          nationality: 'TC',
          id_number: '12345678901',
        }]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => {
      expect(axiosPost).toHaveBeenCalledWith('/kbs/queue', {
        booking_id: 'booking-110',
        action: 'checkin',
      });
    });
    expect(axiosPost).not.toHaveBeenCalledWith('/kbs/send', expect.anything());
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastInfo).toHaveBeenCalledWith(expect.stringContaining('henüz kuruma gönderilmedi'));
  });

  it('shows success only after a configured extension is claimed and completed', async () => {
    pingExtension.mockResolvedValue({
      present: true,
      state: 'absent',
      states: { jandarma: 'configured' },
      version: '1.3.0',
      installId: 'install-1',
    });
    localStorage.setItem('kbs_ext_authority', 'jandarma');
    const job = { id: 'job-110', booking_id: 'booking-110', action: 'checkin', payload: {} };
    axiosPost.mockImplementation((url) => {
      if (url === '/kbs/queue') return Promise.resolve({ data: { created: true, job } });
      if (url === '/kbs/queue/job-110/claim') return Promise.resolve({ data: { job } });
      if (url === '/kbs/queue/job-110/complete') return Promise.resolve({ data: { job: { ...job, status: 'done' } } });
      return Promise.resolve({ data: {} });
    });
    sendViaExtension.mockResolvedValue({
      ok: true,
      reference: 'JANDARMA-MusteriKimlikNoGiris-123',
      error: '',
      test: false,
    });

    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110', guest_id: 'guest-110', status: 'checked_in',
          guest_name: 'Test Guest', room_number: '110', nationality: 'TC',
          id_number: '12345678901',
        }]}
      />,
    );

    await waitFor(() => expect(pingExtension).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => {
      expect(axiosPost).toHaveBeenCalledWith(
        '/kbs/queue/job-110/complete',
        expect.objectContaining({
          worker_id: 'ext:install-1',
          kbs_reference: 'JANDARMA-MusteriKimlikNoGiris-123',
        }),
        expect.objectContaining({ headers: expect.any(Object) }),
      );
    });
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('KBS kabulü doğrulandı'));
    expect(screen.getByRole('tab', { name: 'pendingTab (0)' })).toBeInTheDocument();
    const sentTab = screen.getByRole('tab', { name: 'sentTab (1)' });
    fireEvent.click(sentTab);
    expect(screen.getByText('Test Guest')).toBeVisible();
    expect(screen.getByText(/JANDARMA-MusteriKimlikNoGiris-123/)).toBeVisible();
  });

  it('does not complete or report success for an extension test result', async () => {
    pingExtension.mockResolvedValue({
      present: true,
      state: 'configured',
      states: { polis: 'configured' },
      version: '1.3.0',
      installId: 'install-1',
    });
    localStorage.setItem('kbs_ext_authority', 'polis');
    const job = { id: 'job-110', booking_id: 'booking-110', action: 'checkin', payload: {} };
    axiosPost.mockImplementation((url) => {
      if (url === '/kbs/queue') return Promise.resolve({ data: { created: true, job } });
      if (url === '/kbs/queue/job-110/claim') return Promise.resolve({ data: { job } });
      if (url === '/kbs/queue/job-110/fail') return Promise.resolve({ data: { job: { ...job, status: 'dead' } } });
      return Promise.resolve({ data: {} });
    });
    sendViaExtension.mockResolvedValue({
      ok: true,
      reference: 'TEST-FAKE',
      error: '',
      test: true,
    });

    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110', guest_id: 'guest-110', status: 'checked_in',
          guest_name: 'Test Guest', room_number: '110', nationality: 'TC',
          id_number: '12345678901',
        }]}
      />,
    );

    await waitFor(() => expect(pingExtension).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => {
      expect(axiosPost).toHaveBeenCalledWith(
        '/kbs/queue/job-110/fail',
        expect.objectContaining({ retry: false }),
        expect.objectContaining({ headers: expect.any(Object) }),
      );
    });
    expect(axiosPost).not.toHaveBeenCalledWith(
      '/kbs/queue/job-110/complete', expect.anything(), expect.anything(),
    );
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledWith(expect.stringContaining('Test modu'));
  });

  it('shows the official Jandarma error and disables retry for permanent input failures', async () => {
    pingExtension.mockResolvedValue({
      present: true,
      state: 'absent',
      states: { jandarma: 'configured' },
      version: '1.3.1',
      installId: 'install-1',
    });
    localStorage.setItem('kbs_ext_authority', 'jandarma');
    const job = {
      id: 'job-110', booking_id: 'booking-110', action: 'checkin',
      payload: { guest_name: 'Test Guest', room_number: '110' },
    };
    axiosPost.mockImplementation((url) => {
      if (url === '/kbs/queue') return Promise.resolve({ data: { created: true, job } });
      if (url === '/kbs/queue/job-110/claim') return Promise.resolve({ data: { job } });
      if (url === '/kbs/queue/job-110/fail') return Promise.resolve({ data: { job: { ...job, status: 'dead' } } });
      return Promise.resolve({ data: {} });
    });
    sendViaExtension.mockResolvedValue({
      ok: false,
      reference: '',
      error: 'jandarma_GirdiHatasi: Oda Numarası Eksik.&lt;br&gt;',
      test: false,
    });

    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110', guest_id: 'guest-110', status: 'checked_in',
          guest_name: 'Test Guest', room_number: '110', nationality: 'TC',
          id_number: '12345678901',
        }]}
      />,
    );

    await waitFor(() => expect(pingExtension).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => {
      expect(axiosPost).toHaveBeenCalledWith(
        '/kbs/queue/job-110/fail',
        expect.objectContaining({
          retry: false,
          error: 'jandarma_GirdiHatasi: Oda Numarası Eksik.&lt;br&gt;',
        }),
        expect.objectContaining({ headers: expect.any(Object) }),
      );
    });
    expect(toastError).toHaveBeenCalledWith('Jandarma veri hatası: Oda Numarası Eksik.');
  });

  it('shows a completed Jandarma guest only in Sent, never in Queue', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/kbs/guests') {
        return Promise.resolve({
          data: {
            guests: [{
              // Production can return a delivery/report row id separately
              // from the reservation identity. Queue de-duplication must use
              // booking_id, not the report's own id.
              id: 'report-110',
              booking_id: 'booking-110',
              guest_id: 'guest-110',
              status: 'checked_in',
              guest_name: 'Test Guest',
              room_number: '110',
              nationality: 'TR',
              id_number: '12345678901',
              kbs_status: 'sent',
              kbs_sent_at: '2026-08-30T10:00:00Z',
              kbs_reference: 'JANDARMA-MusteriKimlikNoGiris-123',
              kbs_action: 'checkin',
            }],
          },
        });
      }
      return Promise.resolve({
        data: {
          // Eski backend done isiyle birlikte ayni rezervasyonun daha eski
          // basarisiz kopyasini dondurse bile misafir Kuyruk'ta gorunmemeli.
          jobs: [
            {
              id: 'job-jandarma',
              booking_id: 'booking-110',
              action: 'checkin',
              status: 'done',
              attempts: 1,
              max_attempts: 5,
              kbs_reference: 'JANDARMA-MusteriKimlikNoGiris-123',
              payload: { guest_name: 'Test Guest', room_number: '110' },
            },
            {
              id: 'job-jandarma-old-dead',
              booking_id: 'booking-110',
              action: 'checkin',
              status: 'dead',
              attempts: 5,
              max_attempts: 5,
              last_error: 'Eski basarisiz deneme',
              payload: { guest_name: 'Test Guest', room_number: '110' },
            },
          ],
          stats: { pending: 0, in_progress: 0, done: 1, failed: 0, dead: 1 },
        },
      });
    });

    render(<KBSNotification />);

    const sentTab = await screen.findByRole('tab', { name: 'sentTab (1)' });
    const queueTab = screen.getByRole('tab', { name: 'queueTab (0)' });
    fireEvent.click(sentTab);

    expect(await screen.findByText('Test Guest')).toBeInTheDocument();
    expect(screen.getByText(/JANDARMA-MusteriKimlikNoGiris-123/)).toBeInTheDocument();

    fireEvent.click(queueTab);
    const queuePanel = screen.getByText('noQueueJobs').closest('[role="tabpanel"]');
    expect(queuePanel).toBeInTheDocument();
    expect(within(queuePanel).queryByText('Test Guest')).not.toBeInTheDocument();
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

  it('refreshes a stale calendar guest from the canonical KBS guest API', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/kbs/guests') {
        return Promise.resolve({
          data: {
            guests: [{
              id: 'booking-110',
              guest_id: 'guest-110',
              status: 'checked_in',
              guest_name: 'Abdulhakim Tavlasoğlu',
              room_number: '110',
              nationality: 'TR',
              id_number: '12345678901',
              birth_date: '',
            }],
          },
        });
      }
      return Promise.resolve({
        data: {
          jobs: [],
          stats: { pending: 0, in_progress: 0, done: 0, failed: 0, dead: 0 },
        },
      });
    });

    render(
      <KBSNotification
        bookings={[{
          id: 'booking-110',
          guest_id: 'guest-110',
          status: 'checked_in',
          guest_name: 'Abdulhakim Tavlasoğlu',
          room_number: '110',
          nationality: 'TR',
          id_number: '',
        }]}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByRole('button', {
        name: 'idMissing: Abdulhakim Tavlasoğlu',
      })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'send' })).toBeEnabled();
  });
});
