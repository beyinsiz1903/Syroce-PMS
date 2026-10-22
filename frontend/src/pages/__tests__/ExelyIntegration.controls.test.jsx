import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { api, confirm, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  confirm: vi.fn(), toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('axios', () => ({ default: api }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: confirm }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/components/TestBookingVerification', () => ({ default: () => null }));

import ExelyIntegration from '@/pages/ExelyIntegration';

let connection;
let safety;
let workerRunning;

beforeEach(() => {
  vi.clearAllMocks();
  connection = { auto_sync_reservations: true, ari_write_enabled: true, sync_interval_minutes: 15, hotel_code: 'synthetic-property', room_types: [], rate_plans: [] };
  safety = { ari_write_allowed: true, reservation_sync_allowed: true };
  workerRunning = true;
  confirm.mockResolvedValue(true);
  api.get.mockImplementation(async path => {
    if (path.endsWith('/connection')) return { data: { connected: true, connection: { ...connection } } };
    if (path.endsWith('/sync/status')) return { data: { scheduler_running: workerRunning, production_safety: safety, reservation_sync_enabled: connection.auto_sync_reservations, sync_interval_seconds: connection.sync_interval_minutes * 60 } };
    if (path.includes('/auto-map/status/')) return { data: {} };
    return { data: { mappings: [], logs: [], reservations: [] } };
  });
  api.post.mockImplementation(async (path, body) => {
    if (path.endsWith('/scheduler/stop')) connection.auto_sync_reservations = false;
    if (path.endsWith('/scheduler/start')) connection.auto_sync_reservations = true;
    if (path.endsWith('/ari-write')) connection.ari_write_enabled = body.enabled;
    return { data: { message: 'Ayar kaydedildi' } };
  });
  api.patch.mockImplementation(async (_path, body) => {
    connection.sync_interval_minutes = body.sync_interval_minutes;
    return { data: { message: 'Aralık kaydedildi' } };
  });
});

async function mount() {
  render(<ExelyIntegration user={{ role: 'admin' }} tenant={{ id: 'tenant-a' }} />);
  return screen.findByTestId('exely-reservation-sync-state');
}

describe('Exely tenant-level controls', () => {
  it('can stop this tenant even while both global safety gates are closed', async () => {
    safety = { ari_write_allowed: false, reservation_sync_allowed: false };
    const state = await mount();
    expect(state).toHaveTextContent('Güvenlik kilitli');
    expect(screen.getByTestId('exely-reservation-sync-toggle')).toBeEnabled();
    expect(screen.getByTestId('exely-ari-write-toggle')).toBeEnabled();
    fireEvent.click(screen.getByTestId('exely-reservation-sync-toggle'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/channel-manager/exely/sync/scheduler/stop', {}, {}));
    await waitFor(() => expect(state).toHaveTextContent('Kapalı'));
    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('diğer otellerin çekimi') }));
  });

  it('can independently stop ARI under the global kill switch', async () => {
    safety.ari_write_allowed = false;
    await mount();
    fireEvent.click(screen.getByTestId('exely-ari-write-toggle'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/channel-manager/exely/ari-write', {
      enabled: false, confirmation: 'DISABLE_EXELY_ARI_WRITE',
    }, {}));
  });

  it('never enables either path while its global safety gate is closed', async () => {
    connection.auto_sync_reservations = false;
    connection.ari_write_enabled = false;
    safety = { ari_write_allowed: false, reservation_sync_allowed: false };
    await mount();
    expect(screen.getByTestId('exely-reservation-sync-toggle')).toBeDisabled();
    expect(screen.getByTestId('exely-ari-write-toggle')).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('does not report tenant sync as active just because the shared worker is running', async () => {
    connection.auto_sync_reservations = false;
    const state = await mount();
    expect(state).toHaveTextContent('Kapalı');
    expect(screen.getByText('Bu sunucudaki çalışan: aktif')).toBeInTheDocument();
  });

  it('requires operator confirmation before turning tenant sync on', async () => {
    connection.auto_sync_reservations = false;
    confirm.mockResolvedValue(false);
    await mount();
    fireEvent.click(screen.getByTestId('exely-reservation-sync-toggle'));
    await waitFor(() => expect(confirm).toHaveBeenCalled());
    expect(api.post).not.toHaveBeenCalled();
  });

  it('saves the polling interval without disconnecting or enabling synchronization', async () => {
    connection.auto_sync_reservations = false;
    await mount();
    fireEvent.change(screen.getByLabelText('Çekim aralığı (dakika)'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Çekim Aralığını Kaydet' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/channel-manager/exely/sync/settings', { sync_interval_minutes: 7 }, {}));
    expect(api.post).not.toHaveBeenCalled();
  });

  it('rejects an invalid interval before a request is made', async () => {
    await mount();
    fireEvent.change(screen.getByLabelText('Çekim aralığı (dakika)'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Çekim Aralığını Kaydet' }));
    expect(toast.error).toHaveBeenCalledWith('Çekim aralığı 3–60 dakika arasında tam sayı olmalıdır');
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('shows status read failure instead of a fabricated zero/disabled state', async () => {
    const get = api.get.getMockImplementation();
    api.get.mockImplementation(path => path.endsWith('/sync/status') ? Promise.reject(new Error('offline')) : get(path));
    render(<ExelyIntegration user={{ role: 'admin' }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Senkronizasyon durumu okunamadı');
    expect(screen.queryByTestId('exely-reservation-sync-state')).not.toBeInTheDocument();
    expect(screen.getByTestId('exely-reservation-sync-toggle')).toBeEnabled();
    expect(screen.getByTestId('exely-ari-write-toggle')).toBeEnabled();
  });
});
