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
