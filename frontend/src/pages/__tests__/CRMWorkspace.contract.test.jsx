import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import CRMWorkspace from '@/pages/CRMWorkspace';
import { BrowserRouter } from 'react-router-dom';

vi.mock('axios');
vi.mock('@/pages/SalesCRM', () => ({ default: () => <div>Sales CRM panel</div> }));
vi.mock('@/pages/GuestRelationsDashboard', () => ({ default: () => <div>Guest relations panel</div> }));
vi.mock('@/components/pms/KVKKManager', () => ({ default: () => <div>Privacy panel</div> }));

describe('CRMWorkspace contracts', () => {
  beforeEach(() => vi.clearAllMocks());

  const renderCRM = (path = '/crm') => {
    window.history.replaceState({}, '', path);
    return render(<BrowserRouter><CRMWorkspace /></BrowserRouter>);
  };

  it('loads the summary first and defers expensive tab sources until requested', async () => {
    const user = userEvent.setup();
    axios.get.mockImplementation((url) => {
      if (url.includes('duplicates')) return Promise.resolve({ data: { matches: [{ score: 0.8, reasons: ['email_exact'], left: { id: 'g1', name: 'Ada Lovelace' }, right: { id: 'g2', name: 'Ada L.' } }] } });
      if (url.includes('campaigns')) return Promise.resolve({ data: { campaigns: [] } });
      if (url.includes('automation/rules')) return Promise.resolve({ data: { rules: [] } });
      return Promise.resolve({ data: { guests_analyzed: 12, top_value_guests: [], high_churn_guests: [], upsell_opportunities: [] } });
    });
    renderCRM();

    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument());
    expect(axios.get).toHaveBeenCalledWith('/data-intelligence/guests/dashboard', { params: { limit: 30 } });
    expect(axios.get).not.toHaveBeenCalledWith('/cross-property/duplicates/scan', expect.anything());
    expect(axios.get).not.toHaveBeenCalledWith('/marketing/campaigns', expect.anything());
    await user.click(screen.getByRole('tab', { name: 'Mükerrer kayıtlar' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/cross-property/duplicates/scan', { params: { min_score: 0.6, skip: 0, limit: 20 } }));
    expect(screen.getByText('CRM Merkezi')).toBeInTheDocument();
  });

  it('fails closed when intelligence is unavailable', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'Yetkisiz işlem' } } });
    renderCRM();
    expect(await screen.findByRole('alert')).toHaveTextContent('Yetkisiz işlem');
    expect(screen.queryByText('12')).not.toBeInTheDocument();
  });

  it('requires explicit confirmation before merging duplicate profiles', async () => {
    const user = userEvent.setup();
    axios.get.mockImplementation((url) => {
      if (url.includes('duplicates')) return Promise.resolve({ data: { matches: [{ score: 0.9, reasons: ['email_exact'], left: { id: 'g1', name: 'Ada Lovelace' }, right: { id: 'g2', name: 'Ada L.' } }] } });
      if (url.includes('campaigns')) return Promise.resolve({ data: { campaigns: [] } });
      if (url.includes('automation/rules')) return Promise.resolve({ data: { rules: [] } });
      return Promise.resolve({ data: { guests_analyzed: 2, top_value_guests: [], high_churn_guests: [], upsell_opportunities: [] } });
    });
    axios.post.mockResolvedValue({ data: { bookings_repointed: 1, folios_repointed: 1 } });
    renderCRM();
    await user.click(await screen.findByRole('tab', { name: 'Mükerrer kayıtlar' }));
    await user.click(await screen.findByRole('button', { name: 'İncele ve birleştir' }));
    expect(axios.post).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Onayla ve birleştir' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'Onayla ve birleştir' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/cross-property/guests/g1/merge', { target_guest_id: 'g2' }));
  });

  it('opens the requested workspace tab from the URL and keeps tab state shareable', async () => {
    const user = userEvent.setup();
    axios.get.mockResolvedValue({ data: {} });
    renderCRM('/crm?tab=sales');
    expect(await screen.findByText('Sales CRM panel')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'KVKK ve izinler' }));
    expect(window.location.search).toBe('?tab=privacy');
    expect(screen.getByText('Privacy panel')).toBeInTheDocument();
  });
});
