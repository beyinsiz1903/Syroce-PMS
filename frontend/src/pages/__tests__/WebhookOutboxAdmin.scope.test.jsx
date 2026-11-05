import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import { confirmDialog } from '@/lib/dialogs';
import WebhookOutboxAdmin, { outboxScopeParams } from '../WebhookOutboxAdmin';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/components/ui/page-header', () => ({ PageHeader: ({ title }) => <h1>{title}</h1> }));

const row = id => ({ id, tenant_id: 'hotel', provider: null, status: 'failed',
  event_type: 'booking.created.v1', last_error: 'exely_room_mapping_missing' });
const listCalls = () => axios.get.mock.calls.filter(([url]) => url === '/outbox/events');
const scope = { tenant_id: 'hotel', limit: 50, offset: 0, status: 'failed' };

beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockImplementation(async url => ({ data: url === '/outbox/events'
    ? { events: [row('event')], total: 1 }
    : url.endsWith('/readiness') ? { can_requeue: true, issues: [] } : {} }));
  axios.post.mockResolvedValue({ data: { success: true, requeued_count: 1 } });
});

it('bounds initial inspection to the current property and includes provider-null fan-out events', async () => {
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  await screen.findByText('event');
  expect(listCalls().at(-1)[1].params).toEqual(scope);
  expect(screen.getByText(/Durum kartları platform genelidir/)).toBeInTheDocument();
  expect(outboxScopeParams({ tenantId: ' hotel ', provider: 'all' })).toEqual({ tenant_id: 'hotel' });
  expect(axios.post).not.toHaveBeenCalled();
});

it('keeps legacy pending rows visible while distinguishing them from the OTA queue', async () => {
  const implementation = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url, ...args) => url === '/outbox/status'
    ? { data: { pending: 3, ota_pending: 1, legacy_pending: 2 } }
    : implementation(url, ...args));
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  expect(await screen.findByText('OTA: 1 · eski biçim: 2')).toBeInTheDocument();
  expect(screen.getByText(/Platform genelinde 2 eski biçimli bekleyen olay var/)).toHaveTextContent('gönderilmiş veya çözülmüş sayılmazlar');
  await screen.findByText('event');
  expect(axios.post).not.toHaveBeenCalled();
});

it('applies exact property/provider filters only after an explicit read-only apply', async () => {
  render(<WebhookOutboxAdmin />);
  await screen.findByText('event');
  const initial = listCalls().length;
  fireEvent.change(screen.getByLabelText('Tesis kimliği (tam eşleşme)'), { target: { value: ' hotel ' } });
  fireEvent.change(screen.getByLabelText('Outbox sağlayıcı'), { target: { value: 'exely' } });
  expect(listCalls()).toHaveLength(initial);
  fireEvent.click(screen.getByRole('button', { name: 'Kapsamı uygula' }));
  await waitFor(() => expect(listCalls().at(-1)[1].params).toEqual({ ...scope, provider: 'exely' }));
  await screen.findByText('event');
  expect(axios.post).not.toHaveBeenCalled();
});

it('pages through the complete filtered total without dropping the property/provider scope', async () => {
  axios.get.mockImplementation(async (url, config) => ({ data: url === '/outbox/events'
    ? { total: 51, events: [row(config.params.offset ? 'last-page' : 'first-page')] } : {} }));
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  await screen.findByText('first-page');
  fireEvent.click(screen.getByRole('button', { name: 'Sonraki sayfa' }));
  await screen.findByText('last-page');
  expect(listCalls().at(-1)[1].params).toEqual({ ...scope, offset: 50 });
  expect(screen.getByText('51–51 / 51', { exact: false })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sonraki sayfa' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Önceki sayfa' }));
  await screen.findByText('first-page');
  expect(listCalls().at(-1)[1].params).toEqual(scope);
  expect(axios.post).not.toHaveBeenCalled();
});

