import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import api from '@/api/axios';
import ManagerDailyReport from '../ManagerDailyReport';
import { operations } from './managerOperationsFixture';

vi.mock('@/api/axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
afterEach(cleanup);

describe('manager report uses verified accounting revenue', () => {
  it('does not substitute a booking total or mix currencies in its financial cards', async () => {
    api.get.mockImplementation(url => Promise.resolve({ data: url.includes('manager-daily-operations') ? operations() : { total_revenue_by_currency: { TRY: 200, USD: 100 }, adr_by_currency: { TRY: 50, USD: 25 }, rev_par_by_currency: { TRY: 20, USD: 10 } } }));
    render(<ManagerDailyReport businessDate="2026-10-26" bookings={[{ check_in: '2026-10-25', check_out: '2026-10-28', total_amount: 999999, currency: 'TRY' }]} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/reports/revenue?start_date=2026-10-26&end_date=2026-10-26&nocache=1'));
    expect(await screen.findByText(/USD.*100,00/)).toBeInTheDocument();
    expect(screen.queryByText(/333\.333/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'pmsComponents.managerReport.print' })).toBeEnabled();
  });
  it('shows a financial read failure and disables printing instead of inventing zero', async () => {
    api.get.mockRejectedValue(new Error('failed'));
    render(<ManagerDailyReport businessDate="2026-10-26" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Finansal rapor veya gerçekleşen konaklama kaynağı alınamadı');
    expect(screen.getByRole('button', { name: 'pmsComponents.managerReport.print' })).toBeDisabled();
  });
  it('does not print stale operations after a date change or a failed operational read', async () => {
    const money = { total_revenue_by_currency: {}, adr_by_currency: {}, rev_par_by_currency: {} };
    api.get.mockImplementation(url => Promise.resolve({ data: url.includes('manager-daily-operations') ? operations() : money }));
    const { container } = render(<ManagerDailyReport businessDate="2026-10-26" />);
    const print = () => screen.getByRole('button', { name: 'pmsComponents.managerReport.print' });
    await waitFor(() => expect(print()).toBeEnabled());
    const pending = {};
    api.get.mockImplementation(url => url.includes('manager-daily-operations') ? new Promise(resolve => { pending.resolve = resolve; }) : Promise.resolve({ data: money }));
    fireEvent.change(container.querySelector('input[type="date"]'), { target: { value: '2026-10-27' } });
    expect(print()).toBeDisabled();
    await act(async () => pending.resolve({ data: operations('2026-10-26') }));
    expect(await screen.findByRole('alert')).toBeInTheDocument(); expect(print()).toBeDisabled();
  });
});
