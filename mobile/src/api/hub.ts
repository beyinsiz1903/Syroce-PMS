import { api } from './client';

// Mirrors backend/domains/pms/mobile_router/hub.py
// Person-centric aggregation for the common mobile shell (Task #327, Faz 0).
// These endpoints merge EXISTING data (notifications, alerts, tasks,
// approvals) — they introduce no new data or notification types.

export type FeedSource = 'notification' | 'alert';

export type FeedItem = {
  source: FeedSource;
  id: string;
  type: string;
  title: string;
  message: string;
  priority: string;
  read: boolean;
  action_url?: string | null;
  created_at: string;
};

export type FeedResponse = {
  items: FeedItem[];
  count: number;
  offset: number;
  limit: number;
  has_more: boolean;
  unread_count: number;
};

// GET /api/mobile/hub/feed
export async function getFeed(params?: {
  limit?: number;
  offset?: number;
  unread_only?: boolean;
}): Promise<FeedResponse> {
  return api.get<FeedResponse>('/api/mobile/hub/feed', {
    limit: params?.limit,
    offset: params?.offset,
    unread_only: params?.unread_only,
  });
}

// POST /api/mobile/hub/feed/mark-read
export async function markFeedRead(source: FeedSource, id: string): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>('/api/mobile/hub/feed/mark-read', { source, id });
}

export type MyTaskKind = 'housekeeping' | 'maintenance';

export type MyTask = {
  id: string;
  kind: MyTaskKind;
  title: string;
  room_number?: string | null;
  priority: string;
  status: string;
  notes?: string | null;
  created_at: string;
};

export type MyTasksResponse = {
  tasks: MyTask[];
  count: number;
  by_kind: { housekeeping: number; maintenance: number };
};

// GET /api/mobile/hub/my-tasks
export async function getMyTasks(): Promise<MyTasksResponse> {
  return api.get<MyTasksResponse>('/api/mobile/hub/my-tasks');
}

export type TodayDigest = {
  date: string;
  open_tasks: number;
  urgent_tasks: number;
  unread_feed: number;
  pending_approvals: number;
  tasks_preview: MyTask[];
};

// GET /api/mobile/hub/today
export async function getToday(): Promise<TodayDigest> {
  return api.get<TodayDigest>('/api/mobile/hub/today');
}

// The per-item kind selects which existing backend approve/reject endpoint
// the action routes to (see actOnApproval). It is NOT the category key.
export type ApprovalKind = 'approval' | 'approval_request' | 'leave' | 'shift_swap';

export type ApprovalItem = {
  id: string;
  kind: ApprovalKind | string;
  title: string;
  requested_by?: string | null;
  amount?: number | null;
  priority: string;
  status?: string | null;
  target_consent_status?: string | null;
  created_at: string;
};

export type ApprovalCategory = {
  key: 'finance' | 'hr';
  label: string;
  items: ApprovalItem[];
  count: number;
};

export type ApprovalsResponse = {
  categories: ApprovalCategory[];
  total: number;
};

// GET /api/mobile/hub/approvals
export async function getApprovals(): Promise<ApprovalsResponse> {
  return api.get<ApprovalsResponse>('/api/mobile/hub/approvals');
}

export type ApprovalAction = 'approve' | 'reject';

// Approve or reject a single approval item by delegating to the EXISTING,
// already RBAC-guarded backend endpoints — no new endpoints, no RBAC change.
// Routing depends on the item kind because each source collection exposes a
// different endpoint/method/body shape:
//   - approval          -> PUT  /api/approvals/{id}/approve|reject  (PMS)
//   - approval_request  -> POST /api/approvals/{id}/approve|reject  (analytics)
//   - leave             -> POST /api/hr/leave-request/{id}/decision (2-stage)
//   - shift_swap        -> POST /api/hr/shift-swap-request/{id}/decision
export async function actOnApproval(
  item: ApprovalItem,
  action: ApprovalAction,
  reason?: string,
): Promise<unknown> {
  const id = item.id;
  const note = reason ?? '';
  switch (item.kind) {
    case 'approval':
      if (action === 'approve') {
        return api.put(`/api/approvals/${id}/approve`, { notes: note });
      }
      return api.put(`/api/approvals/${id}/reject`, {
        rejection_reason: note,
        notes: note,
      });
    case 'approval_request':
      if (action === 'approve') {
        return api.post(`/api/approvals/${id}/approve`, { note });
      }
      return api.post(`/api/approvals/${id}/reject`, { reason: note });
    case 'leave': {
      // Honour the backend's 2-stage chain: a pending request can only advance
      // to dept_approved; a dept_approved one to the final approved state.
      const decision =
        action === 'reject'
          ? 'reject'
          : item.status === 'dept_approved'
            ? 'approve'
            : 'dept_approve';
      return api.post(`/api/hr/leave-request/${id}/decision`, {
        decision,
        note: note || null,
      });
    }
    case 'shift_swap':
      return api.post(`/api/hr/shift-swap-request/${id}/decision`, {
        action,
        note: note || null,
      });
    default:
      throw new Error(`Bilinmeyen onay türü: ${item.kind}`);
  }
}
