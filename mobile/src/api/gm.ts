import { api } from './client';

// Mirrors backend/domains/pms/dashboard_router/gm.py
// GET /api/gm/snapshot-enhanced  &  GET /api/gm/complaint-management

export type GmMetrics = {
  date: string;
  occupancy: number;
  revenue: number;
  adr: number;
  revpar: number;
  check_ins: number;
  check_outs: number;
  complaints: number;
  pending_tasks: number;
};

export type GmTrend = 'up' | 'down';

// Point-in-time ("now") housekeeping room-status summary.
export type GmHousekeeping = {
  total_rooms: number;
  available: number;
  occupied: number;
  dirty: number;
  cleaning: number;
  inspected: number;
  out_of_order: number;
  maintenance: number;
  ready_rooms: number;
  dirty_rooms: number;
};

// Channel performance over the last 30 days (by booking source).
export type GmChannel = {
  source: string;
  bookings: number;
  revenue: number;
};

export type GmSnapshot = {
  today: GmMetrics;
  yesterday: GmMetrics;
  last_week: GmMetrics;
  open_faults: number;
  housekeeping: GmHousekeeping;
  channels: GmChannel[];
  trends: {
    occupancy_trend: GmTrend;
    revenue_trend: GmTrend;
    complaints_trend: GmTrend;
  };
};

// GET /api/gm/snapshot-enhanced
export async function getGmSnapshot(): Promise<GmSnapshot> {
  return api.get<GmSnapshot>('/api/gm/snapshot-enhanced');
}

export type Complaint = {
  id: string;
  guest_name: string;
  rating: number;
  category: string;
  comment: string;
  created_at?: string;
  days_open: number;
};

export type CategoryBreakdown = {
  category: string;
  category_tr: string;
  count: number;
};

export type ComplaintManagement = {
  active_complaints: Complaint[];
  active_count: number;
  category_breakdown: CategoryBreakdown[];
  avg_resolution_time_hours: number;
  urgent_complaints: number;
};

// GET /api/gm/complaint-management
export async function getComplaintManagement(): Promise<ComplaintManagement> {
  return api.get<ComplaintManagement>('/api/gm/complaint-management');
}

// ── Revenue trend (last 7 / 30 days) ──────────────────────────────────────
// Mirrors GET /api/revenue/pickup-analysis (JWT-only, no extra permission).
// Only the `historical` array is real per-day data (revenue summed by
// check-in date from actual bookings). The endpoint's `forecast` array is an
// arithmetic projection on the backend, so the dashboard never charts it.
export type PickupPoint = {
  date: string;
  occupancy: number;
  bookings: number;
  revenue: number;
  type: string;
};

export type PickupAnalysis = {
  historical: PickupPoint[];
  forecast: PickupPoint[];
  summary: {
    avg_occupancy_30d: number;
    avg_revenue_30d: number;
    trend: GmTrend;
  };
};

// `historical` is returned oldest → newest, so slicing the tail gives the most
// recent N days. We always request 30 days and derive the 7-day view client
// side to keep this to a single request.
export async function getPickupAnalysis(daysBack = 30): Promise<PickupAnalysis> {
  return api.get<PickupAnalysis>('/api/revenue/pickup-analysis', {
    days_back: daysBack,
    days_forward: 7,
  });
}

// ── Guest satisfaction (NPS) ──────────────────────────────────────────────
// Mirrors GET /api/nps/score (JWT-only). Computed from real guest feedback.
export type NpsScore = {
  nps_score: number;
  promoters: number;
  passives: number;
  detractors: number;
  total_responses: number;
  period_days: number;
};

export async function getNpsScore(days = 30): Promise<NpsScore> {
  return api.get<NpsScore>('/api/nps/score', { days });
}

// ── Sales target (budget vs actual) ───────────────────────────────────────
// Mirrors GET /api/executive/budget-overview (JWT-only). `rev_actual` is
// derived from real bookings; `rev_target` comes from the tenant's configured
// budget (defaults to 0 when unset). The widget only renders a month whose
// `rev_target > 0`, so no placeholder target is ever shown.
export type BudgetMonth = {
  month: number;
  occ_target: number;
  occ_actual: number;
  adr_target: number;
  adr_actual: number;
  rev_target: number;
  rev_actual: number;
};

export type BudgetOverview = {
  year: number;
  currency: string;
  months: BudgetMonth[];
};

export async function getBudgetOverview(): Promise<BudgetOverview> {
  return api.get<BudgetOverview>('/api/executive/budget-overview');
}
