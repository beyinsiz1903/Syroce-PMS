import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import EodReportPage from '../EodReportPage';
import api from '@/api/axios';

vi.mock('@/api/axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ data: { business_date: '2026-09-05', payments_by_currency: { EUR: 50, USD: -10 },
    revenue_by_currency: { EUR: 100, USD: 20 }, payments_by_method_currency: {}, extras_by_currency: {},
    occupancy_rate: 0, occupied: 0, rooms_total: 10, open_folios: 0, open_handovers: 0,
  } });
});

it('opens the PMS business day, not the browser calendar day, and keeps money currencies', async () => {
  render(<EodReportPage />);
  await waitFor(() => expect(screen.getByLabelText('Rapor iş günü')).toHaveValue('2026-09-05'));
  expect(api.get.mock.calls[0][1].params.business_date).toBeUndefined();
  expect(screen.getByTestId('eod-report-page').textContent).toContain('EUR');
  expect(screen.getByTestId('eod-report-page').textContent).toContain('USD');
  fireEvent.change(screen.getByLabelText('Rapor iş günü'), { target: { value: '2026-09-06' } });
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(api.get.mock.calls[1][1].params.business_date).toBe('2026-09-06');
  expect(api.get.mock.calls[0][1].signal.aborted).toBe(true);
});
