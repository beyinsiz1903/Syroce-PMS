import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
import NightAuditLogs from '../NightAuditLogs';

const run = {
  id: 'local-run-1', business_date: '2026-10-25', status: 'completed', dry_run: false,
  started_at: '2026-10-27T08:52:01.462208+00:00', completed_at: '2026-10-27T08:52:02.935409+00:00',
  started_by: 'local-operator', processed_count: 25, skipped_count: 2, failed_count: 0,
  total_room_revenue: 888888, lock_token: 'must-not-render', errors: [], warnings: [],
};
const payload = (runs = [run], total = runs.length) => ({ data: { runs, total, limit: 20, skip: 0 } });
const mount = () => render(<MemoryRouter><NightAuditLogs user={{}} tenant={{ currency: 'TRY' }} /></MemoryRouter>);
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-01T06:00:00Z'));
  get.mockReset().mockResolvedValue(payload());
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

it('renders the real runs contract, separating business day and actual Istanbul event times', async () => {
  mount();
  const row = (await screen.findByText('2026-10-25')).closest('tr');
  expect(within(row).getByText('27.10.2026 11:52:01')).toBeInTheDocument();
  expect(within(row).getByText('27.10.2026 11:52:02')).toBeInTheDocument();
  expect(within(row).getByText('Tamamlandı')).toBeInTheDocument();
  expect(get).toHaveBeenCalledWith('/night-audit/runs', { params: {
    limit: 20, skip: 0, start_date: '2026-10-25', end_date: '2026-11-01',
  } });
  fireEvent.click(within(row).getByRole('button', { name: 'Detay' }));
  expect(screen.queryByText(/888888|must-not-render/)).not.toBeInTheDocument();
});

it.each([
  [{ id: 'operator-id', email: 'operator@example.invalid' }, 'operator@example.invalid'],
  [{ id: 'operator-id', name: 'Vardiya sorumlusu' }, 'Vardiya sorumlusu'],
  [{ unexpected: true }, '—'],
])('renders legacy structured actor %j without crashing the whole history', async (actor, label) => {
  get.mockResolvedValue(payload([{ ...run, started_by: actor }]));
  mount();
  const row = (await screen.findByText('2026-10-25')).closest('tr');
  expect(within(row).getByText(label)).toBeInTheDocument();
  expect(within(row).getByText('27.10.2026 11:52:01')).toBeInTheDocument();
  fireEvent.click(within(row).getByRole('button', { name: 'Detay' }));
  expect(screen.getByText('local-run-1')).toBeInTheDocument();
});

it('distinguishes simulations and superseded runs, with page-scoped operational counts', async () => {
  get.mockResolvedValue(payload([run, { ...run, id: 'dry-run', status: 'dry_run_completed', dry_run: true },
    { ...run, id: 'superseded', status: 'rerun_superseded', dry_run: true }]));
  mount();
  const table = await screen.findByRole('table');
  expect(within(table).getByText('Simülasyon tamamlandı')).toBeInTheDocument();
  expect(within(table).getByText('Yerine yeni koşu işlendi')).toBeInTheDocument();
  expect(screen.getByText('Bu sayfadaki gerçek tamamlanan')).toBeInTheDocument();
  expect(screen.getByText(/Mali tutarlar/)).toHaveTextContent(/günlük.*rapor/i);
  expect(screen.queryByText(/Success Rate|Toplam Charges/)).not.toBeInTheDocument();
});

it('uses server pagination without silently dropping records after the first page', async () => {
  get.mockResolvedValueOnce(payload(Array.from({ length: 20 }, (_, i) => ({ ...run, id: `run-${i}` })), 21))
    .mockResolvedValueOnce(payload([{ ...run, id: 'last-run', started_by: 'last-page-operator' }], 21));
  mount();
  await screen.findByText('1–20 / 21');
  fireEvent.click(screen.getByRole('button', { name: 'Sonraki' }));
  expect(await screen.findByText('last-page-operator')).toBeInTheDocument();
  expect(get.mock.calls[1][1].params.skip).toBe(20);
  expect(screen.getByText('21–21 / 21')).toBeInTheDocument();
});

it('clears stale rows when editing filters and submits dates/status at skip zero', async () => {
  mount();
  await screen.findByText('local-operator');
  fireEvent.change(screen.getByLabelText('Durum'), { target: { value: 'rerun_superseded' } });
  expect(screen.queryByText('local-operator')).not.toBeInTheDocument();
  get.mockResolvedValueOnce(payload([]));
  fireEvent.click(screen.getByRole('button', { name: 'Uygula' }));
  await screen.findByText(/Bu filtrelerle kayıt bulunamadı/);
  expect(get.mock.calls[1][1].params).toEqual({ limit: 20, skip: 0,
    start_date: '2026-10-25', end_date: '2026-11-01', status: 'rerun_superseded' });
});

it('rejects reversed dates locally without querying or showing an empty success', async () => {
  mount();
  await screen.findByText('local-operator');
  fireEvent.change(screen.getByLabelText('Başlangıç iş günü'), { target: { value: '2026-11-02' } });
  fireEvent.click(screen.getByRole('button', { name: 'Uygula' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Başlangıç iş günü bitişten sonra olamaz');
  expect(get).toHaveBeenCalledTimes(1);
});

it('keeps failure distinct from empty and removes previously successful rows', async () => {
  mount();
  await screen.findByText('local-operator');
  get.mockRejectedValueOnce(new Error('local unavailable'));
  fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Gün sonu geçmişi yüklenemedi');
  expect(screen.queryByText('local-operator')).not.toBeInTheDocument();
  expect(screen.queryByText(/Bu filtrelerle kayıt bulunamadı/)).not.toBeInTheDocument();
});

it('does not treat an invalid logs-shaped response as a successful empty history', async () => {
  get.mockResolvedValue({ data: { logs: [], stats: null } });
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('Gün sonu geçmişi yüklenemedi');
});

it('discards a delayed request after its filter context has changed', async () => {
  let resolveOld;
  get.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
  mount();
  fireEvent.change(screen.getByLabelText('Durum'), { target: { value: 'failed' } });
  get.mockResolvedValueOnce(payload([{ ...run, status: 'failed', started_by: 'current-operator' }]));
  fireEvent.click(screen.getByRole('button', { name: 'Uygula' }));
  expect(await screen.findByText('current-operator')).toBeInTheDocument();
  await act(async () => resolveOld(payload()));
  expect(screen.queryByText('local-operator')).not.toBeInTheDocument();
  expect(screen.getByText('current-operator')).toBeInTheDocument();
});
