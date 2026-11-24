import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import POSDashboard from '../POSDashboard';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_key, fallback) => fallback }) }));
vi.mock('@/context/EntitlementContext', () => ({ useEntitlements: () => ({ hasFeature: () => false, tenantId: 't' }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-11-12' }));
vi.mock('../../components/POSTableManagement', () => ({ default: () => null }));
vi.mock('../../components/POSMenuItems', () => ({ default: () => null }));
vi.mock('../../components/POSOutletManagement', () => ({ default: () => null }));
vi.mock('../../components/POSReports', () => ({ default: () => null }));
vi.mock('../../components/POSPrinterSettings', () => ({ default: () => null }));
vi.mock('../../components/POSOperations', () => ({ default: () => null }));
afterEach(cleanup);

it.each([
  { gross_sales: 52.8, discounts: 52.8, net_sales: 0, expected: '₺0' },
  { gross_sales: 100, discounts: 20, net_sales: 60, expected: '₺60' },
  { gross_sales: 100, discounts: 0, net_sales: -20, expected: '-₺20' },
])('uses report net sales after concessions/refunds: $net_sales', async ({ expected, ...report }) => {
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pos/z-report'
    ? { ...report, currency: 'TRY', sale_count: 1 } : [] }));
  render(<MemoryRouter><POSDashboard /></MemoryRouter>);
  expect(await screen.findByTestId('stat-revenue')).toHaveTextContent(expected);
  expect(screen.getByText('İş Günü Net Satış')).toBeInTheDocument();
  expect(screen.getByText(/Brüt .* · İndirim/)).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith('/pos/z-report', { params: { date: '2026-11-12' } });
});
