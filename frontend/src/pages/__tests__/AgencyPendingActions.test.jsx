import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import AgencyPendingActions from '../AgencyPendingActions';

const navigate = vi.fn();
vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

describe('AgencyPendingActions (hotel)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: {
      counts: { yours: 2, theirs: 0, overdue: 0 }, theirs: [],
      yours: [
        { kind: 'contract_request', owner: 'yours', record_id: 'c1', target: 'contracts', party_name: 'Syroce Travel', ref: 'SOZ-2026-0015' },
        { kind: 'statement_approval', owner: 'yours', record_id: 's1', target: 'statements', party_name: 'Syroce Travel', ref: 'EKS-2026-0002' },
      ],
    } });
  });

  it('lists the hotel side and opens the screen that handles each item', async () => {
    render(<AgencyPendingActions />);
    expect(axios.get).toHaveBeenCalledWith('/marketplace/hotel/pending-actions');
    expect(await screen.findByTestId('pending-contract_request-yours')).toHaveTextContent('Sözleşme talebi onayınızı bekliyor');
    const [contract, statement] = screen.getAllByRole('button', { name: /İşleme al/ });
    fireEvent.click(contract);
    expect(navigate).toHaveBeenCalledWith('/app/incoming-agency-contracts');
    fireEvent.click(statement);
    expect(navigate).toHaveBeenCalledWith('/app/agency-statements');
  });

  it('opens approved contracts for an amendment rather than the pending requests tab', async () => {
    axios.get.mockResolvedValueOnce({ data: { yours: [{ kind: 'contract_amendment', owner: 'yours', record_id: 'c1', target: 'contracts' }], theirs: [] } });
    render(<AgencyPendingActions />);
    fireEvent.click(await screen.findByRole('button', { name: /İşleme al/ }));
    expect(navigate).toHaveBeenCalledWith('/app/incoming-agency-contracts?tab=active');
  });

  it('never describes a loading failure as no pending work, and supports retry', async () => {
    axios.get.mockRejectedValueOnce({ response: { status: 403, data: { detail: 'Yetki gerekli' } } });
    render(<AgencyPendingActions />);
    expect(await screen.findByTestId('pending-load-error')).toHaveTextContent('Yetki gerekli');
    expect(screen.queryByTestId('pending-empty')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Yeniden dene' }));
    expect(await screen.findByTestId('pending-contract_request-yours')).toBeInTheDocument();
    expect(screen.queryByTestId('pending-load-error')).not.toBeInTheDocument();
  });

  it('marks the last successful list as stale when refreshing fails', async () => {
    render(<AgencyPendingActions />);
    await screen.findByTestId('pending-contract_request-yours');
    axios.get.mockRejectedValueOnce({ response: { status: 503 } });
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
    expect(await screen.findByTestId('pending-load-error')).toHaveTextContent('güncel olmayabilir');
    expect(screen.getByTestId('pending-contract_request-yours')).toBeInTheDocument();
  });

  it('does not carry the previous hotel list or its late response into a new context', async () => {
    let oldReply;
    axios.get.mockReturnValueOnce(new Promise(resolve => { oldReply = resolve; }));
    const { rerender } = render(<AgencyPendingActions user={{ id: 'admin' }} tenant={{ id: 'old-hotel' }} />);
    axios.get.mockResolvedValueOnce({ data: { yours: [], theirs: [] } });
    rerender(<AgencyPendingActions user={{ id: 'admin' }} tenant={{ id: 'new-hotel' }} />);
    await screen.findByTestId('pending-empty');
    await act(async () => oldReply({ data: { yours: [{ kind: 'contract_request', owner: 'yours', party_name: 'Old hotel private', record_id: 'private' }], theirs: [] } }));
    expect(screen.queryByText(/Old hotel private/)).not.toBeInTheDocument();
    expect(screen.getByTestId('pending-empty')).toBeInTheDocument();
  });
});
