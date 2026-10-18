import { fireEvent, render, screen } from '@testing-library/react';
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
});
