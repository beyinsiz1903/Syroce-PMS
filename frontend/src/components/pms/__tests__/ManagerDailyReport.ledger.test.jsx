import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import api from '@/api/axios';
import ManagerDailyReport from '../ManagerDailyReport';

vi.mock('@/api/axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

describe('manager report uses verified accounting revenue', () => {
  it('does not substitute a booking total or mix currencies in its financial cards', async () => {
    api.get.mockResolvedValue({ data: { total_revenue_by_currency: { TRY: 200, USD: 100 }, adr_by_currency: { TRY: 50, USD: 25 }, rev_par_by_currency: { TRY: 20, USD: 10 } } });
    render(<ManagerDailyReport businessDate="2026-10-26" bookings={[{ check_in: '2026-10-25', check_out: '2026-10-28', total_amount: 999999, currency: 'TRY' }]} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/reports/revenue?start_date=2026-10-26&end_date=2026-10-26&nocache=1'));
    expect(await screen.findByText(/USD.*100,00/)).toBeInTheDocument();
    expect(screen.queryByText(/333\.333/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'pmsComponents.managerReport.print' })).toBeEnabled();
  });
  it('shows a financial read failure and disables printing instead of inventing zero', async () => {
    api.get.mockRejectedValue(new Error('failed'));
    render(<ManagerDailyReport businessDate="2026-10-26" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Finansal rapor alınamadı');
    expect(screen.getByRole('button', { name: 'pmsComponents.managerReport.print' })).toBeDisabled();
  });
});
