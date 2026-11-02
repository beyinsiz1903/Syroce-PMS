import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('axios', () => ({ default: api }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
import IntegrationHub from '@/pages/IntegrationHub';

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async path => ({ data: path.endsWith('/dashboard') ? {
    connectors: [{ connector_id: 'old-exely', provider: 'exely', status: 'paused', health: 'red' }],
  } : path.endsWith('/exely/connection') ? { connected: true, connection: { hotel_code: '501694', ari_write_enabled: true, auto_sync_reservations: false } }
    : path.endsWith('/push-providers') ? { providers: [{ slug: 'exely', mode: 'live', write_enabled: true }] } : {} }));
});

it.each(['Müsaitliği yönet', 'Fiyatları yönet'])('opens the scoped editor for %s, without an unscoped legacy sync', async label => {
  render(<MemoryRouter><Routes>
    <Route path="/" element={<IntegrationHub />} />
    <Route path="/unified-rate-manager" element={<p>Scoped rate editor</p>} />
  </Routes></MemoryRouter>);
  await screen.findByText('ARI gönderimi açık');
  fireEvent.click(screen.getByText('v2 bağlantı geçmişi ve tanı kayıtları'));
  fireEvent.click(await screen.findByRole('button', { name: label }));
  expect(await screen.findByText('Scoped rate editor')).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});

it('shows native state instead of treating a paused v2 record as live Exely health', async () => {
  render(<MemoryRouter><IntegrationHub /></MemoryRouter>);
  expect(await screen.findByText('ARI gönderimi açık')).toBeInTheDocument();
  expect(screen.getByTestId('native-exely-status')).toHaveTextContent('Otomatik rezervasyon çekimi: Kapalı');
  expect(screen.getByTestId('legacy-integration-diagnostics')).not.toHaveAttribute('open');
  expect(api.post).not.toHaveBeenCalled();
});

it('does not let an older successful status overwrite a newer disconnected status', async () => {
  const normalGet = api.get.getMockImplementation();
  let releaseOld;
  let connectionReads = 0;
  api.get.mockImplementation(path => {
    if (path.endsWith('/exely/connection')) {
      if (++connectionReads === 1) return new Promise(resolve => { releaseOld = resolve; });
      return Promise.resolve({ data: { connected: false, connection: {} } });
    }
    return normalGet(path);
  });
  render(<MemoryRouter><IntegrationHub /></MemoryRouter>);
  await waitFor(() => expect(releaseOld).toBeTypeOf('function'));
  fireEvent(window, new Event('focus'));
  expect(await screen.findByText('Bağlantı kapalı')).toBeInTheDocument();
  await act(async () => releaseOld({ data: { connected: true, connection: { ari_write_enabled: true } } }));
  expect(screen.queryByText('ARI gönderimi açık')).not.toBeInTheDocument();
  expect(screen.getByText('Bağlantı kapalı')).toBeInTheDocument();
});
