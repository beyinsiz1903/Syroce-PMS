import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import axios from 'axios';
import CRMWorkspace from '@/pages/CRMWorkspace';

vi.mock('axios');
vi.mock('@/pages/SalesCRM', () => ({ default: () => <div>Sales CRM panel</div> }));
vi.mock('@/pages/GuestRelationsDashboard', () => ({ default: () => <div>Guest relations panel</div> }));
vi.mock('@/components/pms/KVKKManager', () => ({ default: () => <div>Privacy panel</div> }));

describe('CRMWorkspace contracts', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads tenant-scoped intelligence and duplicate candidates without fabricated totals', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('duplicates')) return Promise.resolve({ data: { duplicates: [{ id: 'd1', score: 0.8 }] } });
      if (url.includes('campaigns')) return Promise.resolve({ data: { campaigns: [] } });
      return Promise.resolve({ data: { guests_analyzed: 12, top_value_guests: [], high_churn_guests: [], upsell_opportunities: [] } });
    });
    render(<CRMWorkspace />);

    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument());
    expect(axios.get).toHaveBeenCalledWith('/data-intelligence/guests/dashboard', { params: { limit: 30 } });
    expect(axios.get).toHaveBeenCalledWith('/cross-property/duplicates/scan', { params: { min_score: 0.6, limit: 50 } });
    expect(axios.get).toHaveBeenCalledWith('/marketing/campaigns', { params: { limit: 100 } });
    expect(screen.getByText('CRM Merkezi')).toBeInTheDocument();
  });

  it('fails closed when intelligence is unavailable', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'Yetkisiz işlem' } } });
    render(<CRMWorkspace />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Yetkisiz işlem');
    expect(screen.queryByText('12')).not.toBeInTheDocument();
  });
});
