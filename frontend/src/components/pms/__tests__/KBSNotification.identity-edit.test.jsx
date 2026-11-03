import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, put, post, success, error, info, ping, send, body } = vi.hoisted(() => ({
  get: vi.fn(), put: vi.fn(), post: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn(),
  ping: vi.fn(), send: vi.fn(), body: vi.fn(),
}));
vi.mock('axios', () => ({ default: { get, put, post } }));
vi.mock('sonner', () => ({ toast: { success, error, info } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key.split('.').at(-1) }) }));
vi.mock('@/lib/kbsExtensionBridge', () => ({ pingExtension: ping, sendViaExtension: send, buildKbsBody: body }));
import KBSNotification from '../KBSNotification';

const base = { id: 'job-110', booking_id: 'booking-110', guest_id: 'guest-110',
  guest_name: 'Synthetic Guest', room_number: '110', action: 'checkin',
  delivery_group: 'not_sent', status: 'pending', status_reason: 'awaiting_delivery', missing_fields: [] };
let rows;
let hidden;

describe('KBS two-view operational screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    rows = [{ ...base }];
    hidden = 0;
    ping.mockResolvedValue({ present: false, state: 'absent', states: {}, version: '', installId: '' });
    get.mockImplementation(async (url, config) => {
      if (url === '/kbs/notifications') {
        const group = config?.params?.group;
        return { data: { can_edit: true, items: rows.filter(r => r.delivery_group === group),
          counts: { sent: rows.filter(r => r.delivery_group === 'sent').length, not_sent: rows.filter(r => r.delivery_group === 'not_sent').length },
          hidden_unresolved_count: hidden, has_more: false } };
      }
      if (url === '/kbs/cloud/status') return { data: { managed: false } };
      return { data: { jobs: [] } };
    });
    put.mockImplementation(async () => { rows[0] = { ...rows[0], missing_fields: [], status_reason: 'awaiting_delivery' }; return { data: { ready: true } }; });
    post.mockImplementation(async url => {
      if (url === '/kbs/queue') return { data: { created: true, job: { ...base, payload: {} } } };
      if (url.endsWith('/claim')) return { data: { job: { ...base, payload: {} } } };
      if (url.endsWith('/complete')) {
        rows[0] = { ...base, status: 'done', delivery_group: 'sent', status_reason: 'accepted', completed_at: '2026-11-02T18:20:00Z' };
      }
      return { data: {} };
    });
    body.mockReturnValue({ action: 'checkin' });
  });

  async function show() {
    render(<KBSNotification />);
    await screen.findByText('Synthetic Guest');
  }
  function extension() {
    localStorage.setItem('kbs_ext_authority', 'jandarma');
    ping.mockResolvedValue({ present: true, state: 'absent', states: { jandarma: 'configured' }, version: '1.3.2', installId: 'install-1' });
  }

  it('shows exactly two options, no status counters or destructive queue reset', async () => {
    await show();
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.getByRole('tab', { name: 'Gönderilen (0)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Gönderilmeyen (1)' })).toBeInTheDocument();
    expect(screen.queryByText('Kuyruğu sıfırla')).not.toBeInTheDocument();
    expect(screen.queryByText('qPending')).not.toBeInTheDocument();
  });

  it('completes identity with the scoped encrypted-write endpoint and refreshes readiness', async () => {
    rows[0] = { ...base, status_reason: 'missing_data', missing_fields: ['id_number'] };
    await show();
    fireEvent.click(screen.getByRole('button', { name: 'idMissing: Synthetic Guest' }));
    fireEvent.change(screen.getByLabelText('KBS kimlik numarası'), { target: { value: '12345678901' } });
    fireEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => expect(put).toHaveBeenCalledWith('/kbs/booking/booking-110/guests/guest-110/identity',
      { id_number: '12345678901', id_type: 'tc_kimlik', nationality: 'TR' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'send' })).toBeEnabled());
    expect(screen.queryByDisplayValue('12345678901')).not.toBeInTheDocument();
  });

  it('allows a ready domestic guest without requiring DOB, and never auto-submits the surrounding form', async () => {
    await show();
    const button = screen.getByRole('button', { name: 'send' });
    expect(button).toHaveAttribute('type', 'button');
    fireEvent.click(button);
    await waitFor(() => expect(post).toHaveBeenCalledWith('/kbs/queue', {
      booking_id: 'booking-110', action: 'checkin', guest_id: 'guest-110',
    }));
    expect(post).not.toHaveBeenCalledWith('/kbs/send', expect.anything());
    expect(success).not.toHaveBeenCalled();
    expect(info).toHaveBeenCalledWith(expect.stringContaining('henüz kuruma gönderilmedi'));
  });

  it('renders structured validation errors without crashing or declaring success', async () => {
    post.mockRejectedValueOnce({ response: { data: { detail: { message: 'Eksik check_in' } } } });
    await show();
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
    await waitFor(() => expect(error).toHaveBeenCalledWith('Eksik check_in'));
    expect(success).not.toHaveBeenCalled();
  });

  it('shows accepted only after extension claim and durable complete, formatted in Istanbul time', async () => {
    extension();
    send.mockResolvedValue({ ok: true, reference: 'JANDARMA-local-receipt', test: false });
    await show();
    await waitFor(() => expect(ping).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/kbs/queue/job-110/complete',
      expect.objectContaining({ worker_id: 'ext:install-1', kbs_reference: 'JANDARMA-local-receipt' }), expect.anything()));
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Gönderilen (1)' })).toBeInTheDocument());
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Gönderilen (1)' }), { button: 0, ctrlKey: false });
    expect(await screen.findByText(/21:20:00/)).toBeInTheDocument();
    expect(success).toHaveBeenCalledWith(expect.stringContaining('KBS kabulü doğrulandı'));
  });

  it('holds disconnected transport as uncertain and never blindly retries', async () => {
    extension();
    send.mockRejectedValue(new Error('extension_transport_disconnected'));
    await show();
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/kbs/queue/job-110/fail',
      expect.objectContaining({ retry: false, delivery_uncertain: true, error: 'delivery_unknown_check_authority' }), expect.anything()));
    expect(post.mock.calls.some(([url]) => url.endsWith('/complete'))).toBe(false);
    expect(success).not.toHaveBeenCalled();
  });

  it('does not accept extension test receipts as real delivery', async () => {
    extension();
    send.mockResolvedValue({ ok: true, reference: 'TEST-FAKE', test: true });
    await show();
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/kbs/queue/job-110/fail',
      expect.objectContaining({ retry: false }), expect.anything()));
    expect(post.mock.calls.some(([url]) => url.endsWith('/complete'))).toBe(false);
    expect(success).not.toHaveBeenCalled();
  });

  it.each([
    ['already_registered', /aynı kimlik için tesiste açık kayıt/],
    ['delivery_uncertain', /Teslim sonucu belirsiz/],
    ['awaiting_checkin', /giriş kabulü alınmadan çıkış gönderilemez/],
    ['test_only', /Test sonucu resmî bildirim değildir/],
  ])('keeps %s in Not sent with its real cause and no duplicate send button', async (reason, text) => {
    rows[0] = { ...base, status_reason: reason };
    await show();
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'send' })).not.toBeInTheDocument();
  });

  it('keeps already-registered extension failures permanent and visible, not success', async () => {
    extension();
    send.mockResolvedValue({ ok: false, error: 'jandarma_VTHatasi: Müşteri Tesiste Zaten Kayıtlı.&lt;br&gt;', test: false });
    await show();
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/kbs/queue/job-110/fail',
      expect.objectContaining({ retry: false }), expect.anything()));
    expect(error).toHaveBeenCalledWith(expect.stringContaining('tesiste açık kayıt'));
    expect(success).not.toHaveBeenCalled();
  });

  it('does not resurrect expired rows from old calendar props and shows only an anonymous unresolved count', async () => {
    rows = [];
    hidden = 2;
    render(<KBSNotification bookings={[{ id: 'old', status: 'checked_in', guest_name: 'Expired Calendar Person' }]} />);
    expect(await screen.findByText(/Görünürlük süresi dolmuş 2 bildirim/)).toBeInTheDocument();
    expect(screen.queryByText('Expired Calendar Person')).not.toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(2);
  });

  it('keeps list errors explicit instead of reporting an empty successful state', async () => {
    get.mockRejectedValue(new Error('offline'));
    render(<KBSNotification />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Bildirim listesi yenilenemedi');
    expect(screen.queryByText('Bu görünümde gönderilmeyen bildirim yok.')).not.toBeInTheDocument();
  });
});