it('refreshes even the same scope and invalidates previous readiness before enabling replay', async () => {
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Yapılandırmayı kontrol et' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Requeue' })).toBeEnabled());
  const initial = listCalls().length;
  fireEvent.click(screen.getByRole('button', { name: 'Kapsamı uygula' }));
  await waitFor(() => expect(listCalls().length).toBeGreaterThan(initial));
  await screen.findByText('event');
  expect(screen.getByRole('button', { name: 'Requeue' })).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it('does not turn a failed inspection into an empty or successfully delivered queue', async () => {
  axios.get.mockImplementation(async url => {
    if (url === '/outbox/events') throw new Error('offline');
    return { data: {} };
  });
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('kuyruk boş veya teslim edildi anlamına gelmez');
  expect(screen.queryByText('cm.pages_WebhookOutboxAdmin.bu_filtrede_kayit_yok')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sonraki sayfa' })).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it('fails closed on a malformed successful HTTP response rather than showing an empty queue', async () => {
  axios.get.mockResolvedValue({ data: {} });
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Kuyruk okunamadı');
  expect(screen.queryByText('cm.pages_WebhookOutboxAdmin.bu_filtrede_kayit_yok')).not.toBeInTheDocument();
});

it('switches the applied property scope and clears old readiness when the workspace changes', async () => {
  const view = render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Yapılandırmayı kontrol et' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Requeue' })).toBeEnabled());
  view.rerender(<WebhookOutboxAdmin tenant={{ id: 'other' }} />);
  await waitFor(() => expect(listCalls().at(-1)[1].params.tenant_id).toBe('other'));
  await screen.findByText('event');
  expect(screen.getByRole('button', { name: 'Requeue' })).toBeDisabled();
  expect(screen.getByLabelText('Tesis kimliği (tam eşleşme)')).toHaveValue('other');
  expect(axios.post).not.toHaveBeenCalled();
});

it('distinguishes a disabled availability mapping and shows only safe routing context', async () => {
  const implementation = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url, ...args) => url.endsWith('/readiness')
    ? { data: { can_requeue: false, issues: ['exely_availability_sync_disabled'],
      inventory_target: { room_type: 'Suite', start_date: '2026-11-20', end_date_exclusive: '2026-11-22' } } }
    : implementation(url, ...args));
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Yapılandırmayı kontrol et' }));
  expect(await screen.findByText(/Hedef oda türü: Suite/)).toHaveTextContent('2026-11-20 – 2026-11-22 (çıkış günü hariç)');
  expect(screen.getByText(/eşleştirmesi var, fakat müsaitlik gönderimi kapalı/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Requeue' })).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it('ignores an older property response that arrives after a new filter', async () => {
  let finishOld;
  axios.get.mockImplementation((url, config) => {
    if (url !== '/outbox/events') return Promise.resolve({ data: {} });
    if (!config.params.provider) return new Promise(resolve => { finishOld = resolve; });
    return Promise.resolve({ data: { total: 1, events: [row('new-scope')] } });
  });
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  await waitFor(() => expect(finishOld).toBeTypeOf('function'));
  fireEvent.change(screen.getByLabelText('Outbox sağlayıcı'), { target: { value: 'exely' } });
  fireEvent.click(screen.getByRole('button', { name: 'Kapsamı uygula' }));
  await screen.findByText('new-scope');
  await act(async () => finishOld({ data: { total: 500, events: [row('stale-other-scope')] } }));
  expect(screen.queryByText('stale-other-scope')).not.toBeInTheDocument();
  expect(screen.getByText('new-scope')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sonraki sayfa' })).toBeDisabled();
});

it('sends a bulk replay only to the applied property/provider and makes its full scope explicit', async () => {
  render(<WebhookOutboxAdmin tenant={{ id: 'hotel' }} />);
  await screen.findByText('event');
  fireEvent.change(screen.getByLabelText('Outbox sağlayıcı'), { target: { value: 'exely' } });
  fireEvent.click(screen.getByRole('button', { name: 'Kapsamı uygula' }));
  await screen.findByText('event');
  fireEvent.click(screen.getByRole('button', { name: 'cm.pages_WebhookOutboxAdmin.basarisizlari_replay_et' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/outbox/replay', null, { params: { tenant_id: 'hotel', provider: 'exely' } }));
  expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('Tesis: hotel. Sağlayıcı: exely.') }));
});
