import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { toastSuccess } = vi.hoisted(() => ({ toastSuccess: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: vi.fn() } }));

import ContractAmendmentPanel from '@/components/contracts/ContractAmendmentPanel';

const contract = {
  id: 'c1', status: 'approved', payment_terms: 'prepaid', commission_pct: 15, contract_type: 'commission', currency: 'TRY',
  cancellation_policy: { free_until_days_before: 7, penalty_pct: 50, no_show_penalty_pct: 100 },
  valid_from: '2026-10-16', valid_to: '2027-12-31', credit_limit: 10000, credit_currency: 'TRY',
};

describe('ContractAmendmentPanel', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('lets the agency propose pay-at-hotel, sending only what changed', async () => {
    const api = { post: vi.fn(() => Promise.resolve({ data: { contract } })) };
    render(<ContractAmendmentPanel side="agency" api={api} base="/marketplace/v1/contracts/c1/amendments" contract={contract} />);
    await userEvent.click(screen.getByText('Değişiklik öner'));
    await userEvent.selectOptions(screen.getByLabelText('Ödeme koşulu'), 'on_arrival');
    await userEvent.click(screen.getByText('Teklifi gönder'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/marketplace/v1/contracts/c1/amendments', { note: '', payment_terms: 'on_arrival' }));
  });

  it("shows the agency's pending proposal to the hotel, which approves with a new credit limit", async () => {
    const pending = { ...contract, pending_amendment: { id: 'x1', proposed_by_side: 'agency', changes: { payment_terms: 'on_arrival' }, note: 'Girişte ödeme' } };
    const api = { post: vi.fn(() => Promise.resolve({ data: { contract } })) };
    const onChanged = vi.fn();
    render(<ContractAmendmentPanel side="hotel" api={api} base="/marketplace/incoming-requests/c1/amendments" contract={pending} onChanged={onChanged} />);
    expect(screen.getByText('Ödeme: Ön ödemeli → Girişte')).toBeTruthy();
    expect(screen.getByText('Reddet').closest('button').disabled).toBe(true); // a rejection needs a reason
    await userEvent.type(screen.getByLabelText(/Kredi limiti/), '15000');
    await userEvent.click(screen.getByText('Değişikliği onayla'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/marketplace/incoming-requests/c1/amendments/x1/approve',
      { note: '', credit_limit: 15000, credit_currency: 'TRY' }));
    expect(onChanged).toHaveBeenCalled();
  });

  it('lets the proposer only withdraw its own proposal', async () => {
    const pending = { ...contract, pending_amendment: { id: 'x2', proposed_by_side: 'agency', changes: { commission_pct: 12 } } };
    const api = { post: vi.fn(() => Promise.resolve({ data: { contract } })) };
    render(<ContractAmendmentPanel side="agency" api={api} base="/b" contract={pending} />);
    expect(screen.queryByText('Değişikliği onayla')).toBeNull();
    await userEvent.click(screen.getByText('Teklifi geri çek'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/b/x2/withdraw', {}));
  });
});
