import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/components/PropertySwitcher', () => ({ default: () => null }));

import MobileApprovals from '@/pages/MobileApprovals';

const pendingApproval = {
  id: 'approval-test',
  type: 'refund',
  amount: 25,
  reason: 'Test düzeltmesi',
  requested_by_name: 'Test Operator',
  status: 'pending',
  priority: 'normal',
  created_at: '2026-08-14T10:00:00Z',
};

describe('MobileApprovals active contract', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue({ data: { approvals: [pendingApproval] } });
    post.mockResolvedValue({ data: { status: 'approved' } });
  });

  afterEach(() => cleanup());

  it('normalizes the active approval response and uses the POST mutation contract', async () => {
    render(
      <MemoryRouter>
        <MobileApprovals user={{ role: 'super_admin' }} />
      </MemoryRouter>,
    );

    expect(await screen.findByText('mobileApprovals.types.refund')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Geri' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Yenile' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'mobileApprovals.actions.approve' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'mobileApprovals.actions.approve' }).at(-1));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/approvals/approval-test/approve',
      { note: '' },
    ));
  });

  it('does not render mutation controls for an unrelated role', async () => {
    render(
      <MemoryRouter>
        <MobileApprovals user={{ role: 'staff' }} />
      </MemoryRouter>,
    );

    await screen.findByText('mobileApprovals.types.refund');
    expect(screen.queryByRole('button', { name: 'mobileApprovals.actions.approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'mobileApprovals.actions.reject' })).not.toBeInTheDocument();
  });
});
