import { cleanup, fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, post, patch, toast, translate } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(),
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn() }, translate: (key, fallback) => fallback || key.replace('pmsComponents.kvkk.', '') }));
vi.mock('axios', () => ({ default: { get, post, patch } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate }) }));
import KVKKManager from '../KVKKManager';

let requests;
let logs;
beforeEach(() => {
  vi.clearAllMocks(); requests = []; logs = [];
  get.mockImplementation(async path => ({ data: path === '/kvkk/requests' ? { requests, total: requests.length }
    : path === '/kvkk/consents' ? { consents: [], total: 0 } : path === '/kvkk/audit-log' ? { logs }
      : { policies: [{ data_type: 'guest_pii', retention_days: 100 }], configured: false } }));
});
afterEach(cleanup);
async function openRequest() {
  render(<KVKKManager />);
  await screen.findByText('100 gün');
  fireEvent.click(screen.getByRole('button', { name: 'newRequest', exact: true }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getAllByRole('textbox')[0], { target: { value: 'Yalnız yerel örnek' } });
  fireEvent.click(within(dialog).getByRole('combobox'));
  fireEvent.click(screen.getByRole('option', { name: 'requestTypes.access', exact: true }));
  return dialog;
}
it('refreshes the authoritative requests and embedded audit view after a successful creation', async () => {
  post.mockImplementation(async (_path, body) => {
    const row = { id: 'local-id', ...body, status: 'pending', date: '2026-10-31' };
    requests = [row]; logs = [{ id: 'created', action: 'data_request_created', target: row.id, user: 'local@example.invalid' }];
    return { data: row };
  });
  const dialog = await openRequest();
  fireEvent.click(within(dialog).getByRole('button', { name: 'createRequest', exact: true }));
  expect(await screen.findByRole('tab', { name: 'auditTab (1)', exact: true })).toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
  expect(get.mock.calls.filter(([url]) => url === '/kvkk/audit-log').length).toBe(2);
});
it('uses the server completion date and refreshes the audit rather than inventing a browser date', async () => {
  requests = [{ id: 'local-id', guest_name: 'Yerel kişi', type: 'access', status: 'pending', date: '2026-10-31' }];
  patch.mockImplementation(async () => { requests = [{ ...requests[0], status: 'completed', response_date: '2026-11-02' }];
    logs = [{ id: 'completed', action: 'data_request_updated', target: 'local-id' }]; return { data: { id: 'local-id', status: 'completed' } }; });
  render(<KVKKManager />); await screen.findByText('100 gün');
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'requestsTab (1)', exact: true }), { button: 0 });
  fireEvent.click(await screen.findByRole('button', { name: 'completeRequest', exact: true }));
  expect(await screen.findByText(/2026-11-02/)).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'auditTab (1)', exact: true })).toBeInTheDocument();
});
it('loads all request, consent and audit pages rather than silently truncating at the server defaults', async () => {
  get.mockImplementation(async (path, options) => {
    const skip = options?.params?.skip || 0;
    const limit = options?.params?.limit || (path === '/kvkk/audit-log' ? 200 : 100);
    const count = path === '/kvkk/audit-log' ? 201 : 101;
    const rows = Array.from({ length: count }, (_, index) => ({ id: `local-${index}`, guest_name: `Yerel ${index}`, type: 'access', status: 'completed' })).slice(skip, skip + limit);
    return { data: path === '/kvkk/requests' ? { requests: rows, total: count } : path === '/kvkk/consents' ? { consents: rows, total: count }
      : path === '/kvkk/audit-log' ? { logs: rows } : { policies: [{ data_type: 'guest_pii', retention_days: 100 }] } };
  });
  render(<KVKKManager />);
  expect(await screen.findByRole('tab', { name: 'requestsTab (101)', exact: true })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'consentsTab (101)', exact: true })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'auditTab (201)', exact: true })).toBeInTheDocument();
});
it('does not repeat completion while the previous update is in flight', async () => {
  requests = [{ id: 'local-id', guest_name: 'Yerel kişi', type: 'access', status: 'pending' }];
  patch.mockReturnValue(new Promise(() => {}));
  render(<KVKKManager />); await screen.findByText('100 gün');
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'requestsTab (1)', exact: true }), { button: 0 });
  const complete = await screen.findByRole('button', { name: 'completeRequest', exact: true });
  fireEvent.click(complete); fireEvent.click(complete);
  expect(patch).toHaveBeenCalledTimes(1);
  expect(complete).toBeDisabled();
});
it('cancels a new administrative request without sending a write', async () => {
  await openRequest();
  fireEvent.click(screen.getByRole('button', { name: 'Kapat', exact: true }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(post).not.toHaveBeenCalled(); expect(patch).not.toHaveBeenCalled();
});

it('shows an incomplete paged source as unknown, not zero or a successful first-page total, and supports explicit refresh', async () => {
  get.mockImplementation(async (path, options) => {
    if (path === '/kvkk/requests') {
      if (options.params.skip) throw new Error('second page unavailable');
      return { data: { total: 101, requests: Array.from({ length: 100 }, (_, index) => ({ id: `local-${index}` })) } };
    }
    return { data: path === '/kvkk/consents' ? { consents: [], total: 0 } : path === '/kvkk/audit-log' ? { logs: [] } : { policies: [] } };
  });
  render(<KVKKManager />);
  expect(await screen.findByRole('alert')).toHaveTextContent('1 KVKK veri kaynağı yüklenemedi');
  expect(screen.getByRole('tab', { name: 'requestsTab (—)', exact: true })).toBeInTheDocument();
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'requestsTab (—)', exact: true }), { button: 0 });
  expect(screen.queryByText('noRequests', { exact: true })).toBeNull();
  get.mockImplementation(async path => ({ data: path === '/kvkk/requests' ? { requests: [{ id: 'recovered', guest_name: 'Yerel kişi', type: 'access', status: 'pending' }], total: 1 }
    : path === '/kvkk/consents' ? { consents: [], total: 0 } : path === '/kvkk/audit-log' ? { logs: [] } : { policies: [] } }));
  fireEvent.click(screen.getByRole('button', { name: 'Yenile', exact: true }));
  expect(await screen.findByRole('tab', { name: 'requestsTab (1)', exact: true })).toBeInTheDocument();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('stops a non-advancing audit endpoint rather than duplicating or looping through the same page', async () => {
  get.mockImplementation(async path => ({ data: path === '/kvkk/audit-log'
    ? { logs: Array.from({ length: 200 }, (_, index) => ({ id: `same-${index}` })) }
    : path === '/kvkk/requests' ? { requests: [], total: 0 } : path === '/kvkk/consents' ? { consents: [], total: 0 } : { policies: [] } }));
  render(<KVKKManager />);
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'auditTab (—)', exact: true })).toBeInTheDocument();
  expect(get.mock.calls.filter(([path]) => path === '/kvkk/audit-log')).toHaveLength(2);
});

