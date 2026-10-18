import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import OnboardingWizard from '../OnboardingWizard';

const navigate = vi.fn();
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

const progress = { steps: [], completed: 3, total: 13, progress_pct: 23, is_tenant_admin: true };

function mockApi(readiness, progressData = progress) {
  axios.get.mockImplementation((url) => {
    if (url === '/onboarding/progress') return Promise.resolve({ data: progressData });
    if (url === '/modules/readiness') return readiness;
    return Promise.resolve({ data: {} });
  });
}

const openModulesStep = async () => {
  fireEvent.click(await screen.findByRole('button', { name: /Modüller/ }));
};

describe('OnboardingWizard modules step', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists missing module setup; rooms open the wizard step, others navigate', async () => {
    mockApi(Promise.resolve({ data: { modules: {
      pms: { module: 'pms', status: 'incomplete', setup: [{ key: 'rooms', label: 'Odalar tanımlı', ok: false, path: '/app/onboarding' }], usage: [] },
      agency_extranet: { module: 'agency_extranet', status: 'incomplete', setup: [{ key: 'contract', label: 'Onaylı acente sözleşmesi', ok: false, path: '/app/incoming-agency-contracts' }], usage: [] },
    } } }));
    render(<OnboardingWizard user={{ role: 'admin' }} tenant={{ id: 't1' }} />);
    await openModulesStep();
    expect(await screen.findByTestId('setup-module-agency_extranet')).toHaveTextContent('Onaylı acente sözleşmesi');
    const [agency, rooms] = [screen.getByTestId('setup-module-agency_extranet'), screen.getByTestId('setup-module-pms')];
    fireEvent.click(agency.querySelector('button'));
    expect(navigate).toHaveBeenCalledWith('/app/incoming-agency-contracts');
    fireEvent.click(rooms.querySelector('button'));
    expect(navigate).toHaveBeenCalledTimes(1);                       // rooms: same wizard, no navigation
    expect(screen.queryByTestId('onboarding-modules-step')).not.toBeInTheDocument();
  });

  it('explains that module setup is for the hotel administrator', async () => {
    mockApi(Promise.reject({ response: { status: 403 } }), { ...progress, is_tenant_admin: false });
    render(<OnboardingWizard user={{ role: 'front_desk' }} tenant={{ id: 't1' }} />);
    await openModulesStep();
    expect(await screen.findByText('Modül kurulumunu otel yöneticisi görebilir.')).toBeInTheDocument();
  });
});
