import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import OnboardingWizard from '../OnboardingWizard';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

const progress = { is_tenant_admin: true, completed: 4, total: 13, progress_pct: 31,
  steps: ['hotel_info_completed', 'rooms_configured', 'rates_configured', 'team_members_added'].map(step_id => ({ step_id, completed: true })) };
const missingAgency = { module: 'agency_extranet', status: 'incomplete',
  setup: [{ key: 'contract', label: 'Onaylı acente sözleşmesi', ok: false, path: '/app/incoming-agency-contracts' }], usage: [] };
const readyAgency = { ...missingAgency, status: 'ready', setup: [{ ...missingAgency.setup[0], ok: true }] };
const response = (modules) => ({ data: { tenant_id: 't1', modules } });
const getCount = (path) => axios.get.mock.calls.filter(([url]) => url === path).length;
const renderWizard = () => render(<OnboardingWizard user={{ role: 'admin' }} tenant={{ id: 't1' }} />);
const openModules = async () => fireEvent.click(await screen.findByRole('button', { name: /Modüller/ }));

function mockApi(getReadiness, getProgress = () => Promise.resolve({ data: progress })) {
  axios.get.mockImplementation(url => {
    if (url === '/onboarding/progress') return getProgress();
    if (url === '/modules/readiness') return getReadiness();
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe('OnboardingWizard readiness and progress', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows known missing setup even when usage makes the overall module unknown', async () => {
    mockApi(() => Promise.resolve(response({ agency_extranet: { ...missingAgency, status: 'unknown',
      usage: [{ key: 'agency_bookings_30d', label: 'Son 30 günde acente rezervasyonu', ok: null }] } })));
    renderWizard();
    await openModules();
    expect(screen.getByTestId('setup-module-agency_extranet')).toHaveTextContent('Onaylı acente sözleşmesi');
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
    expect(screen.getByTestId('onboarding-modules-step')).not.toHaveTextContent('Tamamlandı');
    expect(screen.getByText('4/5 · 80%')).toBeInTheDocument();
  });

  it('counts module setup as the fifth actionable step, not the summary card', async () => {
    mockApi(() => Promise.resolve(response({ agency_extranet: missingAgency })));
    renderWizard();
    await openModules();
    expect(screen.getByText('4/5 · 80%')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /6\. Tamamlandı/ }));
    expect(screen.getByText('Kurulum özeti')).toBeInTheDocument();
    expect(screen.getByTestId('onboarding-modules-pending')).toHaveTextContent('1 modülün');
    expect(screen.queryByText('Hazırsınız!')).not.toBeInTheDocument();
  });

  it('reaches 100% only after all setup steps are verified, even if usage is unavailable', async () => {
    mockApi(() => Promise.resolve(response({ agency_extranet: { ...readyAgency, status: 'unknown',
      usage: [{ key: 'bookings', label: 'Rezervasyon geçmişi', ok: null }] } })));
    renderWizard();
    await openModules();
    expect(screen.getByText('5/5 · 100%')).toBeInTheDocument();
    expect(screen.getByTestId('onboarding-modules-step')).toHaveTextContent('Tamamlandı');
    expect(screen.getByTestId('module-setup-usage-unknown')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /6\. Tamamlandı/ }));
    expect(screen.getByText('Hazırsınız!')).toBeInTheDocument();
    expect(screen.queryByTestId('onboarding-modules-unverified')).not.toBeInTheDocument();
  });

  it('does not mark unavailable setup checks complete in the module card or summary', async () => {
    mockApi(() => Promise.resolve(response({ agency_extranet: { ...missingAgency, status: 'unknown',
      setup: [{ ...missingAgency.setup[0], ok: null }] } })));
    renderWizard();
    await openModules();
    expect(screen.getByText('4/5 · 80%')).toBeInTheDocument();
    expect(screen.getByTestId('setup-unverified-agency_extranet')).toBeInTheDocument();
    expect(screen.getByTestId('onboarding-modules-step')).not.toHaveTextContent('Tamamlandı');
    fireEvent.click(screen.getByRole('button', { name: /6\. Tamamlandı/ }));
    expect(screen.getByTestId('onboarding-modules-unverified')).toBeInTheDocument();
    expect(screen.queryByTestId('onboarding-modules-pending')).not.toBeInTheDocument();
    expect(screen.queryByText('Hazırsınız!')).not.toBeInTheDocument();
  });

  it('refreshes both data sources with the global refresh, without duplicate initial requests', async () => {
    let current = { agency_extranet: missingAgency };
    mockApi(() => Promise.resolve(response(current)));
    renderWizard();
    await openModules();
    expect(getCount('/onboarding/progress')).toBe(1);
    expect(getCount('/modules/readiness')).toBe(1);
    current = { agency_extranet: readyAgency };
    fireEvent.click(screen.getAllByRole('button', { name: 'Yenile' })[0]);
    expect(await screen.findByTestId('module-setup-complete')).toBeInTheDocument();
    expect(getCount('/onboarding/progress')).toBe(2);
    expect(getCount('/modules/readiness')).toBe(2);
    expect(screen.queryByTestId('setup-module-agency_extranet')).not.toBeInTheDocument();
    expect(screen.getByText('5/5 · 100%')).toBeInTheDocument();
  });

  it('removes stale completion during a local refresh, then displays the new evidence', async () => {
    const pending = deferred();
    let calls = 0;
    mockApi(() => ++calls === 1 ? Promise.resolve(response({ agency_extranet: readyAgency })) : pending.promise);
    renderWizard();
    await openModules();
    expect(screen.getByText('5/5 · 100%')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Yenile' })[1]);
    expect(screen.getByRole('status')).toHaveTextContent('Modül durumu kontrol ediliyor');
    expect(screen.getByText('4/5 · 80%')).toBeInTheDocument();
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
    await act(async () => pending.resolve(response({ agency_extranet: missingAgency })));
    expect(await screen.findByTestId('setup-module-agency_extranet')).toBeInTheDocument();
    expect(getCount('/onboarding/progress')).toBe(1);
  });

  it.each([403, 500])('handles a readiness error (%s) without claiming completion and supports refresh', async (status) => {
    let fail = true;
    mockApi(() => fail ? Promise.reject({ response: { status } }) : Promise.resolve(response({ agency_extranet: readyAgency })));
    renderWizard();
    await openModules();
    expect(screen.getByText('4/5 · 80%')).toBeInTheDocument();
    expect(screen.getByTestId('onboarding-modules-step')).toHaveTextContent(status === 403 ? 'otel yöneticisi' : 'Modül durumu alınamadı');
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
    expect(await screen.findByText('5/5 · 100%')).toBeInTheDocument();
  });

  it.each([undefined, null, [], { spa: null }])('rejects malformed successful readiness responses (%j)', async (modules) => {
    mockApi(() => Promise.resolve(response(modules)));
    renderWizard();
    await openModules();
    expect(screen.getByTestId('onboarding-modules-step')).toHaveTextContent('Modül durumu alınamadı');
    expect(screen.getByText('4/5 · 80%')).toBeInTheDocument();
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
  });

  it('does not let an older local request overwrite a newer global refresh', async () => {
    const older = deferred();
    let calls = 0;
    mockApi(() => ++calls === 2 ? older.promise : Promise.resolve(response({ agency_extranet: readyAgency })));
    renderWizard();
    await openModules();
    fireEvent.click(screen.getAllByRole('button', { name: 'Yenile' })[1]);
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
    expect(await screen.findByText('5/5 · 100%')).toBeInTheDocument();
    await act(async () => older.resolve(response({ agency_extranet: missingAgency })));
    expect(screen.getByTestId('module-setup-complete')).toBeInTheDocument();
    expect(screen.queryByTestId('setup-module-agency_extranet')).not.toBeInTheDocument();
  });

  it('keeps module evidence available when the progress endpoint fails', async () => {
    let fail = true;
    mockApi(() => Promise.resolve(response({ agency_extranet: readyAgency })),
      () => fail ? Promise.reject(new Error('progress unavailable')) : Promise.resolve({ data: progress }));
    renderWizard();
    expect(await screen.findByText('İlerleme yüklenemedi')).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole('button', { name: /Tekrar Dene/ }));
    await openModules();
    expect(screen.getByText('5/5 · 100%')).toBeInTheDocument();
    expect(getCount('/modules/readiness')).toBe(2);
  });

  it('shows a progress refresh failure rather than claiming stale core steps are verified', async () => {
    let fail = false;
    mockApi(() => Promise.resolve(response({ agency_extranet: readyAgency })),
      () => fail ? Promise.reject(new Error('progress unavailable')) : Promise.resolve({ data: progress }));
    renderWizard();
    await openModules();
    fail = true;
    fireEvent.click(screen.getAllByRole('button', { name: 'Yenile' })[0]);
    expect(await screen.findByRole('alert')).toHaveTextContent('İlerleme yenilenemedi');
    expect(screen.getByText('1/5 · 20%')).toBeInTheDocument();
    expect(screen.getByTestId('module-setup-complete')).toBeInTheDocument();
    await waitFor(() => expect(getCount('/modules/readiness')).toBe(2));
  });
});
