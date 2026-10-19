import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
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

beforeEach(() => api.get.mockReset());
const report = date => ({ data: { daily: [{ date, rooms_otb: 2, rooms_forecast: 2, occupancy_pct: 20, revenue_otb: 100, currency: 'EUR' }] } });
const selectTab = name => fireEvent.mouseDown(screen.getByTestId(`tab-${name}`), { button: 0, ctrlKey: false });

it('clears previous financial results and shows a persistent error on failed refresh', async () => {
  api.get.mockResolvedValueOnce(report('2026-10-18')).mockRejectedValueOnce(new Error('Sunucuya ulaşılamıyor'));
  render(<ForecastReportsPage />);
  await screen.findByText('2026-10-18');
  fireEvent.click(screen.getByTestId('button-load-forecast'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Sunucuya ulaşılamıyor');
  expect(screen.queryByText('2026-10-18')).not.toBeInTheDocument();
  expect(screen.queryByText('Seçili kapsamda rapor kaydı bulunmuyor.')).not.toBeInTheDocument();
});

it('hides results after filter changes and ignores an earlier response after explicit refresh', async () => {
  let finishOld;
  api.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
  api.get.mockResolvedValueOnce(report('2026-10-19'));
  render(<ForecastReportsPage />);
  fireEvent.change(screen.getByTestId('input-forecast-segment'), { target: { value: 'Kurumsal' } });
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('status')).toHaveTextContent('Filtreler değişti');
  fireEvent.click(screen.getByTestId('button-load-forecast'));
  await screen.findByText('2026-10-19');
  expect(api.get).toHaveBeenLastCalledWith('/analytics/forecast', { params: { days: 30, segment: 'Kurumsal' } });
  await act(async () => finishOld(report('2026-10-18')));
  expect(screen.queryByText('2026-10-18')).not.toBeInTheDocument();
  expect(screen.getByText('2026-10-19')).toBeInTheDocument();
  fireEvent.change(screen.getByTestId('input-forecast-segment'), { target: { value: 'Bireysel' } });
  expect(screen.queryByText('2026-10-19')).not.toBeInTheDocument();
  expect(api.get).toHaveBeenCalledTimes(2);
});

it('keeps active pickup loading until its own request finishes, regardless of the forecast response', async () => {
  let finishForecast, finishPickup;
  api.get.mockImplementationOnce(() => new Promise(resolve => { finishForecast = resolve; }));
  api.get.mockImplementationOnce(() => new Promise(resolve => { finishPickup = resolve; }));
  render(<ForecastReportsPage />);
  selectTab('pickup');
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(screen.getByTestId('button-load-pickup')).toBeDisabled();
  await act(async () => finishForecast(report('2026-10-18')));
  expect(screen.getByTestId('button-load-pickup')).toBeDisabled();
  expect(screen.getByRole('status')).toHaveTextContent('Rapor yükleniyor');
  await act(async () => finishPickup({ data: { daily: [], total_revenue_picked: 0, total_rooms_picked: 0, currency: 'EUR' } }));
  expect(screen.getByTestId('button-load-pickup')).toBeEnabled();
  expect(screen.getByRole('status')).toHaveTextContent('rapor kaydı bulunmuyor');
});

it('distinguishes a successful empty report and rejects a cleared pace date without an API call', async () => {
  api.get.mockResolvedValue({ data: { daily: [], current: [] } });
  render(<ForecastReportsPage />);
  expect(await screen.findByText('Seçili kapsamda rapor kaydı bulunmuyor.')).toBeInTheDocument();
  selectTab('pace');
  await waitFor(() => expect(screen.getByTestId('button-load-pace')).toBeEnabled());
  const calls = api.get.mock.calls.length;
  fireEvent.change(screen.getByTestId('input-pace-date'), { target: { value: '' } });
  fireEvent.click(screen.getByTestId('button-load-pace'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Geçerli bir rapor tarihi seçin');
  expect(api.get).toHaveBeenCalledTimes(calls);
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
