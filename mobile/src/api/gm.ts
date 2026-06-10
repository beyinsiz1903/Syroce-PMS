import { api } from './client';

// Mirrors backend/domains/pms/dashboard_router/gm.py
// GET /api/gm/snapshot-enhanced  &  GET /api/gm/complaint-management

export type GmMetrics = {
  date: string;
  occupancy: number;
  revenue: number;
  check_ins: number;
  check_outs: number;
  complaints: number;
  pending_tasks: number;
};

export type GmTrend = 'up' | 'down';

export type GmSnapshot = {
  today: GmMetrics;
  yesterday: GmMetrics;
  last_week: GmMetrics;
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
