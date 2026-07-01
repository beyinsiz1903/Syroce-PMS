import { api } from './client';

// Mirrors backend/routers/departments/reports.py — all routes are gated by
// require_op("view_finance_reports") on the backend. The mobile UI gate is a
// cosmetic mirror only; the backend remains the source of truth.

export type FinanceSnapshot = {
  report_date: string;
  pending_ar: {
    total: number;
    overdue_breakdown: {
      '0-30_days': number;
      '30-60_days': number;
      '60_plus_days': number;
    };
    overdue_invoices_count: number;
  };
  todays_collections: {
    amount: number;
    payment_count: number;
  };
  mtd_collections: {
    amount: number;
    collection_rate_percentage: number;
  };
  accounting_invoices: {
    pending_count: number;
    pending_total: number;
  };
};

// GET /api/reports/finance-snapshot
export async function getFinanceSnapshot(): Promise<FinanceSnapshot> {
  return api.get<FinanceSnapshot>('/api/reports/finance-snapshot');
}

export type SegmentStat = {
  bookings: number;
  nights: number;
  revenue: number;
  adr: number;
};

export type MarketSegmentReport = {
  start_date: string;
  end_date: string;
  total_bookings: number;
  market_segments: Record<string, SegmentStat>;
  rate_types: Record<string, SegmentStat>;
};

// GET /api/reports/market-segment?start_date=&end_date=
export async function getMarketSegment(
  startDate: string,
  endDate: string,
): Promise<MarketSegmentReport> {
  return api.get<MarketSegmentReport>('/api/reports/market-segment', {
    start_date: startDate,
    end_date: endDate,
  });
}

export type CompanyAgingEntry = {
  company_name: string;
  corporate_code: string;
  total_balance: number;
  aging: {
    '0-7 days': number;
    '8-14 days': number;
    '15-30 days': number;
    '30+ days': number;
  };
  folio_count: number;
};

export type CompanyAgingReport = {
  report_date: string;
  total_ar: number;
  company_count: number;
  companies: CompanyAgingEntry[];
};

// GET /api/reports/company-aging
export async function getCompanyAging(): Promise<CompanyAgingReport> {
  return api.get<CompanyAgingReport>('/api/reports/company-aging');
}

// Format a Date into a local YYYY-MM-DD string (no timezone shift).
// The backend coerces date-only ISO strings to midnight, so YYYY-MM-DD is safe.
function fmtISO(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Default market-segment window: first day of the current month → today.
export function currentMonthRange(): { start: string; end: string } {
  const now = new Date();
  return { start: fmtISO(new Date(now.getFullYear(), now.getMonth(), 1)), end: fmtISO(now) };
}

// Previous calendar month: first day → last day of last month.
export function lastMonthRange(): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const end = new Date(now.getFullYear(), now.getMonth(), 0); // day 0 = last day of prev month
  return { start: fmtISO(start), end: fmtISO(end) };
}

// Rolling 30-day window ending today (inclusive).
export function last30DaysRange(): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now);
  start.setDate(start.getDate() - 29);
  return { start: fmtISO(start), end: fmtISO(now) };
}
