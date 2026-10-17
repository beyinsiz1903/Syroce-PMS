import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { get, translate } = vi.hoisted(() => ({ get: vi.fn(), translate: key => key }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/components/statements/PerformanceReport', () => ({ default: () => <div>Canonical report</div> }));
import TravelAgentARAP from '../TravelAgentARAP';

afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe('TravelAgentARAP directory integration', () => {
  it('lists the Extranet partner alongside local cards, and archives are an explicit read-only view', async () => {
    const real = { agency_id: 'local', agency_name: 'Manual Agency', commission_rate: 15, balance: 0 };
    const test = { agency_id: 'test', agency_name: '=cmd test', commission_rate: 10, balance: 0, archived: true, readonly_finance: true };
    get.mockImplementation((url, config) => {
      if (url === '/agent-arap/summary') return Promise.resolve({ data: { total_agencies: 1, agencies: config?.params?.include_archived ? [real, test] : [real] } });
      if (url === '/agent-arap/aging') return Promise.resolve({ data: {} });
      if (url === '/agent-arap/extranet-agencies') return Promise.resolve({ data: { agencies: [{ id: 'a1', name: 'Test Acente E2E', approved: true, currencies: [] }] } });
      return Promise.reject(new Error(`Unexpected ${url}`));
    });
    render(<MemoryRouter><TravelAgentARAP /></MemoryRouter>);
    await screen.findByText('Yerel / eski manuel cari özeti');
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'agentArap.tabLedger' }), { button: 0, ctrlKey: false });
    expect(await screen.findByText('Test Acente E2E')).toBeTruthy();
    expect(within(screen.getByRole('tabpanel', { name: 'agentArap.tabLedger' })).getByText('Manual Agency')).toBeTruthy();
    expect(screen.queryByText('=cmd test')).toBeNull();
    fireEvent.click(screen.getByLabelText('Pasif / test / örnek kayıtları göster'));
    await waitFor(() => expect(within(screen.getByRole('tabpanel', { name: 'agentArap.tabLedger' })).getByText('=cmd test')).toBeTruthy());
    expect(screen.getByText('Arşiv / salt okunur')).toBeTruthy();
    await waitFor(() => expect(get).toHaveBeenCalledWith('/agent-arap/summary', { params: { include_archived: true } }));
    expect(screen.getAllByRole('button', { name: /agentArap.recordPayment/ }).filter(button => button.disabled)).toHaveLength(1);
  });
});
