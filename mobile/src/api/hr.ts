import { api } from './client';

// HR API client — read-focused mirror of backend/domains/hr/router.py (mounted
// under /api). The list endpoints (shifts / leave-requests / attendance) only
// require auth server-side; the (departments) HR entitlement decides whether we
// show the screen. Decisions (leave / shift-swap) flow through the unified
// approvals backbone (see api/hub.ts) and stay gated by require_op("manage_hr").

export type Shift = {
  id: string;
  staff_id?: string;
  staff_name?: string;
  shift_date?: string;
  start_time?: string;
  end_time?: string;
  status?: string;
  crosses_midnight?: boolean;
  notes?: string | null;
};

export type LeaveRequest = {
  id: string;
  staff_id?: string;
  staff_name?: string;
  leave_type?: string;
  start_date?: string;
  end_date?: string;
  status?: string;
  reason?: string | null;
};

export type AttendanceRecord = {
  id: string;
  staff_id?: string;
  staff_name?: string;
  department?: string | null;
  position?: string | null;
  date?: string;
  clock_in?: string | null;
  clock_out?: string | null;
  status?: string;
};

// GET /api/hr/shifts?start=&end= → { items, total, range }
export async function listShifts(params?: {
  start?: string;
  end?: string;
  staff_id?: string;
  department?: string;
}): Promise<Shift[]> {
  const res = await api.get<{ items?: Shift[] }>('/api/hr/shifts', params);
  return res?.items ?? [];
}

// GET /api/hr/leave-requests?status= → { items, total, counts }
export async function listLeaveRequests(params?: {
  status?: string;
  staff_id?: string;
}): Promise<LeaveRequest[]> {
  const res = await api.get<{ items?: LeaveRequest[] }>(
    '/api/hr/leave-requests',
    params,
  );
  return res?.items ?? [];
}

// GET /api/hr/attendance/records?start_date=&end_date= → { records, total, range }
export async function listAttendanceRecords(params?: {
  start_date?: string;
  end_date?: string;
  staff_id?: string;
  limit?: number;
}): Promise<AttendanceRecord[]> {
  const res = await api.get<{ records?: AttendanceRecord[] }>(
    '/api/hr/attendance/records',
    params,
  );
  return res?.records ?? [];
}

export type PerformanceReview = {
  id: string;
  staff_id?: string;
  staff_name?: string;
  reviewer_name?: string | null;
  period?: string | null;
  overall_score?: number;
  goals?: string | null;
  strengths?: string | null;
  improvement_areas?: string | null;
  competency_scores?: Record<string, number>;
  reviewed_at?: string;
};

export type PerformanceSummary = {
  items: PerformanceReview[];
  total: number;
  avg_score: number;
};

// GET /api/hr/performance → { items, total, avg_score }. Backend gates this
// surface with require_op("manage_hr") — the SAME gate as its sibling endpoints
// (POST /hr/performance, leave-request decision). The screen mirrors that with
// a cosmetic manage-HR check so view-only roles (e.g. finance) never see it.
export async function getPerformanceSummary(params?: {
  staff_id?: string;
}): Promise<PerformanceSummary> {
  const res = await api.get<Partial<PerformanceSummary>>(
    '/api/hr/performance',
    params,
  );
  return {
    items: res?.items ?? [],
    total: res?.total ?? 0,
    avg_score: res?.avg_score ?? 0,
  };
}

// The backend's 2-stage leave state machine (Task #263):
//   pending → dept_approve → dept_approved → approve → approved
//   pending | dept_approved → reject → rejected (note ZORUNLU)
export type LeaveDecisionAction = 'dept_approve' | 'approve' | 'reject';

// POST /api/hr/leave-request/{id}/decision — RBAC: require_op("manage_hr").
// A rejection note is mandatory server-side (>= 1 non-blank char).
export async function decideLeaveRequest(
  leaveId: string,
  decision: LeaveDecisionAction,
  note?: string,
): Promise<{ success: boolean; status: string }> {
  return api.post<{ success: boolean; status: string }>(
    `/api/hr/leave-request/${encodeURIComponent(leaveId)}/decision`,
    { decision, note: note || null },
  );
}
