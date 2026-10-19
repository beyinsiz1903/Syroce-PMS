import React from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import HousekeepingDetailedReports from '@/components/HousekeepingDetailedReports';
import AdrRevparSection from '@/pages/reports/AdrRevparSection';
import NightScreen from '@/components/NightScreen';

// Report acceptance audit 2026-10-19 (housekeeping and ADR ported from it).
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => (typeof fallback === 'string' ? fallback : key), i18n: { language: 'tr' } }) }));
vi.mock('recharts', () => {
  const Box = ({ children }) => <div>{children}</div>;
  const Empty = () => null;
  return { ResponsiveContainer: Box, BarChart: Box, Bar: Empty, XAxis: Empty, YAxis: Empty, CartesianGrid: Empty, Tooltip: Empty };
});

beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => {}); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('housekeeping report HTTP errors are not presented as an empty successful report', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ detail: 'isolated unavailable report' }) })));
  render(<HousekeepingDetailedReports />);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  await screen.findByText('hkReports.roomStatusSummary');
  expect(await screen.findByRole('alert')).toBeInTheDocument();
});

it('a successful housekeeping load shows no error', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ summary: { total_rooms: 10 }, staff_performance: [] }) })));
  render(<HousekeepingDetailedReports />);
  await screen.findByText('hkReports.roomStatusSummary');
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('ADR details expose sold-night denominator separately from occupied nights', () => {
  render(<AdrRevparSection data={{}} s={{}} pc={{}} reportPeriod="daily" periodMetrics={{
    adr: 2500, adr_by_currency: { TRY: 2500 }, room_revenue: 5000, room_revenue_by_currency: { TRY: 5000 },
    occupied_room_nights: 5, sold_room_nights: 2, available_room_nights: 17, revenue_source: 'accrued',
  }} />);
  expect(screen.getByText(/Satılan oda.gecesi/i)).toBeInTheDocument();
  expect(screen.getByTestId('adr-sold-nights')).toHaveTextContent('2');
  expect(screen.getByTestId('adr-formula')).toHaveTextContent('3 gece dolu ama satılmamış');
});

it('the night screen overlay is excluded from print output', () => {
  vi.useFakeTimers();
  try {
    render(<NightScreen />);
    act(() => { vi.advanceTimersByTime(10 * 60 * 1000 + 1); });
    expect(screen.getByTestId('night-screen-overlay').className).toContain('print:hidden');
  } finally {
    vi.useRealTimers();
  }
});

it('the reports page shell does not stretch to a screen height in print', async () => {
  // A min-height of 100vh-64px became a near-blank second A4 page (measured
  // with Chromium print: 2 pages before, 1 after, for a one-page report).
  const fs = await import('node:fs');
  const page = fs.readFileSync('src/pages/BasicReports.jsx', 'utf8');
  expect(page).toContain('min-h-[calc(100vh-64px)] bg-slate-50/70 print:block print:min-h-0 print:bg-white');
});
