import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const { get, translate } = vi.hoisted(() => ({ get: vi.fn(), translate: (key, fallback) => fallback || key }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));

import { TimelineEvent } from '../AuditTimelinePage';
import EntityHistoryDrawer from '@/components/EntityHistoryDrawer';
import SecurityLogs from '@/components/SecurityLogs';
import LogViewer, { buildSystemLogCsv } from '../LogViewer';
import MobileLogViewer from '../MobileLogViewer';
import NightAuditLogs from '../NightAuditLogs';
import KVKKManager from '@/components/pms/KVKKManager';
import { HistoryTab } from '../reservation-detail/GuestServiceTabs';

const stamp = '2026-10-31T22:05:06.123456'; // Legacy backend UTC, no zone suffix.
const expected = '01.11.2026 01:05:06';
const log = { id: 'local-clock', timestamp: stamp, level: 'INFO', user: 'Yerel operatör', message: 'Yalnız yerel saat kabulü', action: 'created' };
beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async path => ({ data: path.startsWith('/audit/timeline/') ? { trail: [{ ...log, operation: 'update' }] }
    : path.startsWith('/security/login-logs') ? { logs: [{ ...log, success: true, email: 'local@example.invalid' }] }
      : path === '/kvkk/requests' ? { requests: [], total: 0 } : path === '/kvkk/consents' ? { consents: [], total: 0 }
        : path === '/kvkk/audit-log' ? { logs: [log] } : path === '/gdpr/retention-policy' ? { policies: [] }
          : path === '/night-audit/history' ? { logs: [{ ...log, audit_date: '2026-10-26', status: 'completed' }], stats: null }
            : { logs: [log], log_levels: { INFO: 1 } } }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

it('reservation history converts UTC once, crosses midnight and identifies its display zone', () => {
  render(<HistoryTab history={[{ id: 'local-history', created_at: stamp, action: 'created', actor: 'Yerel operatör' }]} roomMoves={[]} />);
  expect(screen.getByText('01.11.2026 01:05')).toBeInTheDocument();
  expect(screen.getByText(/Europe\/Istanbul/)).toBeInTheDocument();
});
it('central audit events use the same explicit hotel clock instead of the browser zone', () => {
  render(<TimelineEvent event={log} expanded={false} onToggle={() => {}} t={translate} i18n={{ language: 'tr' }} />);
  expect(screen.getByText(expected)).toHaveAttribute('title', expect.stringContaining('Europe/Istanbul'));
});
it('entity audit drawer shows the same clock for the same legacy UTC event', async () => {
  render(<EntityHistoryDrawer entityType="booking" entityId="local-only" onClose={() => {}} />);
  expect(await screen.findByText(expected)).toBeInTheDocument();
});
it('desktop system logs show converted event time with its zone', async () => {
  render(<MemoryRouter><LogViewer user={{}} /></MemoryRouter>);
  expect(await screen.findByText(expected)).toHaveAttribute('title', expect.stringContaining('Europe/Istanbul'));
});
it('mobile system logs retain the date when the event crosses hotel midnight', async () => {
  render(<MemoryRouter><MobileLogViewer user={{}} /></MemoryRouter>);
  expect(await screen.findByText(expected)).toBeInTheDocument();
});
it('security logs show an unambiguous event date and time', async () => {
  render(<SecurityLogs />);
  expect(await screen.findByText(expected)).toBeInTheDocument();
});
it('KVKK audit uses the event clock without altering request calendar dates', async () => {
  render(<KVKKManager />);
  const tab = await screen.findByRole('tab', { name: /auditTab.*1/ });
  fireEvent.mouseDown(tab, { button: 0 });
  expect(await screen.findByText(expected)).toBeInTheDocument();
});
it('night-audit logs distinguish historical business day from actual event date/time', async () => {
  render(<MemoryRouter><NightAuditLogs user={{}} tenant={{ currency: 'TRY' }} /></MemoryRouter>);
  const row = (await screen.findByText('2026-10-26')).closest('tr');
  expect(within(row).getByText(expected)).toBeInTheDocument();
  expect(within(row).getByText('2026-10-26')).toBeInTheDocument();
});
it('night-audit default date filters follow hotel midnight, not UTC or browser date', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-31T22:05:00Z'));
  const { container } = render(<MemoryRouter><NightAuditLogs user={{}} tenant={{ currency: 'TRY' }} /></MemoryRouter>);
  await screen.findByText('2026-10-26');
  const fields = container.querySelectorAll('input[type="date"]');
  expect(fields[0]).toHaveValue('2026-10-25');
  expect(fields[1]).toHaveValue('2026-11-01');
});

it('log CSV retains the source timestamp alongside the labelled display time, escaping cells safely', () => {
  const csv = buildSystemLogCsv([{ ...log, user: '=1+1', message: 'virgül, "alıntı"\nikinci satır' }]);
  expect(csv).toContain(`"${stamp}"`);
  expect(csv).toContain(`"${expected}"`);
  expect(csv).toContain('Türkiye saati · Europe/Istanbul');
  expect(csv).toContain('"\'=1+1"');
  expect(csv).toContain('"virgül, ""alıntı""\nikinci satır"');
});

it('failed log reload removes old rows and disables stale CSV export', async () => {
  render(<MemoryRouter><LogViewer user={{}} /></MemoryRouter>);
  await screen.findByText(expected);
  get.mockRejectedValueOnce(new Error('local unavailable'));
  fireEvent.click(screen.getByRole('button', { name: 'Logları yenile' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('yüklenemedi');
  expect(screen.queryByText(expected)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Logları CSV indir' })).toBeDisabled();
});

it('a delayed older log response cannot replace the latest refresh', async () => {
  render(<MemoryRouter><LogViewer user={{}} /></MemoryRouter>);
  await screen.findByText(expected);
  let resolveOld;
  let resolveNew;
  get.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
    .mockImplementationOnce(() => new Promise(resolve => { resolveNew = resolve; }));
  // Two operator refreshes enter the same event loop before React hides the controls.
  const button = screen.getByRole('button', { name: 'Logları yenile' });
  await act(async () => { button.click(); button.click(); });
  await act(async () => resolveNew({ data: { logs: [{ ...log, message: 'Güncel sonuç' }] } }));
  expect(await screen.findByText('Güncel sonuç')).toBeInTheDocument();
  await act(async () => resolveOld({ data: { logs: [{ ...log, message: 'Eski sonuç' }] } }));
  expect(screen.queryByText('Eski sonuç')).not.toBeInTheDocument();
  expect(screen.getByText('Güncel sonuç')).toBeInTheDocument();
});
