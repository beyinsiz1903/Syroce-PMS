import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ForecastReportsPage from '../ForecastReportsPage';
import api from '@/api/axios';

vi.mock('@/api/axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('recharts', () => {
  const Container = ({ children }) => <div>{children}</div>;
  const Empty = () => null;
  return { ResponsiveContainer: Container, LineChart: Container, BarChart: Container, Line: Empty, Bar: Empty,
    XAxis: Empty, YAxis: Empty, Tooltip: Empty, CartesianGrid: Empty, Legend: Empty };
});

it('shows forecast revenue, ADR and RevPAR in their actual currencies, not as null/TRY', async () => {
  api.get.mockResolvedValue({ data: { daily: [{ date: '2026-10-18', rooms_otb: 2, rooms_forecast: 2, occupancy_pct: 20,
    adr: null, revpar: null, revenue_otb: null, revenue_forecast: null,
    adr_by_currency: { EUR: 50, USD: 100 }, revpar_by_currency: { EUR: 10, USD: 20 },
    revenue_otb_by_currency: { EUR: 100, USD: 200 }, revenue_forecast_by_currency: { EUR: 100, USD: 200 }, confidence: .5,
  }] } });
  render(<ForecastReportsPage />);
  await screen.findByText('2026-10-18');
  const table = screen.getByRole('table');
  expect(table.textContent).toContain('EUR:');
  expect(table.textContent).toContain('USD:');
  expect(table.textContent).not.toContain('₺');
  expect(table.textContent).not.toContain('null');
});
