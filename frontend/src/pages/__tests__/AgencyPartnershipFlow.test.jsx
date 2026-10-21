import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post, error } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), error: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error } }));
import AgencyPartnerDirectory from '@/components/contracts/AgencyPartnerDirectory';
import ContractInitialOffer from '@/components/contracts/ContractInitialOffer';

afterEach(() => { cleanup(); vi.clearAllMocks(); });
beforeEach(() => { get.mockResolvedValue({data: {agencies: []}}); post.mockResolvedValue({data: {ok: true}}); });

describe('Mutual partnership workflow', () => {
  it('lets the hotel discover an uncontracted agency and request terms, not rates', async () => {
    get.mockResolvedValue({data: {agencies: [{id: 'a1', name: 'Synthetic Agency', country: 'TR'}]}});
    render(<AgencyPartnerDirectory />);
    await userEvent.click(await screen.findByRole('button', {name: 'Çalışmak istiyorum, şartlarınızı iletin'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/marketplace/incoming-requests/partnership-requests', {agency_id: 'a1'}));
    expect(screen.getByText(/Bu talep satış yetkisi vermez/)).toBeInTheDocument();
    expect(post.mock.calls.some(([path]) => path.includes('rate'))).toBe(false);
  });
  it('does not allow duplicate requests or requests to already-contracted agencies', async () => {
    get.mockResolvedValue({data: {agencies: [{id: 'a1', name: 'Pending', request_pending: true}, {id: 'a2', name: 'Agreed', contract_active: true}]}});
    render(<AgencyPartnerDirectory />);
    expect(await screen.findByRole('button', {name: 'Şartlar istendi'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Sözleşme yürürlükte'})).toBeDisabled();
  });
  it('shows a retry when discovery fails instead of an empty successful network', async () => {
    get.mockRejectedValueOnce(new Error('offline'));
    render(<AgencyPartnerDirectory />);
    expect(await screen.findByRole('alert')).toHaveTextContent('yüklenemedi');
    await userEvent.click(screen.getByRole('button', {name: 'Yeniden dene'}));
    expect(await screen.findByText('Henüz aktif acente bulunmuyor.')).toBeInTheDocument();
  });
  it('shows changed terms and requires affirmative consent before agency acceptance', async () => {
    const accept = vi.fn();
    const contract = {id: 'c1', status: 'pending', awaiting_party: 'agency', commission_pct: 10, currency: 'EUR',
      valid_from: '2026-11-01', valid_to: '2027-10-31', payment_terms: 'net_15', special_terms: 'Synthetic terms',
      cancellation_policy: {free_until_days_before: 7, penalty_pct: 50, no_show_penalty_pct: 100}};
    render(<ContractInitialOffer contract={contract} onAccept={accept} />);
    const button = screen.getByRole('button', {name: 'Karşı teklifi onayla'});
    expect(button).toBeDisabled();
    expect(screen.getByText(/Synthetic terms/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(button);
    expect(accept).toHaveBeenCalledWith(contract);
  });
  it('does not offer agency self-approval of its original proposal', () => {
    render(<ContractInitialOffer contract={{status: 'pending', awaiting_party: 'hotel'}} onAccept={vi.fn()} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