it('keeps a rejected creation editable without claiming success or issuing a second write', async () => {
  post.mockRejectedValue(new Error('controlled failure'));
  const dialog = await openRequest();
  fireEvent.click(within(dialog).getByRole('button', { name: 'createRequest', exact: true }));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('createError'));
  expect(within(dialog).getAllByRole('textbox')[0]).toHaveValue('Yalnız yerel örnek');
  expect(post).toHaveBeenCalledTimes(1); expect(toast.success).not.toHaveBeenCalled();
});

it('does not mark a rejected completion as complete or synthesize an audit/date', async () => {
  requests = [{ id: 'local-id', guest_name: 'Yerel kişi', type: 'access', status: 'pending' }];
  patch.mockRejectedValue(new Error('controlled failure'));
  render(<KVKKManager />); await screen.findByText('100 gün');
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'requestsTab (1)', exact: true }), { button: 0 });
  fireEvent.click(await screen.findByRole('button', { name: 'completeRequest', exact: true }));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('completeError'));
  expect(screen.getByRole('button', { name: 'completeRequest', exact: true })).toBeEnabled();
  expect(screen.getByRole('tab', { name: 'auditTab (0)', exact: true })).toBeInTheDocument();
  expect(toast.success).not.toHaveBeenCalled();
});
