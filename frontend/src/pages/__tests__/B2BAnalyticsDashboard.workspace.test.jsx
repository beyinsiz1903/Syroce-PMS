import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));

vi.mock('axios', () => ({
  default: {
    get: (...args) => apiGet(...args),
    isCancel: () => false,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'tr' } }),
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  AreaChart: ({ children }) => <div>{children}</div>,
  Area: () => null,
  BarChart: ({ children }) => <div>{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  PieChart: ({ children }) => <div>{children}</div>,
  Pie: ({ children }) => <div>{children}</div>,
  Cell: () => null,
}));

vi.mock('@/pages/reports/ReportHelpers', () => ({
  KPICard: ({ title, value }) => <div><span>{title}</span><strong>{value}</strong></div>,
  CustomTooltip: () => null,
  COLORS: ['#2563eb', '#059669'],
  formatNumber: (value) => String(value),
}));

import B2BAnalyticsDashboard from '@/pages/B2BAnalyticsDashboard';

const responses = {
  summary: {
    period: { start: '2026-08-01', end: '2026-08-30' },
    data_scope: { usage: 'tenant_metering', usage_is_agency_specific: false },
    kpis: { total_bookings: 0, approved_bookings: 0, active_agencies: 0, api_calls: 32758 },
  },
  agencies: { agencies: [] },
  trends: { trends: [] },
  usage: { scope: 'tenant_metering', agency_specific: false, timeline: [], totals: [] },
  activity: { scope: 'tenant_metering', agency_specific: false, activity_types: [] },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <B2BAnalyticsDashboard tenant={{ currency: 'TRY' }} />
    </MemoryRouter>,
  );
}

describe('B2BAnalyticsDashboard workspace', () => {
  afterEach(cleanup);

  beforeEach(() => {
    apiGet.mockReset();
    apiGet.mockImplementation((path) => {
      if (path.endsWith('/summary')) return Promise.resolve({ data: responses.summary });
      if (path.endsWith('/agency-breakdown')) return Promise.resolve({ data: responses.agencies });
      if (path.endsWith('/booking-trends')) return Promise.resolve({ data: responses.trends });
      if (path.endsWith('/api-usage')) return Promise.resolve({ data: responses.usage });
      if (path.endsWith('/top-endpoints')) return Promise.resolve({ data: responses.activity });
      return Promise.reject(new Error(`Unexpected request: ${path}`));
    });
  });

  it('separates B2B sales metrics from tenant-wide telemetry', async () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'B2B Satış Analitiği' })).toBeInTheDocument();
    expect(screen.getByText(/yalnızca tek bir acenteye ait trafik değildir/)).toBeInTheDocument();
    expect(screen.getByText('Tesis API Trafiği')).toBeInTheDocument();
    expect(await screen.findByText('32758')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Sözleşme Talepleri/ })).toHaveAttribute('href', '/app/incoming-agency-contracts');
    expect(screen.getByRole('link', { name: /Komisyon ve Ödemeler/ })).toHaveAttribute('href', '/travel-agent-arap');

    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(5));
  });
});
