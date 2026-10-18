import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { client } = vi.hoisted(() => ({ client: {
  get: vi.fn(), post: vi.fn(), delete: vi.fn(),
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
} }));
vi.mock('axios', () => ({ default: { create: () => client } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/statements/StatementsWorkspace', () => ({
  default: ({ onChanged }) => <button onClick={() => onChanged?.()}>Test ödeme işlemi tamamlandı</button>,
  money: (amount, currency) => `${amount} ${currency}`,
}));
vi.mock('@/components/statements/PerformanceReport', () => ({ default: () => null }));
vi.mock('@/components/contracts/ContractAmendmentPanel', () => ({
  default: ({ onChanged }) => <button onClick={() => onChanged?.()}>Test sözleşme işlemi tamamlandı</button>,
}));

import AgencyPortalDashboard from '../AgencyPortalDashboard';

let pending;
const empty = { yours: [], theirs: [], counts: { yours: 0, theirs: 0, overdue: 0 } };
const pendingCalls = () => client.get.mock.calls.filter(([path]) => path === '/marketplace/v1/pending-actions').length;

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('agency_token', 'test-session');
  localStorage.setItem('agency_portal_mode', 'marketplace');
  pending = { ...empty, yours: [{ kind: 'statement_approval', owner: 'yours', record_id: 's1', target: 'statements', ref: 'EKS-1' }] };
  client.get.mockReset().mockImplementation(async path => {
    if (path.endsWith('/profile')) return { data: { user: { email: 'agency@example.com' }, agency: { name: 'Agency A' }, hotels: [] } };
    if (path === '/marketplace/v1/pending-actions') return { data: pending };
    if (path === '/marketplace/v1/contracts/mine') return { data: { contracts: [{
      id: 'c1', status: 'approved', hotel_name: 'Demo', valid_from: '2026-10-01', valid_to: '2027-10-01',
      commission_pct: 15, pending_amendment: { proposed_by_side: 'hotel' },
    }] } };
    return { data: {} };
  });
});
afterEach(() => { cleanup(); localStorage.clear(); vi.clearAllMocks(); });

describe('agency pending-centre integration', () => {
  it('refreshes immediately after a statement action without switching tabs', async () => {
    render(<MemoryRouter><AgencyPortalDashboard /></MemoryRouter>);
    await screen.findByTestId('pending-statement_approval-yours');
    await userEvent.click(screen.getByRole('button', { name: /İşleme al/ }));
    const complete = await screen.findByRole('button', { name: 'Test ödeme işlemi tamamlandı' });
    const before = pendingCalls();
    pending = empty;
    await userEvent.click(complete);
    await waitFor(() => expect(pendingCalls()).toBeGreaterThan(before));
    expect(await screen.findByTestId('pending-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('pending-statement_approval-yours')).not.toBeInTheDocument();
  });

  it('refreshes after a contract amendment action', async () => {
    pending = { ...empty, yours: [{ kind: 'contract_amendment', owner: 'yours', record_id: 'c1', target: 'contracts', ref: 'SOZ-1' }] };
    render(<MemoryRouter><AgencyPortalDashboard /></MemoryRouter>);
    await screen.findByTestId('pending-contract_amendment-yours');
    await userEvent.click(screen.getByRole('button', { name: /İşleme al/ }));
    const complete = await screen.findByRole('button', { name: 'Test sözleşme işlemi tamamlandı' });
    const before = pendingCalls();
    pending = empty;
    await userEvent.click(complete);
    await waitFor(() => expect(pendingCalls()).toBeGreaterThan(before));
    expect(await screen.findByTestId('pending-empty')).toBeInTheDocument();
  });

  it('does not request marketplace work when legacy portal tabs change', async () => {
    localStorage.setItem('agency_portal_mode', 'hotel');
    render(<MemoryRouter><AgencyPortalDashboard /></MemoryRouter>);
    await screen.findByTestId('agency-portal-dashboard');
    await userEvent.click(screen.getByTestId('tab-reservations'));
    await waitFor(() => expect(client.get).toHaveBeenCalledWith('/agency-portal/reservations'));
    expect(pendingCalls()).toBe(0);
    expect(screen.queryByTestId('agency-pending-card')).not.toBeInTheDocument();
  });
});
